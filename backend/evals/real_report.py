"""Test search on a REAL annual report with answer keys read from the filing (no LLM).

    uv run python -m evals.real_report --limit 5                      # 5 questions on the production index
    uv run python -m evals.real_report --limit 5 --offset 5           # the next 5
    uv run python -m evals.real_report --group typos --variants production,drop_tiny
    uv run python -m evals.real_report --build --variants drop_tiny,strip15   # one-time, slow, then tests are instant

A question counts as found when one of the top-6 passages contains the expected figure (or phrase).
The PDF itself lives in data/pdfs (git-ignored); only the questions and answer keys are in the repo.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from app.core.config import Settings
from evals.pages_cache import raw_pages
from evals.retrieval_stress import _OFF, PDFS, build_variant, contains_figure

K = 6
HERE = Path(__file__).parent / "real_reports"


def ok(text: str, expect: str) -> bool:
    return contains_figure(text, expect) if re.search(r"\d", expect) else expect in text.lower()


def first_rank(hits, expect: str) -> int | None:
    return next((i for i, h in enumerate(hits, 1) if ok(h.text, expect)), None)


def table(
    results: dict[str, list[tuple[str, int | None]]], extra: dict[str, float] | None = None
) -> str:
    names = list(results)
    groups = sorted({g for v in results.values() for g, _ in v})
    lines = ["| group | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for grp in [*groups, "ALL"]:
        row = []
        for n in names:
            rows = [x for x in results[n] if grp in (x[0], "ALL")]
            found = sum(1 for x in rows if x[1]) / len(rows)
            mrr = sum(1 / x[1] if x[1] else 0 for x in rows) / len(rows)
            row.append(f"{found:.0%} / {mrr:.2f}")
        lines.append(f"| {grp} | " + " | ".join(row) + " |")
    if extra:
        lines.append("| avg ms | " + " | ".join(f"{extra[n]:.0f}" for n in names) + " |")
    return "\n".join(lines)


def load_cases(report: str) -> tuple[list[dict], Path]:
    spec = json.loads((HERE / f"{report.lower()}.json").read_text())
    return spec["cases"], PDFS / f"{spec['report']}.pdf"


# index options to compare. "production" is the real index; the others are built once and saved on disk.
BASE_FLAGS = {k: getattr(Settings(), k) for k in _OFF} | {
    "index_boilerplate_share": Settings().index_boilerplate_share
}
VARIANTS: dict[str, dict] = {
    "current": {},
    "drop_tiny": {"index_drop_tiny_chunks": True},
    "strip15": {"index_boilerplate_share": 0.15},
    "both": {"index_drop_tiny_chunks": True, "index_boilerplate_share": 0.15},
}
BOOSTS = {
    "boost": 0.25,
    "boost_big": 0.6,
}  # extra score for primary-statement tables on money questions
INDEX_DIR = Path(__file__).resolve().parents[1] / "data" / "cache" / "indexes"


def get_retriever(name: str, report: str, embedder):
    """The retriever for a named variant. First use builds and saves its index (slow); later uses are instant."""
    if name in ("production", "plain"):
        from app.container import get_container

        return get_container().retriever
    if name in BOOSTS:  # same production index, different ranking rule: nothing to rebuild
        from app.container import get_container
        from app.retrieval.retriever import Retriever

        c = get_container()
        return Retriever(
            c.embedder,
            c.store,
            None,
            Settings(query_statement_boost=BOOSTS[name]),
            c.company_names(),
        )
    pdf = load_cases(report)[1]
    r = build_variant(
        {**BASE_FLAGS, **VARIANTS[name]},
        {pdf: raw_pages(pdf)},
        embedder,
        INDEX_DIR / f"{report}-{name}",
    )
    r.store.backfill_kinds()  # indexes built before tagging existed get their section kind (payload only)
    return r


def run(
    report: str, names: list[str], limit: int | None, group: str | None, offset: int, rerank: bool
) -> None:
    from app.retrieval.embedder import FastEmbedder

    cases, _ = load_cases(report)
    if group:
        cases = [c for c in cases if c["group"] == group]
    cases = cases[offset : offset + limit] if limit else cases[offset:]
    emb = FastEmbedder()
    arms = {}
    for n in names:
        t = time.perf_counter()
        arms[n] = get_retriever(n, report, emb)
        if time.perf_counter() - t > 5:
            print(
                f"(built the '{n}' index in {time.perf_counter() - t:.0f}s; it is saved for next time)",
                flush=True,
            )
    res: dict[str, list] = {n: [] for n in names}
    print(
        f"\n{len(cases)} questions on {report}, top-{K}: ✓#n = the right passage at rank n, ✗ = not in the top {K}\n"
    )
    for i, c in enumerate(cases, 1):
        cells = []
        for n, r in arms.items():
            hits = r.search(
                c["question"], limit=K, hybrid=True, rerank=rerank, improve=(n != "plain")
            )
            rank = first_rank(hits, c["expect"])
            res[n].append((c["group"], rank))
            cells.append(f"{n}: {f'✓#{rank}' if rank else '✗'}")
        print(
            f"{i:>2}/{len(cases)} [{c['group']}] {c['question'][:70]}\n      " + "   ".join(cells),
            flush=True,
        )
    print("\nFound in top-6 / MRR\n")
    print(table(res))
    if any(n in ("production", "plain") or n in BOOSTS for n in arms):
        from app.container import get_container

        get_container().store.client.close()


def build_only(report: str, names: list[str]) -> None:
    from app.retrieval.embedder import FastEmbedder

    emb = FastEmbedder()
    for n in names:
        t = time.perf_counter()
        get_retriever(n, report, emb)
        print(f"built '{n}' in {time.perf_counter() - t:.0f}s", flush=True)


def main() -> None:
    sys.setrecursionlimit(5000)
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--report", default="tcs_fy2026")
    ap.add_argument(
        "--variants",
        default="production",
        help="comma list from: plain,production," + ",".join([*BOOSTS, *VARIANTS]),
    )
    ap.add_argument("--limit", type=int, help="run only N questions (a small batch)")
    ap.add_argument(
        "--offset", type=int, default=0, help="skip the first N questions (to continue a batch)"
    )
    ap.add_argument(
        "--group", help="one group: literal, synonyms, typos, exact_figures, chatty, held_out"
    )
    ap.add_argument("--rerank", action="store_true")
    ap.add_argument(
        "--build", action="store_true", help="only build and save the variant indexes (slow, once)"
    )
    a = ap.parse_args()
    names = [v.strip() for v in a.variants.split(",")]
    if a.build:
        build_only(a.report, [n for n in names if n in VARIANTS])
    else:
        run(a.report, names, a.limit, a.group, a.offset, a.rerank)


if __name__ == "__main__":
    main()
