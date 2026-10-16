import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from app.container import Container
from app.db.models import Document
from app.db.repositories import DocumentRepository
from app.db.session import get_sessionmaker
from app.ingestion.filename import parse_report_filename
from app.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)
_ingest_lock = asyncio.Lock()  # embedding is CPU heavy: one ingestion at a time


def save_upload_path(pdf_dir: str, filename: str) -> Path:
    """Validate the TICKER_FYyyyy.pdf name and return the final destination (no path tricks)."""
    name = parse_report_filename(Path(filename).name)
    target = Path(pdf_dir)
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{name.ticker}_FY{name.fiscal_year}.pdf"


def incoming_path(pdf_dir: str) -> Path:
    """A unique temp file per upload, so concurrent uploads of one report never share a file."""
    folder = Path(pdf_dir) / ".incoming"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid4().hex}.part"


async def ingest_in_background(container: Container, temp: Path, final: Path) -> None:
    """Runs after the upload response is sent, with its own DB session."""
    try:
        async with _ingest_lock:
            async with get_sessionmaker()() as session:
                pipeline = IngestionPipeline(
                    DocumentRepository(session),
                    container.embedder,
                    container.store,
                    container.settings,
                )
                await pipeline.ingest_file(temp, replace=True, final_path=final)
    except Exception:
        logger.exception("background ingestion crashed for %s", final.name)
    finally:
        temp.unlink(missing_ok=True)  # already moved on success


async def catalog(repo: DocumentRepository) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for d in await repo.list():
        if d.status.value == "ready":
            out.setdefault(d.ticker, []).append(d.fiscal_year)
    return out


async def delete_document(container: Container, repo: DocumentRepository, doc: Document) -> None:
    await asyncio.to_thread(container.store.delete_document, doc.id)
    pdf = Path(container.settings.pdf_dir) / f"{doc.ticker}_FY{doc.fiscal_year}.pdf"
    pdf.unlink(missing_ok=True)  # otherwise `ingest` would bring a deleted report back
    await repo.delete(doc)
