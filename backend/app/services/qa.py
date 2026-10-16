import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal

from app.agent import prompts
from app.agent.deps import AgentDeps, ChatLLM
from app.agent.graph import build_graph
from app.agent.grounding import CITATION_RE
from app.agent.nodes import format_evidence
from app.llm.base import Message
from app.retrieval.retriever import Retriever
from app.retrieval.schemas import SearchHit

Mode = Literal["naive", "hybrid", "agentic"]


@dataclass
class Citation:
    ticker: str
    fiscal_year: int
    page: int
    text: str


@dataclass
class AnswerResult:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    llm_calls: int = 0
    mode: str = "agentic"
    retrieved: list[tuple[str, int, int]] = field(default_factory=list)  # (ticker, year, page)


def extract_citations(answer: str, evidence: list[SearchHit]) -> list[Citation]:
    by_key = {(h.ticker, str(h.fiscal_year), str(h.page)): h for h in evidence}
    seen, out = set(), []
    for t, y, p in CITATION_RE.findall(answer):
        key = (t.upper(), y, p)
        if key in by_key and key not in seen:
            seen.add(key)
            h = by_key[key]
            out.append(Citation(h.ticker, h.fiscal_year, h.page, h.text))
    return out


def _locations(hits: list[SearchHit]) -> list[tuple[str, int, int]]:
    return [(h.ticker, h.fiscal_year, h.page) for h in hits]


class QAService:
    """Answers questions in one of three modes so the eval can compare them fairly."""

    def __init__(self, llm: ChatLLM, retriever: Retriever, deps: AgentDeps):
        self.llm = llm
        self.retriever = retriever
        self.deps = deps
        self.graph = build_graph(deps)

    async def answer(self, question: str, *, mode: Mode = "agentic", history=None) -> AnswerResult:
        if mode == "agentic":
            return await self._agentic(question, history or [])
        return await self._single_pass(question, mode)

    async def _single_pass(self, question: str, mode: Mode) -> AnswerResult:
        """Baseline RAG: retrieve once, answer once. 'naive' = dense only; 'hybrid' adds BM25+rerank."""
        hybrid = mode == "hybrid"
        hits = await asyncio.to_thread(
            self.retriever.search,
            question,
            limit=6,
            hybrid=hybrid,
            rerank=hybrid,
            improve=hybrid,  # 'naive' is the plain baseline: no typo fixing, synonyms or auto filters
        )
        evidence = format_evidence(hits, self.deps.config.max_passage_chars)
        text = await self.llm.generate(
            [
                Message("system", prompts.SYNTH_SYSTEM),
                Message("user", f"Question: {question}\n\nEvidence:\n{evidence}"),
            ],
            temperature=0.1,
            max_tokens=900,
        )
        return AnswerResult(
            text.strip(), extract_citations(text, hits), [], 1, mode, _locations(hits)
        )

    async def _agentic(self, question: str, history: list[dict]) -> AnswerResult:
        async for event in self.stream(question, history):
            if event["type"] == "final":
                return event["result"]
        raise RuntimeError("agent produced no result")

    async def stream(self, question: str, history: list[dict] | None = None) -> AsyncIterator[dict]:
        """Yields {'type': 'step', ...} per node, then {'type': 'final', 'result': ...}."""
        state: dict = {"question": question, "history": history or [], "steps": []}
        steps: list[dict] = []
        async for update in self.graph.astream(state, stream_mode="updates"):
            for _node, delta in update.items():
                state.update({k: v for k, v in delta.items() if k != "steps"})
                for step in delta.get("steps", []):
                    steps.append(step)
                    yield {"type": "step", "step": step}
        answer = state.get("answer", "")
        result = AnswerResult(
            answer,
            extract_citations(answer, state.get("evidence", [])),
            steps,
            state.get("llm_calls", 0),
            "agentic",
            _locations(state.get("evidence", [])),
        )
        yield {"type": "final", "result": result}
