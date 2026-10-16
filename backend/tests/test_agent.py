import json

import pytest

from app.agent.deps import AgentConfig, AgentDeps
from app.agent.grounding import check_grounding
from app.agent.tools import CalculationError, calculate
from app.ingestion.pipeline import IngestionPipeline
from app.llm.json_utils import parse_json
from app.retrieval.retriever import Retriever
from app.retrieval.schemas import SearchHit
from app.services.qa import QAService
from tests.test_ingestion import repo  # noqa: F401  (fixture)


class ScriptedLLM:
    """Replies based on which prompt it receives; records every call."""

    def __init__(self, plan=None, grade=None, compute=None, synth=None):
        self.plan = plan or {
            "out_of_scope": False,
            "sub_questions": [
                {"query": "TCS revenue from operations", "tickers": ["TCS"], "fiscal_years": [2024]}
            ],
        }
        self.grade = grade or [{"sufficient": True, "missing": "", "new_sub_questions": []}]
        self.compute = compute or {"calculations": []}
        self.synth = synth or ["Revenue was Rs 2,40,893 crore [TCS FY2024 p.1]."]
        self.calls: list[str] = []

    async def generate(self, messages, *, temperature=0.2, max_tokens=1024):
        system = messages[0].content
        if "plan research" in system:
            self.calls.append("plan")
            return json.dumps(self.plan)
        if "judge whether" in system:
            self.calls.append("grade")
            return json.dumps(self.grade.pop(0) if len(self.grade) > 1 else self.grade[0])
        if "decide which calculations" in system:
            self.calls.append("compute")
            return json.dumps(self.compute)
        self.calls.append("synth")
        return self.synth.pop(0) if len(self.synth) > 1 else self.synth[0]


def hit(text, page=1, ticker="TCS", year=2024):
    return SearchHit("id" + str(page), 1.0, text, ticker, year, page, "text")


# ---- units ----
def test_calculator():
    assert calculate("(240893-225458)/225458*100") == pytest.approx(6.846, rel=1e-3)
    assert calculate("2,000 * 3") == 6000
    with pytest.raises(CalculationError):
        calculate("__import__('os')")
    with pytest.raises(CalculationError):
        calculate("1/0")


def test_parse_json_handles_fences_and_chatter():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    assert parse_json("no json here") is None


def test_grounding_flags_unsupported_numbers_and_bad_citations():
    ev = [hit("Revenue was Rs 2,40,893 crore and margin 24.1%.")]
    ok = check_grounding("Revenue Rs 2,40,893 crore [TCS FY2024 p.1].", ev, [])
    assert ok.ok
    bad = check_grounding(
        "Revenue Rs 3,00,000 crore [TCS FY2024 p.1] and [INFY FY2024 p.9].", ev, []
    )
    assert "3,00,000" in bad.unsupported_numbers
    assert bad.invalid_citations == ["[INFY FY2024 p.9]"]
    assert not check_grounding("Revenue Rs 2,40,893 crore.", ev, []).ok  # no citation
    assert check_grounding("Growth was 6.85%", ev, [6.85], require_citation=False).ok  # calc value


# ---- graph ----
@pytest.fixture
async def service_factory(repo, embedder, store, sample_pdf_dir):  # noqa: F811
    await IngestionPipeline(repo, embedder, store).ingest_dir(sample_pdf_dir)
    retriever = Retriever(embedder, store, reranker=None)
    catalog = {"TCS": [2024], "INFY": [2024]}

    def make(llm, **cfg):
        deps = AgentDeps(llm, retriever, catalog, AgentConfig(**cfg))
        return QAService(llm, retriever, deps)

    return make


async def test_agentic_happy_path(service_factory):
    llm = ScriptedLLM()
    res = await service_factory(llm).answer("What was TCS revenue in FY2024?")
    assert "2,40,893" in res.answer and "⚠" not in res.answer
    assert [(c.ticker, c.page) for c in res.citations] == [("TCS", 1)]
    assert llm.calls == ["plan", "grade", "compute", "synth"]
    assert [s["node"] for s in res.steps][-1] == "finalize"


