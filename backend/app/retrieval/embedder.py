from typing import Protocol

from app.core.config import Settings, get_settings
from app.retrieval.schemas import SparseVector


class Embedder(Protocol):
    dim: int

    def embed_documents(
        self, texts: list[str], sparse_texts: list[str] | None = None
    ) -> tuple[list[list[float]], list[SparseVector]]: ...

    def embed_query(
        self, text: str, sparse_text: str | None = None
    ) -> tuple[list[float], SparseVector]: ...


class FastEmbedder:
    """Local dense (bge) + sparse (BM25) embeddings via fastembed (ONNX, no GPU/torch needed)."""

    def __init__(self, settings: Settings | None = None):
        from fastembed import SparseTextEmbedding, TextEmbedding

        s = settings or get_settings()
        self._dense = TextEmbedding(s.dense_model, cache_dir=s.embedding_cache_dir)
        self._sparse = SparseTextEmbedding(s.sparse_model, cache_dir=s.embedding_cache_dir)
        self.dim = len(next(iter(self._dense.embed(["dim probe"]))))

    @staticmethod
    def _sv(e) -> SparseVector:
        return SparseVector(e.indices.tolist(), e.values.tolist())

    def embed_documents(
        self, texts: list[str], sparse_texts: list[str] | None = None
    ) -> tuple[list[list[float]], list[SparseVector]]:
        """`sparse_texts` lets the keyword index see a different (normalised) text than the dense model."""
        dense = [v.tolist() for v in self._dense.embed(texts)]
        sparse = [self._sv(e) for e in self._sparse.embed(sparse_texts or texts)]
        return dense, sparse

    def embed_query(
        self, text: str, sparse_text: str | None = None
    ) -> tuple[list[float], SparseVector]:
        dense = next(iter(self._dense.query_embed(text))).tolist()
        sparse = self._sv(next(iter(self._sparse.query_embed(sparse_text or text))))
        return dense, sparse
