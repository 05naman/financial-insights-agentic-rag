"""Evaluate retrieval and answering on a question set with known answers.

Usage (from backend/):
    uv run python -m evals.run --retrieval-only          # no LLM needed, fast, deterministic
    uv run python -m evals.run --modes naive hybrid agentic
    uv run python -m evals.run --modes agentic --category calculation --limit 5
See docs/evaluation.md for how the set is built and what each metric means.
"""

import argparse
import asyncio
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app.container import get_container
from app.db.repositories import DocumentRepository
from app.db.session import get_sessionmaker, init_db
from app.retrieval.schemas import SearchFilters
from evals.scoring import retrieval_recall, score_answer

HERE = Path(__file__).parent
K = 6


def pct(n: float, d: float) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def load_questions(path: Path, category: str | None, limit: int | None) -> list[dict]:
    qs = [q for q in json.loads(path.read_text()) if not q.get("skip")]
    if category:
        qs = [q for q in qs if q["category"] == category]
    return qs[:limit]


async def load_catalog() -> dict[str, list[int]]:
    await init_db()
    catalog: dict[str, list[int]] = defaultdict(list)
    async with get_sessionmaker()() as session:
        for d in await DocumentRepository(session).list():
            if d.status.value == "ready":
                catalog[d.ticker].append(d.fiscal_year)
    return dict(catalog)


def retrieval_report(questions: list[dict]) -> str:
    """Does the right page come back? Scored per retrieval setup, with no LLM involved.

    Two views: raw question only, and with the company/year filters a good planner would add
    (taken from the gold labels). Follow-ups are skipped: they need conversation context."""
    retriever = get_container().retriever
    setups = [
        ("dense only", dict(hybrid=False, rerank=False)),
        ("hybrid (dense + BM25)", dict(hybrid=True, rerank=False)),
        ("hybrid + reranker", dict(hybrid=True, rerank=True)),
    ]
    qs = [
        q
        for q in questions
        if q.get("gold") and not q.get("unanswerable") and q["category"] != "follow_up"
    ]
    out = [f"## Retrieval (top-{K}), {len(qs)} questions\n"]
    for view, with_filters in (
        ("raw question, no filters", False),
        ("with company/year filters", True),
    ):
        out.append(f"### {view}\n")
        out.append("| Setup | Mean recall | All gold pages found | Avg latency (ms) |")
        out.append("|---|---|---|---|")
        per_cat: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for name, kw in setups:
            recalls, lat = [], []
            for q in qs:
                flt = SearchFilters()
                if with_filters:
                    flt = SearchFilters(
                        tickers=sorted({g["ticker"] for g in q["gold"]}),
                        fiscal_years=sorted({g["fiscal_year"] for g in q["gold"]}),
                    )
                t = time.perf_counter()
                hits = retriever.search(q["question"], limit=K, filters=flt, **kw)
                lat.append((time.perf_counter() - t) * 1000)
                r = retrieval_recall(q["gold"], [(h.ticker, h.fiscal_year, h.page) for h in hits])
                recalls.append(r)
                per_cat[q["category"]][name].append(r)
            out.append(
                f"| {name} | {pct(sum(recalls), len(recalls))} "
                f"| {pct(sum(r == 1.0 for r in recalls), len(recalls))} | {sum(lat) / len(lat):.0f} |"
            )
        out.append("\nMean recall by category:\n")
        out.append("| Category | " + " | ".join(n for n, _ in setups) + " |")
        out.append("|---|" + "---|" * len(setups))
        for cat in sorted(per_cat):
            row = [pct(sum(per_cat[cat][n]), len(per_cat[cat][n])) for n, _ in setups]
            out.append(f"| {cat} | " + " | ".join(row) + " |")
        out.append("")
    return "\n".join(out)