async def test_agent_rewrites_when_evidence_insufficient(service_factory):
    llm = ScriptedLLM(
        grade=[
            {
                "sufficient": False,
                "missing": "risk info",
                "new_sub_questions": [
                    {"query": "attrition currency risk", "tickers": ["TCS"], "fiscal_years": [2024]}
                ],
            },
            {"sufficient": True, "missing": "", "new_sub_questions": []},
        ]
    )
    res = await service_factory(llm).answer("What are TCS risks?")
    assert llm.calls.count("grade") == 2
    assert sum(1 for s in res.steps if s["node"] == "retrieve") == 2


async def test_retrieval_rounds_are_bounded(service_factory):
    never = {
        "sufficient": False,
        "missing": "x",
        "new_sub_questions": [{"query": "more", "tickers": ["TCS"], "fiscal_years": []}],
    }
    llm = ScriptedLLM(grade=[never])
    res = await service_factory(llm, max_rounds=2).answer("anything")
    assert sum(1 for s in res.steps if s["node"] == "retrieve") == 2


async def test_unsupported_number_triggers_retry_then_warning(service_factory):
    llm = ScriptedLLM(synth=["Revenue was Rs 9,99,999 crore [TCS FY2024 p.1]."])
    res = await service_factory(llm, max_synth_attempts=2).answer("TCS revenue?")
    assert llm.calls.count("synth") == 2
    assert "⚠" in res.answer and "9,99,999" in res.answer


async def test_retry_fixes_answer(service_factory):
    llm = ScriptedLLM(
        synth=[
            "Revenue was Rs 9,99,999 crore [TCS FY2024 p.1].",
            "Revenue was Rs 2,40,893 crore [TCS FY2024 p.1].",
        ]
    )
    res = await service_factory(llm).answer("TCS revenue?")
    assert "2,40,893" in res.answer and "⚠" not in res.answer


async def test_calculation_feeds_grounding(service_factory):
    llm = ScriptedLLM(
        compute={"calculations": [{"label": "growth", "expression": "(240893-225458)/225458*100"}]},
        synth=["Revenue grew 6.85% to Rs 2,40,893 crore [TCS FY2024 p.1]."],
    )
    res = await service_factory(llm).answer("TCS revenue growth?")
    assert "⚠" not in res.answer


async def test_out_of_scope_skips_retrieval(service_factory):
    llm = ScriptedLLM(plan={"out_of_scope": True, "sub_questions": []})
    res = await service_factory(llm).answer("Should I buy TCS shares?")
    assert "investment advice" in res.answer
    assert llm.calls == ["plan"]


async def test_planner_failure_falls_back_to_raw_question(service_factory):
    llm = ScriptedLLM()
    llm.plan = "not json"  # json.dumps -> a JSON string, not a dict
    res = await service_factory(llm).answer("TCS revenue?")
    assert res.answer and res.steps[0]["node"] == "plan"


async def test_single_pass_modes(service_factory):
    llm = ScriptedLLM()
    svc = service_factory(llm)
    for mode in ("naive", "hybrid"):
        res = await svc.answer("TCS revenue?", mode=mode)
        assert res.llm_calls == 1 and res.mode == mode


async def test_llm_outage_returns_clear_message_without_false_warning(service_factory):
    from app.llm.base import LLMError

    class DownLLM:
        async def generate(self, *a, **k):
            raise LLMError("all providers failed")

    res = await service_factory(DownLLM()).answer("TCS revenue?")
    assert "unavailable" in res.answer and "⚠" not in res.answer


def test_grouped_citations_are_parsed_and_checked():
    ev = [hit("Revenue was Rs 2,40,893 crore.", page=1), hit("Risks: attrition.", page=4)]
    ok = check_grounding("Revenue Rs 2,40,893 crore [TCS FY2024 p.1, TCS FY2024 p.4].", ev, [])
    assert ok.ok
    bad = check_grounding("Revenue Rs 2,40,893 crore [TCS FY2024 p.1, TCS FY2024 p.9].", ev, [])
    assert bad.invalid_citations == ["[TCS FY2024 p.9]"]
