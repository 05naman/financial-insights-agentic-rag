import hashlib
import math

import pymupdf
import pytest
from qdrant_client import QdrantClient

from app.retrieval.schemas import SparseVector
from app.retrieval.vector_store import VectorStore

DIM = 64


def _tokens(text: str) -> list[str]:
    return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]


def _bucket(tok: str, mod: int) -> int:
    return int(hashlib.md5(tok.encode()).hexdigest(), 16) % mod


class FakeEmbedder:
    """Deterministic bag-of-words embedder: similar words -> similar vectors. No model download."""

    dim = DIM

    def _dense(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for t in _tokens(text):
            v[_bucket(t, DIM)] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def _sparse(self, text: str) -> SparseVector:
        counts: dict[int, float] = {}
        for t in _tokens(text):
            i = _bucket(t, 10_000)
            counts[i] = counts.get(i, 0.0) + 1.0
        return SparseVector(list(counts), list(counts.values()))

    def embed_documents(self, texts, sparse_texts=None):
        sp = sparse_texts or texts
        return [self._dense(t) for t in texts], [self._sparse(t) for t in sp]

    def embed_query(self, text, sparse_text=None):
        return self._dense(text), self._sparse(sparse_text or text)


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def store(embedder):
    return VectorStore(QdrantClient(":memory:"), "test", embedder.dim)


def make_pdf(path, pages: list[str]) -> None:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 550, 780), text, fontsize=11)
    doc.save(path)
    doc.close()


@pytest.fixture
def sample_pdf_dir(tmp_path):
    make_pdf(
        tmp_path / "TCS_FY2024.pdf",
        [
            "Revenue from operations was Rs 2,40,893 crore in FY2024, up 6.8 percent.",
            "Risk factors: attrition of employees and currency fluctuation may hurt margins.",
        ],
    )
    make_pdf(
        tmp_path / "INFY_FY2024.pdf",
        ["Infosys revenue was Rs 1,53,670 crore. Operating margin stood at 20.7 percent."],
    )
    return tmp_path


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch):
    """LLM retries back off in production; tests should not actually wait."""
    import app.llm.http as http

    async def instant(_):
        return None

    monkeypatch.setattr(http, "_sleep", instant)
