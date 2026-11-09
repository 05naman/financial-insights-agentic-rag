"""End-to-end answer check on REAL reports (needs LLM quota; runs in small resumable batches).

    uv run python -m evals.real_answers --mode agentic --limit 5          # next 5 unanswered, results stream
    uv run python -m evals.real_answers --mode naive --set answerable --limit 5
    uv run python -m evals.real_answers --summary                         # numbers for everything run so far

Questions are in evals/real_answers.json (written before any run). Each result is appended to
evals/results/real_answers.jsonl (git-ignored) with the full answer, so every answer can be read by hand.
A question that failed because the LLM was unavailable is NOT recorded, so a rerun picks it up.
"""

import argparse
import asyncio
import json
import statistics
import time
from collections import defaultdict
from pathlib import Path

from app.container import get_container
from evals.run import load_catalog
from evals.scoring import score_answer

HERE = Path(__file__).parent
QUESTIONS = HERE / "real_answers.json"
RESULTS = HERE / "results" / "real_answers.jsonl"


def load_done() -> set[tuple[str, str]]:
    if not RESULTS.exists():
        return set()
    rows = [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]
    return {(r["mode"], r["id"]) for r in rows}


async def run(modes: list[str], which: str, limit: int | None, redo: bool) -> None:
    questions = [q for q in json.loads(QUESTIONS.read_text()) if which in ("all", q["set"])]
    qa = get_container().qa_service(await load_catalog())
    RESULTS.parent.mkdir(exist_ok=True)
    done = set() if redo else load_done()
    for mode in modes:
        todo = [q for q in questions if (mode, q["id"]) not in done][:limit]
        print(f"[{mode}] {len(todo)} question(s) to run", flush=True)
        for q in todo:
            t = time.perf_counter()
            try:
                result = await qa.answer(q["question"], mode=mode)
            except Exception as e:  # not recorded: rerun later
                print(f"[{mode}] {q['id']} ERROR (not recorded): {str(e)[:120]}", flush=True)
                continue
            seconds = time.perf_counter() - t
            s = score_answer(q, result)
            row = {
                "mode": mode,
                "id": q["id"],
                "set": q["set"],
                "category": q["category"],
                "question": q["question"],
                "correct": s.correct,
                "citation_ok": s.citation_ok,
                "grounded": s.grounded,
                "seconds": round(seconds, 1),
                "llm_calls": result.llm_calls,
                "answer": result.answer,
            }
            with RESULTS.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            short = " ".join(result.answer.split())[:110]
            print(
                f"[{mode}] {q['id']} {'PASS' if s.correct else 'FAIL'} "
                f"cite={s.citation_ok} grounded={s.grounded} {seconds:.1f}s calls={result.llm_calls}"
                f"\n    Q: {q['question']}\n    A: {short}",
                flush=True,
            )


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}% ({n}/{d})" if d else "n/a"


def summary() -> None:
    rows = [json.loads(line) for line in RESULTS.read_text().splitlines() if line.strip()]
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["mode"], r["set"])].append(r)
    print(
        "| Mode | Set | Questions | Correct | Cited right report | No invented numbers | Median s | Slowest s | Avg LLM calls |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    for (mode, which), rs in sorted(groups.items()):
        cites = [r for r in rs if r["citation_ok"] is not None]
        secs = sorted(r["seconds"] for r in rs)
        print(
            f"| {mode} | {which} | {len(rs)} | {pct(sum(r['correct'] for r in rs), len(rs))} "
            f"| {pct(sum(bool(r['citation_ok']) for r in cites), len(cites))} "
            f"| {pct(sum(r['grounded'] for r in rs), len(rs))} "
            f"| {statistics.median(secs):.1f} | {secs[-1]:.1f} "
            f"| {sum(r['llm_calls'] for r in rs) / len(rs):.1f} |"
        )
    print("\nBy category (correct):")
    cats: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for r in rows:
        cats[(r["mode"], r["category"])].append(r["correct"])
    for (mode, cat), v in sorted(cats.items()):
        print(f"  {mode:8} {cat:13} {pct(sum(v), len(v))}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--mode", nargs="+", default=["agentic"])
    ap.add_argument("--set", default="all", choices=["all", "answerable", "unanswerable"])
    ap.add_argument("--limit", type=int, help="run at most N not-yet-run questions per mode")
    ap.add_argument("--redo", action="store_true", help="ignore earlier results for this selection")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        summary()
        return
    try:
        asyncio.run(run(a.mode, a.set, a.limit, a.redo))
    finally:
        get_container().store.client.close()


if __name__ == "__main__":
    main()
