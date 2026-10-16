import operator
from dataclasses import dataclass
from typing import Annotated, TypedDict

from app.retrieval.schemas import SearchHit


@dataclass
class SubQuestion:
    query: str
    tickers: list[str]
    fiscal_years: list[int]


class AgentState(TypedDict, total=False):
    question: str
    history: list[dict]  # [{"role": "user"|"assistant", "content": str}]
    sub_questions: list[SubQuestion]
    evidence: list[SearchHit]
    calculations: list[dict]  # [{"label", "expression", "value"}]
    answer: str
    out_of_scope: bool
    sufficient: bool
    rounds: int  # retrieval rounds used
    synth_attempts: int
    feedback: str  # grounding feedback for the next synthesis attempt
    grounded: bool
    llm_failed: bool  # synthesis could not reach any LLM provider
    unsupported: list[str]
    llm_calls: int
    steps: Annotated[list[dict], operator.add]
