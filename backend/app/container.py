"""Wires concrete components together. Heavy objects (models, vector client) are built lazily once."""

from functools import lru_cache

from app.agent.deps import AgentConfig, AgentDeps
from app.core.companies import load_company_names
from app.core.config import Settings, get_settings
from app.llm.factory import FallbackLLM, get_llm
from app.retrieval.embedder import Embedder, FastEmbedder
from app.retrieval.reranker import CrossEncoderReranker, Reranker
from app.retrieval.retriever import Retriever
from app.retrieval.vector_store import VectorStore, make_client
from app.services.qa import QAService


class Container:
    def __init__(
        self,
        settings: Settings,
        embedder: Embedder | None = None,
        use_reranker: bool = True,
        llm: FallbackLLM | None = None,
    ):
        self.settings = settings
        self.embedder = embedder or FastEmbedder(settings)
        self.reranker: Reranker | None = CrossEncoderReranker(settings) if use_reranker else None
        self.store = VectorStore(
            make_client(settings), settings.qdrant_collection, self.embedder.dim
        )
        self.retriever = Retriever(
            self.embedder, self.store, self.reranker, settings, self.company_names()
        )
        self.llm = llm or get_llm(settings)

    def company_names(self) -> dict[str, str]:
        return load_company_names(self.settings)

    def qa_service(self, catalog: dict[str, list[int]]) -> QAService:
        s = self.settings
        config = AgentConfig(
            top_k=s.agent_top_k,
            max_evidence=s.agent_max_evidence,
            max_passage_chars=s.agent_passage_chars,
        )
        deps = AgentDeps(
            self.llm, self.retriever, catalog, config=config, company_names=self.company_names()
        )
        return QAService(self.llm, self.retriever, deps)


@lru_cache
def get_container() -> Container:
    return Container(get_settings())
