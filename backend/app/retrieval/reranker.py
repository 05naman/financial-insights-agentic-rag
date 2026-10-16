from dataclasses import replace
from typing import Protocol

from app.core.config import Settings, get_settings
from app.retrieval.schemas import SearchHit


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]: ...


class CrossEncoderReranker:
    """Re-scores hits with a local cross-encoder (fastembed), keeping the best top_k."""

    def __init__(self, settings: Settings | None = None):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        s = settings or get_settings()
        self._model = TextCrossEncoder(s.reranker_model, cache_dir=s.embedding_cache_dir)

    def rerank(self, query: str, hits: list[SearchHit], top_k: int) -> list[SearchHit]:
        if not hits:
            return []
        scores = list(self._model.rerank(query, [h.text for h in hits]))
        ranked = sorted(zip(hits, scores, strict=True), key=lambda x: x[1], reverse=True)
        return [replace(h, score=float(s)) for h, s in ranked[:top_k]]