async def answer_report(modes: list[str], questions: list[dict]) -> str:
    qa = get_container().qa_service(await load_catalog())
    rows = []
    for mode in modes:
        st: dict[str, float] = defaultdict(float)
        by_cat = defaultdict(lambda: [0, 0])
        by_diff = defaultdict(lambda: [0, 0])
        lat, calls, failures = [], [], []
        for q in questions:
            t = time.perf_counter()
            try:
                result = await qa.answer(q["question"], mode=mode, history=q.get("history"))
                s = score_answer(q, result)
            except Exception as e:  # keep going; count as wrong
                print(f"[{mode}] {q['id']} ERROR: {e}")
                st["errors"] += 1
                by_cat[q["category"]][1] += 1
                by_diff[q["difficulty"]][1] += 1
                continue
            lat.append(time.perf_counter() - t)
            calls.append(result.llm_calls)
            st["correct"] += s.correct
            st["grounded"] += s.grounded
            if s.citation_ok is not None:
                st["cit_total"] += 1
                st["cit_ok"] += s.citation_ok
            if s.retrieval_recall is not None:
                st["rec_total"] += 1
                st["rec_sum"] += s.retrieval_recall
            for bucket, key in ((by_cat, q["category"]), (by_diff, q["difficulty"])):
                bucket[key][0] += s.correct
                bucket[key][1] += 1
            if not s.correct:
                failures.append(
                    {"id": q["id"], "question": q["question"], "answer": result.answer[:400]}
                )
            print(f"[{mode}] {q['id']}: {'PASS' if s.correct else 'FAIL'}")
        rows.append((mode, len(questions), st, by_cat, by_diff, lat, calls, failures))

    out = ["## Answer quality\n"]
    out.append(
        "| Mode | Accuracy | Retrieval recall | Citation correct | Grounded | Avg latency (s) | Avg LLM calls |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for mode, n, st, _, _, lat, calls, _ in rows:
        ok = len(lat)
        if not ok:
            out.append(f"| {mode} | n/a | n/a | n/a | n/a | n/a | n/a |")
            continue
        out.append(
            f"| {mode} | {pct(st['correct'], n)} | {pct(st['rec_sum'], st['rec_total'])} "
            f"| {pct(st['cit_ok'], st['cit_total'])} | {pct(st['grounded'], ok)} "
            f"| {sum(lat) / ok:.1f} | {sum(calls) / ok:.1f} |"
        )
    for title, idx, order in (("category", 3, None), ("difficulty", 4, ["easy", "medium", "hard"])):
        keys = order or sorted({k for r in rows for k in r[idx]})
        out.append(f"\nAccuracy by {title}:\n")
        out.append(f"| {title.title()} | " + " | ".join(r[0] for r in rows) + " |")
        out.append("|---|" + "---|" * len(rows))
        for k in keys:
            out.append(f"| {k} | " + " | ".join(pct(*r[idx][k]) for r in rows) + " |")
    for mode, *_, failures in rows:
        if failures:
            out.append(f"\n<details><summary>{mode}: {len(failures)} failures</summary>\n")
            for f in failures:
                out.append(f"- **{f['id']}** {f['question']}\n  > {f['answer']!r}")
            out.append("\n</details>")
    return "\n".join(out)


async def main_async(args) -> str:
    qs = load_questions(args.questions, args.category, args.limit)
    parts = [f"# Eval results ({datetime.now():%Y-%m-%d %H:%M}), {len(qs)} questions\n"]
    if args.retrieval_only or args.with_retrieval:
        parts.append(retrieval_report(qs))
    if not args.retrieval_only:
        parts.append(await answer_report(args.modes, qs))
    report = "\n\n".join(parts)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}.md").write_text(report)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["naive", "hybrid", "agentic"])
    ap.add_argument("--questions", type=Path, default=HERE / "questions.json")
    ap.add_argument("--category")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--retrieval-only", action="store_true")
    ap.add_argument("--with-retrieval", action="store_true", help="also print the retrieval table")
    args = ap.parse_args()
    try:
        print(asyncio.run(main_async(args)))
    finally:
        get_container().store.client.close()


if __name__ == "__main__":
    main()
