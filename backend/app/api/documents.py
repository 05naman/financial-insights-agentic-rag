import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import ContainerDep, CurrentUser, DocumentsRepoDep
from app.ingestion.filename import InvalidFilenameError, parse_report_filename
from app.schemas.documents import DocumentOut
from app.services import documents as svc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=list[DocumentOut])
async def list_documents(_: CurrentUser, repo: DocumentsRepoDep):
    return await repo.list()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, _: CurrentUser, repo: DocumentsRepoDep):
    doc = await repo.get(document_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


async def _save_pdf(file: UploadFile, tmp: Path, max_bytes: int) -> None:
    """Stream the upload to `tmp`, rejecting non-PDFs, empty files and oversize files."""
    size = 0
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                if size == 0 and not chunk.startswith(b"%PDF-"):
                    raise HTTPException(422, "That file is not a PDF.")
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        413, f"File is larger than the {max_bytes // (1024 * 1024)} MB limit."
                    )
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, "The file is empty.")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: Annotated[UploadFile, File()],
    user: CurrentUser,
    container: ContainerDep,
    repo: DocumentsRepoDep,
    background: BackgroundTasks,
):
    """Upload `TICKER_FYyyyy.pdf`. Ingestion runs in the background; poll GET /documents."""
    try:
        final = svc.save_upload_path(container.settings.pdf_dir, file.filename or "")
        name = parse_report_filename(final.name)
    except InvalidFilenameError as e:
        logger.info("upload rejected: bad filename")
        raise HTTPException(422, str(e)) from e
    busy = HTTPException(
        status.HTTP_409_CONFLICT,
        f"{name.ticker} FY{name.fiscal_year} is still being processed. Wait for it to finish.",
    )
    existing = await repo.get_by_company_year(name.ticker, name.fiscal_year)
    if existing and existing.status.value in ("pending", "processing"):
        raise busy

    tmp = svc.incoming_path(container.settings.pdf_dir)
    await _save_pdf(file, tmp, container.settings.max_upload_mb * 1024 * 1024)
    if existing is None:
        # make the row now (not later in the background) so a second upload sees it and gets a 409
        try:
            await repo.create(name.ticker, name.fiscal_year, final.name)
        except IntegrityError:
            await repo.session.rollback()
            tmp.unlink(missing_ok=True)
            raise busy from None
    logger.info("upload accepted %s by user=%s", final.name, user.id)
    background.add_task(svc.ingest_in_background, container, tmp, final)
    return {"message": "Ingestion started", "filename": final.name}


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: int, _: CurrentUser, container: ContainerDep, repo: DocumentsRepoDep
):
    doc = await repo.get(document_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    if doc.status.value in ("pending", "processing"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This report is still being processed. Try again shortly."
        )
    await svc.delete_document(container, repo, doc)
