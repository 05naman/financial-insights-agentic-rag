import asyncio
import logging

from app.agent import prompts
from app.agent.deps import AgentDeps
from app.agent.grounding import check_grounding
from app.agent.state import AgentState, SubQuestion
from app.agent.tools import CalculationError, calculate
from app.llm.base import LLMError, Message
from app.llm.json_utils import parse_json
from app.retrieval.schemas import SearchFilters, SearchHit

logger = logging.getLogger(__name__)
INSUFFICIENT = "Insufficient evidence in the provided reports."


def format_evidence(hits: list[SearchHit], max_chars: int) -> str:
    if not hits:
        return "(no evidence found)"
    body = "\n\n".join(
        f"[{h.ticker} FY{h.fiscal_year} p.{h.page}] ({h.chunk_type})\n{h.text[:max_chars]}"
        for h in hits
    )
    return f"<evidence>\n{body}\n</evidence>"


def _catalog_text(catalog: dict[str, list[int]], names: dict[str, str] | None = None) -> str:
    if not catalog:
        return "(none)"
    names = names or {}
    lines = []
    for ticker, years in catalog.items():
        label = f"{ticker} ({names[ticker]})" if ticker in names else ticker
        lines.append(f"- {label}: {', '.join(f'FY{y}' for y in sorted(years))}")
    return "\n".join(lines)


def _history_text(history: list[dict]) -> str:
    if not history:
        return "(none)"
    return "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-6:])


def _clean_sub_questions(raw, catalog: dict[str, list[int]], fallback: str) -> list[SubQuestion]:
    out: list[SubQuestion] = []
    for item in raw or []:
        if not isinstance(item, dict) or not str(item.get("query", "")).strip():
            continue
        tickers = [str(t).upper() for t in item.get("tickers") or [] if str(t).upper() in catalog]
        years = []
        for y in item.get("fiscal_years") or []:
            try:
                years.append(int(y))
            except (TypeError, ValueError):
                continue
        valid_years = {y for t in (tickers or catalog) for y in catalog.get(t, [])}
        years = [y for y in years if y in valid_years]
        out.append(SubQuestion(str(item["query"]).strip(), tickers, years))
    return out[:6] or [SubQuestion(fallback, [], [])]


