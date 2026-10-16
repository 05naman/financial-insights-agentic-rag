"""Local CLI: ingest PDFs and ask questions without running the API.

uv run python -m app.cli ingest --dir ../data/pdfs
uv run python -m app.cli ask "How did TCS revenue change?" --mode agentic
"""

import argparse
import asyncio
from collections import defaultdict

from app.container import get_container
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.models import DocumentStatus
from app.db.repositories import DocumentRepository
from app.db.session import get_sessionmaker, init_db
from app.ingestion.pipeline import IngestionPipeline


async def cmd_ingest(directory: str, replace: bool, only: str | None = None) -> None:
    c = get_container()
    await init_db()
    async with get_sessionmaker()() as session:
        pipeline = IngestionPipeline(DocumentRepository(session), c.embedder, c.store, c.settings)
        for d in await pipeline.ingest_dir(directory, replace=replace, only=only):
            print(
                f"{d.ticker} FY{d.fiscal_year}: {d.status.value} "
                f"({d.page_count} pages, {d.chunk_count} chunks) {d.error or ''}"
            )


SEARCH_MODES = {
    "dense": dict(hybrid=False, rerank=False),  # meaning-based vectors only
    "hybrid": dict(hybrid=True, rerank=False),  # + BM25 keywords, fused
    "rerank": dict(hybrid=True, rerank=True),  # + cross-encoder reranker
}


def cmd_search(
    query: str, mode: str, companies: list[str], years: list[int], limit: int, width: int
) -> None:
    """Show what the search index returns for a query. No LLM involved, so it is free and instant."""
    from app.retrieval.schemas import SearchFilters

    c = get_container()
    hits = c.retriever.search(
        query,
        limit=limit,
        filters=SearchFilters(tickers=companies, fiscal_years=years),
        **SEARCH_MODES[mode],
    )
    scope = " ".join([*companies, *[f"FY{y}" for y in years]]) or "all reports"
    print(
        f"\nquery: {query!r}   mode: {mode}   scope: {scope}   chunks in index: {c.store.count()}\n"
    )
    if not hits:
        print("  no results (is anything ingested for that company/year?)")
    for rank, h in enumerate(hits, start=1):
        text = " ".join(h.text.split())
        print(
            f"{rank:>2}. [{h.citation}] {h.chunk_type:<5} score {h.score:7.3f}\n    {text[:width]}{'…' if len(text) > width else ''}\n"
        )


async def cmd_ask(question: str, mode: str) -> None:
    await init_db()
    async with get_sessionmaker()() as session:
        catalog: dict[str, list[int]] = defaultdict(list)
        for d in await DocumentRepository(session).list():
            if d.status == DocumentStatus.ready:
                catalog[d.ticker].append(d.fiscal_year)
    result = await get_container().qa_service(dict(catalog)).answer(question, mode=mode)  # type: ignore[arg-type]
    print(result.answer)
    print(
        f"\nSources: {', '.join(f'{c.ticker} FY{c.fiscal_year} p.{c.page}' for c in result.citations)}"
    )
    print(f"LLM calls: {result.llm_calls}")


def main() -> None:
    setup_logging(get_settings().log_level)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ing = sub.add_parser("ingest")
    ing.add_argument("--dir", default=get_settings().pdf_dir)
    ing.add_argument("--replace", action="store_true")
    ing.add_argument("--only", help="only files whose name contains this text, e.g. TCS_FY2026")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ask.add_argument("--mode", default="agentic", choices=["naive", "hybrid", "agentic"])
    sub.add_parser(
        "retag", help="tag already-indexed passages with their section kind (no re-embedding)"
    )
    se = sub.add_parser("search", help="show raw search results for a query (no LLM)")
    se.add_argument("query")
    se.add_argument("--mode", default="hybrid", choices=list(SEARCH_MODES))
    se.add_argument(
        "--company", action="append", default=[], help="ticker filter; repeat for several"
    )
    se.add_argument(
        "--year",
        action="append",
        default=[],
        type=int,
        help="fiscal year filter; repeat for several",
    )
    se.add_argument("--limit", type=int, default=5)
    se.add_argument("--width", type=int, default=230, help="characters of each passage to show")
    args = ap.parse_args()
    try:
        if args.cmd == "retag":
            print(f"retagged {get_container().store.backfill_kinds()} passages")
        elif args.cmd == "search":
            cmd_search(
                args.query,
                args.mode,
                [t.upper() for t in args.company],
                args.year,
                args.limit,
                args.width,
            )
        elif args.cmd == "ingest":
            asyncio.run(cmd_ingest(args.dir, args.replace, args.only))
        else:
            asyncio.run(cmd_ask(args.question, args.mode))
    finally:
        get_container().store.client.close()  # avoids noisy errors from the embedded Qdrant at exit


if __name__ == "__main__":
    main()
