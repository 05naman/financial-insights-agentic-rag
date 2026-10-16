import functools
import re
import threading
import warnings
from dataclasses import dataclass

from qdrant_client import QdrantClient, models

from app.core.config import Settings, get_settings
from app.ingestion.schemas import Chunk
from app.retrieval.schemas import SearchFilters, SearchHit, SparseVector

DENSE = "dense"
SPARSE = "sparse"


def make_client(settings: Settings | None = None) -> QdrantClient:
    s = settings or get_settings()
    if s.qdrant_url == ":memory:":
        return QdrantClient(":memory:")
    if s.qdrant_url:
        return QdrantClient(url=s.qdrant_url)
    return QdrantClient(path=s.qdrant_path)


def _locked(fn):
    """Serialise access: the embedded Qdrant client is not safe for concurrent search and write."""

    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper


def _filter(f: SearchFilters | None) -> models.Filter | None:
    if not f:
        return None
    must: list[models.Condition] = []
    if f.tickers:
        must.append(
            models.FieldCondition(
                key="ticker", match=models.MatchAny(any=[t.upper() for t in f.tickers])
            )
        )
    if f.fiscal_years:
        must.append(
            models.FieldCondition(key="fiscal_year", match=models.MatchAny(any=f.fiscal_years))
        )
    return models.Filter(must=must) if must else None


@dataclass
class CorpusStats:
    words: set[str]
    years_by_ticker: dict[str, set[int]]


class VectorStore:
    def __init__(self, client: QdrantClient, collection: str, dim: int):
        self.client = client
        self.collection = collection
        self.dim = dim
        self._lock = (
            threading.RLock()
        )  # embedded Qdrant is not safe for concurrent search and write
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self.client.collection_exists(self.collection):
            return
        self.client.create_collection(
            self.collection,
            vectors_config={
                DENSE: models.VectorParams(size=self.dim, distance=models.Distance.COSINE)
            },
            sparse_vectors_config={SPARSE: models.SparseVectorParams(modifier=models.Modifier.IDF)},
        )
        for key, schema in (
            ("ticker", "keyword"),
            ("fiscal_year", "integer"),
            ("document_id", "integer"),
        ):
            with warnings.catch_warnings():  # no-op warning in embedded local mode
                warnings.simplefilter("ignore")
                self.client.create_payload_index(self.collection, key, schema)

    @_locked
    def upsert(
        self, chunks: list[Chunk], dense: list[list[float]], sparse: list[SparseVector]
    ) -> None:
        points = [
            models.PointStruct(
                id=c.id,
                vector={DENSE: d, SPARSE: models.SparseVector(indices=s.indices, values=s.values)},
                payload=c.payload,
            )
            for c, d, s in zip(chunks, dense, sparse, strict=True)
        ]
        for i in range(0, len(points), 128):
            self.client.upsert(self.collection, points[i : i + 128])

    @_locked
    def search(
        self,
        dense: list[float],
        sparse: SparseVector | None = None,
        *,
        limit: int = 10,
        filters: SearchFilters | None = None,
    ) -> list[SearchHit]:
        """Dense-only when `sparse` is None, otherwise hybrid (dense + BM25) fused with RRF."""
        flt = _filter(filters)
        if sparse is None:
            res = self.client.query_points(
                self.collection,
                query=dense,
                using=DENSE,
                limit=limit,
                query_filter=flt,
                with_payload=True,
            )
        else:
            res = self.client.query_points(
                self.collection,
                prefetch=[
                    models.Prefetch(query=dense, using=DENSE, limit=limit * 3, filter=flt),
                    models.Prefetch(
                        query=models.SparseVector(indices=sparse.indices, values=sparse.values),
                        using=SPARSE,
                        limit=limit * 3,
                        filter=flt,
                    ),
                ],
                query=models.FusionQuery(fusion=models.Fusion.RRF),
                limit=limit,
                with_payload=True,
            )
        return [
            SearchHit(
                id=str(p.id),
                score=p.score,
                text=p.payload["text"],
                ticker=p.payload["ticker"],
                fiscal_year=p.payload["fiscal_year"],
                page=p.payload["page"],
                chunk_type=p.payload["chunk_type"],
                kind=p.payload.get("section_kind", "other"),
            )
            for p in res.points
        ]

    @_locked
    def delete_document(self, document_id: int) -> None:
        self.client.delete(
            self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )

    @_locked
    def backfill_kinds(self) -> int:
        """Tag passages that were indexed before `section_kind` existed. Payload only: no re-embedding."""
        from app.ingestion.classify import classify_chunk

        changed, offset = 0, None
        while True:
            points, offset = self.client.scroll(
                self.collection, limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            for p in points:
                kind = classify_chunk(p.payload["text"], p.payload["chunk_type"])
                if p.payload.get("section_kind") != kind:
                    self.client.set_payload(self.collection, {"section_kind": kind}, points=[p.id])
                    changed += 1
            if offset is None:
                break
        return changed

    @_locked
    def corpus_stats(self) -> CorpusStats:
        """Every word and every company/year in the index (feeds typo correction and filter detection)."""
        words: set[str] = set()
        years: dict[str, set[int]] = {}
        offset = None
        while True:
            points, offset = self.client.scroll(
                self.collection, limit=256, offset=offset, with_payload=True, with_vectors=False
            )
            for p in points:
                words.update(w.lower() for w in re.findall(r"[A-Za-z]{3,}", p.payload["text"]))
                years.setdefault(p.payload["ticker"], set()).add(p.payload["fiscal_year"])
            if offset is None:
                break
        return CorpusStats(words, years)

    @_locked
    def count(self) -> int:
        return self.client.count(self.collection).count
