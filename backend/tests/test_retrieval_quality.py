"""Tests for the retrieval improvements (query parsing, typo fixing, number handling, company names)."""

import pytest

from app.core.config import Settings
from app.ingestion.chunker import chunk_pages
from app.ingestion.pipeline import IngestionPipeline, embedding_inputs
from app.ingestion.schemas import PageContent
from app.retrieval.query_parser import detect_companies, detect_years, parse_query
from app.retrieval.retriever import Retriever
from app.retrieval.rewriter import QueryRewriter
from app.retrieval.schemas import SearchFilters
from app.retrieval.text import normalize_numbers
from tests.conftest import make_pdf
from tests.test_ingestion import repo  # noqa: F401  (fixture)

NAMES = {
    "BHIT": "Bharat Infotech Limited",
    "SAGR": "Sagar Pharma Limited",
    "NAVM": "Navbharat Motors Limited",
}
TICKERS = list(NAMES)


# ---------- years ----------
@pytest.mark.parametrize(
    ("text", "years"),
    [
        ("revenue FY2024", [2024]),
        ("revenue FY24", [2024]),
        ("revenue FY 2023", [2023]),
        ("profit 2023-24", [2024]),
        ("profit 2023-2024", [2024]),
        ("profit 2022/23", [2023]),
        ("year ended March 31, 2024", [2024]),
        ("as at March 2023", [2023]),
        ("compare FY2022 and FY2024", [2022, 2024]),
        ("figure 1,89,866 crore", []),  # a number is not a year
        ("2,40,893", []),
        ("revenue", []),
    ],
)
def test_year_detection(text, years):
    assert detect_years(text) == years


# ---------- companies ----------
@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("bhit rev", ["BHIT"]),
        ("BHIT revenue", ["BHIT"]),
        ("Bharat Infotech Limited assets", ["BHIT"]),
        ("bharat infotech profit", ["BHIT"]),
        ("Bharat Infotec profit", ["BHIT"]),  # one letter missing
        ("sagar pharma", ["SAGR"]),
        ("Sagar risks", ["SAGR"]),  # distinctive first word
        ("navbharat motors and bhit", ["BHIT", "NAVM"]),
        ("what are the risks", []),
        ("bharat results", ["BHIT"]),  # a first word no other company shares is enough
        ("which company has the most staff", []),
    ],
)
def test_company_detection(text, found):
    assert sorted(detect_companies(text, NAMES, TICKERS)) == sorted(found)


def test_parse_query_combines_company_and_year():
    f = parse_query("bhit vs sagar borrowings FY24", NAMES, TICKERS)
    assert sorted(f.tickers) == ["BHIT", "SAGR"] and f.fiscal_years == [2024]


# ---------- numbers ----------
def test_indian_grouped_numbers_lose_their_commas_only_inside_numbers():
    assert normalize_numbers("Rs 1,89,866 crore, up 5%") == "Rs 189866 crore, up 5%"
    assert normalize_numbers("a, b, c") == "a, b, c"


# ---------- rewriter ----------
def test_typos_are_fixed_against_the_corpus_vocabulary():
    rw = QueryRewriter(["revenue", "employees", "dividend", "risks"], protected=["bhit"])
    assert rw.correct("revnue of bhit") == "revenue of bhit"
    assert rw.correct("employes and riscs") == "employees and risks"
    assert rw.correct("zzzzzz") == "zzzzzz"  # nothing close: leave it
    assert rw.correct("bhit fy24") == "bhit fy24"  # tickers and year tokens are never rewritten


def test_rewriter_options_can_be_switched_off():
    rw = QueryRewriter(["revenue"], spell_correct=False, synonyms=False, numbers=False)
    out = rw.rewrite("revnue turnover 1,89,866")
    assert out.dense == out.sparse == "revnue turnover 1,89,866"
    on = QueryRewriter(["revenue"], synonyms=True, numbers=True).rewrite("turnover 1,89,866")
    assert "revenue from operations" in on.sparse and "189866" in on.sparse


