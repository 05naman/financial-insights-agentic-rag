from dataclasses import dataclass, field
from typing import Protocol

from app.llm.base import Message
from app.retrieval.retriever import Retriever


class ChatLLM(Protocol):
    async def generate(
        self, messages: list[Message], *, temperature: float = ..., max_tokens: int = ...
    ) -> str: ...


@dataclass
class AgentConfig:
    max_rounds: int = 2  # retrieval attempts (initial + rewrites)
    max_synth_attempts: int = 2
    top_k: int = 6  # passages per sub-question
    max_evidence: int = 14
    max_passage_chars: int = 1500


@dataclass
class AgentDeps:
    llm: ChatLLM
    retriever: Retriever
    catalog: dict[str, list[int]] = field(default_factory=dict)  # ticker -> fiscal years
    config: AgentConfig = field(default_factory=AgentConfig)
    company_names: dict[str, str] = field(default_factory=dict)  # ticker -> full name