def build_nodes(deps: AgentDeps) -> dict:
    cfg = deps.config

    async def ask(
        system: str, user: str, state: AgentState, max_tokens: int = 700
    ) -> tuple[str, int]:
        text = await deps.llm.generate(
            [Message("system", system), Message("user", user)],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return text, state.get("llm_calls", 0) + 1

    async def plan(state: AgentState) -> dict:
        calls = state.get("llm_calls", 0)
        sub_qs = [SubQuestion(state["question"], [], [])]
        out_of_scope = False
        try:
            user = f"History:\n{_history_text(state.get('history', []))}\n\nQuestion: {state['question']}"
            text, calls = await ask(
                prompts.PLAN_SYSTEM.format(catalog=_catalog_text(deps.catalog, deps.company_names)),
                user,
                state,
            )
            data = parse_json(text)
            if isinstance(data, dict):
                out_of_scope = bool(data.get("out_of_scope"))
                sub_qs = _clean_sub_questions(
                    data.get("sub_questions"), deps.catalog, state["question"]
                )
        except LLMError as e:
            logger.warning("planner failed, using the raw question: %s", e)
        return {
            "sub_questions": sub_qs,
            "out_of_scope": out_of_scope,
            "llm_calls": calls,
            "rounds": 0,
            "synth_attempts": 0,
            "evidence": [],
            "steps": [
                {
                    "node": "plan",
                    "out_of_scope": out_of_scope,
                    "sub_questions": [s.__dict__ for s in sub_qs],
                }
            ],
        }

    async def retrieve(state: AgentState) -> dict:
        evidence = {h.id: h for h in state.get("evidence", [])}
        searches = []
        for sq in state["sub_questions"]:
            flt = SearchFilters(tickers=sq.tickers, fiscal_years=sq.fiscal_years)
            hits = await asyncio.to_thread(
                deps.retriever.search, sq.query, limit=cfg.top_k, filters=flt
            )
            searches.append(
                {
                    "query": sq.query,
                    "tickers": sq.tickers,
                    "years": sq.fiscal_years,
                    "hits": [h.citation for h in hits],
                }
            )
            for h in hits:
                if h.id not in evidence or h.score > evidence[h.id].score:
                    evidence[h.id] = h
        ranked = sorted(evidence.values(), key=lambda h: h.score, reverse=True)[: cfg.max_evidence]
        # group by company/year/page so the synthesizer reads in document order
        ranked.sort(key=lambda h: (h.ticker, h.fiscal_year, h.page))
        return {
            "evidence": ranked,
            "rounds": state.get("rounds", 0) + 1,
            "steps": [
                {"node": "retrieve", "round": state.get("rounds", 0) + 1, "searches": searches}
            ],
        }

    async def grade(state: AgentState) -> dict:
        evidence = state.get("evidence", [])
        if not evidence:
            sufficient, missing, new_sqs = False, "no passages retrieved", []
            calls = state.get("llm_calls", 0)
        else:
            user = (
                f"Question: {state['question']}\n\nEvidence:\n"
                f"{format_evidence(evidence, cfg.max_passage_chars)}"
            )
            try:
                text, calls = await ask(prompts.GRADE_SYSTEM, user, state)
            except LLMError:
                text, calls = "", state.get("llm_calls", 0)
            data = parse_json(text)
            if isinstance(data, dict):
                sufficient = bool(data.get("sufficient"))
                missing = str(data.get("missing", ""))
                new_sqs = _clean_sub_questions(data.get("new_sub_questions"), deps.catalog, "")
                new_sqs = [s for s in new_sqs if s.query]
            else:  # could not judge: assume sufficient and let grounding catch problems
                sufficient, missing, new_sqs = True, "", []
        update: dict = {
            "sufficient": sufficient,
            "llm_calls": calls,
            "steps": [{"node": "grade", "sufficient": sufficient, "missing": missing}],
        }
        if not sufficient and new_sqs:
            update["sub_questions"] = new_sqs
        return update

    async def compute(state: AgentState) -> dict:
        evidence = state.get("evidence", [])
        calcs: list[dict] = []
        calls = state.get("llm_calls", 0)
        if evidence:
            user = (
                f"Question: {state['question']}\n\nEvidence:\n"
                f"{format_evidence(evidence, cfg.max_passage_chars)}"
            )
            try:
                text, calls = await ask(prompts.COMPUTE_SYSTEM, user, state)
                data = parse_json(text)
                items = data.get("calculations", []) if isinstance(data, dict) else []
                for item in items[:8]:
                    try:
                        value = calculate(str(item["expression"]))
                        calcs.append(
                            {
                                "label": item.get("label", ""),
                                "expression": item["expression"],
                                "value": round(value, 2),
                            }
                        )
                    except (CalculationError, KeyError, TypeError, ValueError):
                        continue
            except LLMError:
                pass
        return {
            "calculations": calcs,
            "llm_calls": calls,
            "steps": [{"node": "compute", "calculations": calcs}],
        }

    async def synthesize(state: AgentState) -> dict:
        evidence = state.get("evidence", [])
        calcs = state.get("calculations", [])
        calc_text = "\n".join(f"- {c['label']}: {c['value']} (= {c['expression']})" for c in calcs)
        user = (
            f"Question: {state['question']}\n\nEvidence:\n{format_evidence(evidence, cfg.max_passage_chars)}"
            f"\n\nCalculation results:\n{calc_text or '(none)'}"
        )
        if state.get("feedback"):
            user += f"\n\nYour previous answer had problems. Fix them: {state['feedback']}"
        if not state.get("sufficient", True):
            user += "\n\nNote: the evidence may be incomplete; state clearly what is missing."
        try:
            answer, calls = await ask(prompts.SYNTH_SYSTEM, user, state, max_tokens=900)
        except LLMError as e:
            logger.warning("synthesis failed, no model available: %s", e)
            return {
                "answer": "Sorry, the language model is unavailable right now. Please try again shortly.",
                "llm_failed": True,
                "synth_attempts": cfg.max_synth_attempts,
                "steps": [{"node": "synthesize", "error": "language model unavailable"}],
            }
        return {
            "answer": answer.strip(),
            "llm_calls": calls,
            "synth_attempts": state.get("synth_attempts", 0) + 1,
            "steps": [{"node": "synthesize", "attempt": state.get("synth_attempts", 0) + 1}],
        }

    async def verify(state: AgentState) -> dict:
        if state.get("llm_failed"):
            return {"grounded": True, "steps": [{"node": "verify", "skipped": "llm unavailable"}]}
        calc_values = [c["value"] for c in state.get("calculations", [])]
        says_insufficient = "insufficient evidence" in state["answer"].lower()
        report = check_grounding(
            state["answer"],
            state.get("evidence", []),
            calc_values,
            state["question"],
            require_citation=not says_insufficient,
        )
        problems = []
        if report.unsupported_numbers:
            problems.append(
                f"numbers not found in the evidence: {', '.join(report.unsupported_numbers)}"
            )
        if report.invalid_citations:
            problems.append(f"citations not in the evidence: {', '.join(report.invalid_citations)}")
        if not report.has_citation:
            problems.append("no citations were given")
        return {
            "grounded": report.ok,
            "unsupported": report.unsupported_numbers,
            "feedback": "; ".join(problems),
            "steps": [{"node": "verify", "grounded": report.ok, "problems": problems}],
        }

    async def finalize(state: AgentState) -> dict:
        if state.get("out_of_scope"):
            answer = (
                "I can only answer questions about the annual reports I have been given "
                "(company performance, financials and risks). I can't give investment advice."
            )
        else:
            answer = state.get("answer", INSUFFICIENT)
            if not state.get("grounded", True):
                answer += (
                    "\n\n⚠ Some figures in this answer could not be verified against the "
                    f"reports: {', '.join(state.get('unsupported', [])) or 'see citations'}."
                )
        return {"answer": answer, "steps": [{"node": "finalize"}]}

    return {
        "plan": plan,
        "retrieve": retrieve,
        "grade": grade,
        "compute": compute,
        "synthesize": synthesize,
        "verify": verify,
        "finalize": finalize,
    }
