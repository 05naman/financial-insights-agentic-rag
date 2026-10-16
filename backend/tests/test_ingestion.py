import pytest

from app.db.models import DocumentStatus
from app.db.repositories import DocumentRepository
from app.db.session import get_sessionmaker, init_db, reset_engine
from app.ingestion.chunker import chunk_pages
from app.ingestion.filename import InvalidFilenameError, parse_report_filename
from app.ingestion.pdf_loader import load_pdf
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.schemas import PageContent
from app.retrieval.retriever import Retriever
from app.retrieval.schemas import SearchFilters


@pytest.fixture
async def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    from app.core.config import get_settings

    get_settings.cache_clear()
    reset_engine()
    await init_db()
    async with get_sessionmaker()() as session:
        yield DocumentRepository(session)
    reset_engine()
    get_settings.cache_clear()


def test_filename_parsing():
    n = parse_report_filename("tcs_FY2024.pdf")
    assert (n.ticker, n.fiscal_year) == ("TCS", 2024)
    with pytest.raises(InvalidFilenameError):
        parse_report_filename("annual-report.pdf")


def test_chunker_keeps_tables_whole_with_context_and_tracks_pages():
    table = "|Year|Revenue|\n|---|---|\n|FY23|100|\n|FY24|120|"
    page2 = f"## Financial Summary\n\n(Rs in Crores)\n\n{table}"
    pages = [
        PageContent(
            1, "Paragraph one is long enough to keep.\n\nParagraph two is also long enough."
        ),
        PageContent(2, page2),
    ]
    chunks = chunk_pages(pages, document_id=1, ticker="TCS", fiscal_year=2024)
    assert {c.page for c in chunks} == {1, 2}
    tables = [c for c in chunks if c.chunk_type == "table"]
    assert len(tables) == 1 and table in tables[0].text
    assert "Financial Summary" in tables[0].text and "Rs in Crores" in tables[0].text
    assert len({c.id for c in chunks}) == len(chunks)


def test_chunker_splits_long_text():
    text = "\n\n".join(f"Sentence number {i} about revenue growth." * 5 for i in range(40))
    chunks = chunk_pages(
        [PageContent(1, text)],
        document_id=1,
        ticker="X",
        fiscal_year=2024,
        chunk_size=500,
        chunk_overlap=50,
    )
    assert len(chunks) > 3
    assert all(len(c.text) <= 600 for c in chunks)


def test_big_table_splits_with_repeated_header():
    rows = "\n".join(f"|Row {i}|{i * 100}|" for i in range(600))
    table = f"|Name|Value|\n|---|---|\n{rows}"
    chunks = chunk_pages([PageContent(1, table)], document_id=1, ticker="X", fiscal_year=2024)
    assert len(chunks) > 1
    assert all(c.text.startswith("|Name|Value|") for c in chunks)


def test_strip_boilerplate_removes_running_headers_only():
    from app.ingestion.pdf_loader import strip_boilerplate

    pages = [
        PageContent(i, f"Acme Ltd Annual Report\n\nReal content {i}.\n\n|a|b|")
        for i in range(1, 11)
    ]
    cleaned = strip_boilerplate(pages)
    assert all("Acme Ltd" not in p.text for p in cleaned)
    assert all("Real content" in p.text and "|a|b|" in p.text for p in cleaned)


def test_pdf_loader_reads_pages(sample_pdf_dir):
    pages = load_pdf(sample_pdf_dir / "TCS_FY2024.pdf")
    assert len(pages) == 2
    assert "Revenue from operations" in pages[0].text


async def test_pipeline_ingests_and_search_filters(repo, embedder, store, sample_pdf_dir):
    pipeline = IngestionPipeline(repo, embedder, store)
    docs = await pipeline.ingest_dir(sample_pdf_dir)
    assert {d.ticker for d in docs} == {"TCS", "INFY"}
    assert all(d.status == DocumentStatus.ready for d in docs)
    assert store.count() > 0

    retriever = Retriever(embedder, store, reranker=None)
    hits = retriever.search("revenue from operations", filters=SearchFilters(tickers=["TCS"]))
    assert hits and all(h.ticker == "TCS" for h in hits)
    assert hits[0].page == 1

    hits = retriever.search(
        "operating margin", hybrid=False, filters=SearchFilters(tickers=["INFY"])
    )
    assert hits[0].ticker == "INFY"


async def test_reingest_is_idempotent(repo, embedder, store, sample_pdf_dir):
    pipeline = IngestionPipeline(repo, embedder, store)
    await pipeline.ingest_dir(sample_pdf_dir)
    n = store.count()
    await pipeline.ingest_dir(sample_pdf_dir)
    assert store.count() == n
    await pipeline.ingest_file(sample_pdf_dir / "TCS_FY2024.pdf", replace=True)
    assert store.count() == n


async def test_failed_ingestion_marks_document_failed(repo, embedder, store, tmp_path):
    bad = tmp_path / "BAD_FY2024.pdf"
    bad.write_bytes(b"not a pdf")
    doc = await IngestionPipeline(repo, embedder, store).ingest_file(bad)
    assert doc.status == DocumentStatus.failed and doc.error


def test_spaced_numbers_in_table_cells_are_repaired():
    from app.ingestion.pdf_loader import repair_spaced_numbers

    md = (
        "|**TOTAL IN COME**||**2, 7 1, 423**|**2, 59, 286**|\n"
        "|Revenue|12|2,67,021|(355)|\n"
        "|**PROFIT**||**48, 7 97**|( 376)|\n"
        "|Years||2025 2026|7 0, 013|"
    )
    out = repair_spaced_numbers(md)
    assert "**2,71,423**" in out and "**2,59,286**" in out and "**48,797**" in out
    assert "|2,67,021|(355)|" in out  # already fine: untouched
    assert "(376)" in out
    assert "|2025 2026|" in out  # two separate numbers must not be glued together
    assert "|70,013|" in out


def test_number_repair_leaves_prose_and_dates_alone():
    from app.ingestion.pdf_loader import repair_spaced_numbers

    text = "For the year ended March 31, 2026, revenue was 2, 7 1, 423 crore.\n\n|a|b|\n|---|---|\n|x|1|"
    assert repair_spaced_numbers(text) == text  # outside table cells nothing changes


def test_markdown_artifacts_are_repaired():
    from app.ingestion.pdf_loader import repair_markdown_artifacts
    from app.ingestion.schemas import PageContent

    body = "The year ended and the year before. " * 4  # makes 'year' a known word of this document
    pages = [
        PageContent(1, body + "|**Y **|(`H`crores)<br>**Y **|\n|**Y ear ended**|**N ote**|"),
        PageContent(2, body + "Note 12 is about notes. A note. Notes notes."),
    ]
    out = repair_markdown_artifacts(pages)[0].text
    assert "**Y **" not in out and "**Y** " in out  # spaces moved outside the markers
    assert "(₹ crores)" in out and "`H`" not in out
    assert (
        "Year ended" in out and "N ote" in out or "Note" in out
    )  # 'Y ear' rejoined (vocabulary-backed)
    assert "Y ear" not in out


def test_repair_does_not_glue_real_words_or_touch_normal_text():
    from app.ingestion.pdf_loader import repair_markdown_artifacts
    from app.ingestion.schemas import PageContent

    text = "A bank. I am here. The group H1 results were fine. Plan B was used. H. Singh joined."
    out = repair_markdown_artifacts([PageContent(1, text * 5)])[0].text
    assert out == text * 5  # 'A bank', 'I am', 'H1', 'B was', 'H. Singh' are untouched