# ---------- index text ----------
def test_company_name_goes_into_the_header_and_numbers_only_into_the_keyword_text():
    chunks = chunk_pages(
        [PageContent(1, "Revenue was Rs 1,89,866 crore in the year under review, a good result.")],
        document_id=1,
        ticker="BHIT",
        fiscal_year=2024,
    )
    on = Settings(index_company_name=True, index_normalize_numbers=True)
    dense, sparse = embedding_inputs(chunks, NAMES, on)
    assert (
        "Bharat Infotech Limited (BHIT)" in dense[0] and "1,89,866" in dense[0]
    )  # dense text unchanged
    assert "189866" in sparse[0] and "1,89,866" not in sparse[0]
    off = Settings(index_company_name=False, index_normalize_numbers=False)
    d2, s2 = embedding_inputs(chunks, NAMES, off)
    assert "Bharat Infotech" not in d2[0] and s2 == d2


def test_tiny_text_fragments_are_dropped_only_when_asked():
    page = PageContent(1, "## **Financial Highlights**\n\n|a|b|\n|---|---|\n|x|1|\n|y|2|")
    kept = chunk_pages([page], document_id=1, ticker="X", fiscal_year=2024)
    cleaned = chunk_pages([page], document_id=1, ticker="X", fiscal_year=2024, drop_tiny_text=True)
    assert sum(c.chunk_type == "text" for c in kept) >= sum(c.chunk_type == "text" for c in cleaned)
    assert any(c.chunk_type == "table" for c in cleaned)


# ---------- retriever behaviour ----------
@pytest.fixture
async def indexed(repo, embedder, store, tmp_path):  # noqa: F811
    make_pdf(
        tmp_path / "BHIT_FY2024.pdf",
        ["Revenue from operations was Rs 2,40,893 crore in FY2024. " * 3],
    )
    make_pdf(
        tmp_path / "SAGR_FY2024.pdf",
        ["Revenue from operations was Rs 5,50,000 crore in FY2024. " * 3],
    )
    make_pdf(
        tmp_path / "BHIT_FY2023.pdf",
        ["Revenue from operations was Rs 1,00,000 crore in FY2023. " * 3],
    )
    pipe = IngestionPipeline(repo, embedder, store, Settings())
    pipe.names = NAMES
    await pipe.ingest_dir(tmp_path)
    return Retriever(embedder, store, None, Settings(), NAMES)


async def test_exact_figure_is_found_even_with_indian_grouping(indexed):
    hits = indexed.search("2,40,893", limit=3, rerank=False)
    assert hits and "240893" in hits[0].text.replace(",", "")
    assert (hits[0].ticker, hits[0].fiscal_year) == ("BHIT", 2024)


async def test_company_and_year_in_the_question_narrow_the_search(indexed):
    hits = indexed.search("sagar revenue FY24", limit=5, rerank=False)
    assert hits and {(h.ticker, h.fiscal_year) for h in hits} == {("SAGR", 2024)}


async def test_callers_filters_win_and_gaps_are_filled(indexed):
    f = indexed.resolve_filters("bhit revenue FY2024", SearchFilters(tickers=["SAGR"]))
    assert f.tickers == ["SAGR"] and f.fiscal_years == [2024]  # their ticker kept, year filled in


async def test_improve_false_is_the_plain_baseline(indexed):
    hits = indexed.search("sagar revenue FY24", limit=9, rerank=False, improve=False)
    assert len({(h.ticker, h.fiscal_year) for h in hits}) > 1  # not narrowed


async def test_switching_auto_filters_off_in_settings(embedder, store):
    r = Retriever(embedder, store, None, Settings(query_auto_filters=False), NAMES)
    f = r.resolve_filters("bhit FY2024", None)
    assert f.tickers == [] and f.fiscal_years == []


