import asyncio
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from app.core.companies import load_company_names
from app.core.config import Settings, get_settings
from app.db.models import Document, DocumentStatus
from app.db.repositories import DocumentRepository
from app.ingestion.chunker import chunk_pages
from app.ingestion.filename import parse_report_filename
from app.ingestion.pdf_loader import load_pdf
from app.ingestion.schemas import Chunk, PageContent
from app.retrieval.embedder import Embedder
from app.retrieval.schemas import SparseVector
from app.retrieval.text import normalize_numbers
from app.retrieval.vector_store import VectorStore

logger = logging.getLogger(__name__)
EMBED_BATCH = 32
SAFE_INGEST_ERROR = "Could not read this PDF. It may be corrupted, password-protected or scanned."
SAFE_REUPLOAD_ERROR = "The newer upload could not be read, so the previous version is still in use."


class IngestError(Exception):
    """A failure whose message is safe to show to users."""


def embedding_text(c: Chunk, company_name: str | None = None) -> str:
    """Prefix each chunk with where it comes from so company/year terms help retrieval."""
    who = f"{company_name} ({c.ticker})" if company_name else c.ticker
    return f"{who} FY{c.fiscal_year} annual report, page {c.page} ({c.chunk_type})\n{c.text}"


def embedding_inputs(
    chunks: list[Chunk], names: dict[str, str], settings: Settings
) -> tuple[list[str], list[str]]:
    """The text each chunk is embedded as: one for the dense model, one for the keyword (BM25) index."""
    dense = [
        embedding_text(c, names.get(c.ticker) if settings.index_company_name else None)
        for c in chunks
    ]
    sparse = [normalize_numbers(t) for t in dense] if settings.index_normalize_numbers else dense
    return dense, sparse


@dataclass
class Prepared:
    pages: list[PageContent]
    dense: list[list[float]]
    sparse: list[SparseVector]


class IngestionPipeline:
    """PDF -> pages -> chunks -> vectors.

    All CPU-heavy work runs in worker threads (the API stays responsive) and happens BEFORE any
    existing data is touched, so a bad re-upload can never destroy a report that already works."""

    def __init__(
        self,
        repo: DocumentRepository,
        embedder: Embedder,
        store: VectorStore,
        settings: Settings | None = None,
    ):
        self.repo = repo
        self.embedder = embedder
        self.store = store
        self.settings = settings or get_settings()
        self.names = load_company_names(self.settings)

    # ---- heavy, blocking work (runs in a thread) ----
    def _prepare(self, source: Path, ticker: str, fiscal_year: int) -> Prepared:
        pages = load_pdf(source, boilerplate_share=self.settings.index_boilerplate_share)
        if len(pages) > self.settings.max_pdf_pages:
            raise IngestError(f"This report has more than {self.settings.max_pdf_pages} pages.")
        chunks = self._chunks(pages, 0, ticker, fiscal_year)
        if not chunks:
            raise IngestError("No readable text was found. The PDF may be scanned images.")
        dense_texts, sparse_texts = embedding_inputs(chunks, self.names, self.settings)
        dense: list[list[float]] = []
        sparse: list[SparseVector] = []
        for i in range(0, len(chunks), EMBED_BATCH):
            d, s = self.embedder.embed_documents(
                dense_texts[i : i + EMBED_BATCH], sparse_texts[i : i + EMBED_BATCH]
            )
            dense += d
            sparse += s
        return Prepared(pages, dense, sparse)

    def _chunks(
        self, pages: list[PageContent], document_id: int, ticker: str, year: int
    ) -> list[Chunk]:
        return chunk_pages(
            pages,
            document_id=document_id,
            ticker=ticker,
            fiscal_year=year,
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
            drop_tiny_text=self.settings.index_drop_tiny_chunks,
        )

    def _store(self, chunks: list[Chunk], prepared: Prepared) -> None:
        self.store.upsert(chunks, prepared.dense, prepared.sparse)

    # ---- orchestration ----
    async def ingest_file(
        self, path: str | Path, *, replace: bool = False, final_path: str | Path | None = None
    ) -> Document:
        """Read `path`. On success the file is kept as `final_path` (default: where it already is)."""
        source = Path(path)
        final = Path(final_path) if final_path else source
        name = parse_report_filename(final.name)
        existing = await self.repo.get_by_company_year(name.ticker, name.fiscal_year)

        if existing and existing.status == DocumentStatus.ready and not replace:
            logger.info("skip %s (already ingested)", final.name)
            return existing

        # a row made at upload time (pending) belongs to this run; otherwise a ready/failed row is
        # only replaced after the new data is fully prepared
        claimed = (
            existing
            if existing and existing.status in (DocumentStatus.pending, DocumentStatus.processing)
            else None
        )
        replacing = existing if existing and claimed is None else None
        doc = claimed or (
            None if replacing else await self.repo.create(name.ticker, name.fiscal_year, final.name)
        )
        if doc:
            await self.repo.set_status(doc, DocumentStatus.processing)

        try:
            prepared = await asyncio.to_thread(self._prepare, source, name.ticker, name.fiscal_year)
        except Exception as e:
            safe = str(e) if isinstance(e, IngestError) else SAFE_INGEST_ERROR
            if isinstance(e, IngestError):
                logger.warning("ingestion rejected %s: %s", final.name, e)
            else:
                logger.exception(
                    "ingestion failed for %s", final.name
                )  # full detail stays in the log
            return await self._fail(doc, replacing, safe)

        try:
            if replacing:  # swap only now that everything is ready
                await asyncio.to_thread(self.store.delete_document, replacing.id)
                await self.repo.delete(replacing)
                doc = await self.repo.create(name.ticker, name.fiscal_year, final.name)
            assert doc is not None
            chunks = self._chunks(prepared.pages, doc.id, name.ticker, name.fiscal_year)
            await asyncio.to_thread(self._store, chunks, prepared)
            if source != final:
                os.replace(source, final)
            logger.info(
                "ingested %s FY%s: %d pages, %d chunks",
                doc.ticker,
                doc.fiscal_year,
                len(prepared.pages),
                len(chunks),
            )
            return await self.repo.set_status(
                doc, DocumentStatus.ready, page_count=len(prepared.pages), chunk_count=len(chunks)
            )
        except Exception:
            logger.exception("storing %s failed", final.name)
            if doc:
                await asyncio.to_thread(self.store.delete_document, doc.id)
            return await self._fail(doc, None, SAFE_INGEST_ERROR)

    async def _fail(self, doc: Document | None, kept: Document | None, message: str) -> Document:
        """Record a failure without losing anything that was already working."""
        if doc is not None:  # a brand-new (or upload-time) row: nothing worth keeping
            fresh = await self.repo.get(doc.id)  # it may have been removed meanwhile
            if fresh is None:
                return doc
            await asyncio.to_thread(self.store.delete_document, doc.id)
            return await self.repo.set_status(fresh, DocumentStatus.failed, error=message)
        assert kept is not None
        # re-upload of a report that exists: keep serving the old one, just note the problem
        kept.error = SAFE_REUPLOAD_ERROR if kept.status == DocumentStatus.ready else message
        await self.repo.session.commit()
        return kept

    async def ingest_dir(
        self, directory: str | Path, *, replace: bool = False, only: str | None = None
    ) -> list[Document]:
        results = []
        for pdf in sorted(Path(directory).glob("*.pdf")):
            if only and only not in pdf.name:
                continue
            try:
                results.append(await self.ingest_file(pdf, replace=replace))
            except ValueError as e:  # bad filename
                logger.warning("skipping %s: %s", pdf.name, e)
        return results