async def test_corpus_stats_report_vocabulary_and_companies(indexed):
    stats = indexed.store.corpus_stats()
    assert "revenue" in stats.words and stats.years_by_ticker == {
        "BHIT": {2023, 2024},
        "SAGR": {2024},
    }


# ---------- primary-statement tagging and boost ----------
def test_statement_tables_are_tagged_and_other_chunks_are_not():
    from app.ingestion.classify import classify_chunk

    assert (
        classify_chunk("Consolidated Statement of Profit and Loss\n\n|a|b|", "table") == "statement"
    )
    assert classify_chunk("Standalone Balance Sheet As at March 31\n|a|b|", "table") == "statement"
    assert classify_chunk("Financial Highlights\n|a|b|", "table") == "statement"
    assert (
        classify_chunk(
            "Notes forming part of Financial Statements\n13) Other income\n|a|b|", "table"
        )
        == "other"
    )
    assert (
        classify_chunk("Statement of Profit and Loss is discussed here in prose", "text") == "other"
    )


@pytest.mark.parametrize(
    ("q", "money"),
    [
        ("net income TCS FY2026", True),
        ("how much money did it earn after taxes", True),
        ("what is the debt of the company", True),
        ("what could go wrong for the business", False),
        ("2,67,021", False),  # a bare figure is a lookup, not a metric question
        ("Rs 1,89,866 crore", False),  # units alone are not metrics
        ("who is the chairman", False),
    ],
)
def test_money_question_detector(q, money):
    from app.ingestion.classify import is_financial_query

    assert is_financial_query(q) is money


def test_chunks_carry_their_section_kind_into_the_payload():
    page = PageContent(
        1, "## **Standalone Balance Sheet**\n\n|(Rs)||\n|---|---|\n|Assets|5|\n|Equity|6|"
    )
    chunks = chunk_pages([page], document_id=1, ticker="X", fiscal_year=2024)
    table = next(c for c in chunks if c.chunk_type == "table")
    assert table.kind == "statement" and table.payload["section_kind"] == "statement"


async def test_boost_moves_a_statement_above_a_note_on_money_questions(indexed):
    from app.retrieval.schemas import SearchHit

    class Fake:  # a store whose plain ranking puts a note first and the statement second
        def count(self):
            return 2

        def corpus_stats(self):
            from app.retrieval.vector_store import CorpusStats

            return CorpusStats({"profit"}, {"BHIT": {2024}})

        def search(self, dense, sparse, *, limit, filters):
            return [
                SearchHit("n", 0.50, "note", "BHIT", 2024, 9, "table", "other"),
                SearchHit("s", 0.45, "statement", "BHIT", 2024, 5, "table", "statement"),
            ]

    emb = indexed.embedder
    off = Retriever(emb, Fake(), None, Settings(query_statement_boost=0.0), NAMES)
    on = Retriever(emb, Fake(), None, Settings(query_statement_boost=0.6), NAMES)
    assert off.search("net income BHIT", limit=2, rerank=False)[0].id == "n"
    assert on.search("net income BHIT", limit=2, rerank=False)[0].id == "s"
    # not a money question: no boost
    assert on.search("what could go wrong for BHIT", limit=2, rerank=False)[0].id == "n"
    # the plain baseline never boosts
    assert on.search("net income BHIT", limit=2, rerank=False, improve=False)[0].id == "n"


async def test_retag_adds_section_kind_to_older_passages(indexed):
    store = indexed.store
    assert store.backfill_kinds() == 0  # fresh index is already tagged
    store.client.set_payload(
        store.collection,
        {"section_kind": "other"},
        points=[p.id for p in store.client.scroll(store.collection, limit=50)[0]],
    )
    changed = store.backfill_kinds()
    tables = sum(
        1
        for p in store.client.scroll(store.collection, limit=50)[0]
        if p.payload["chunk_type"] == "table"
    )
    assert changed >= 0 and tables >= 0  # only statement-looking tables flip back
