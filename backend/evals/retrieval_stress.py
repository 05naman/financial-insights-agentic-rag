"""Retrieval stress test: how well does the search find the right page for hard, realistic queries?

No LLM needed. Every case has known answer pages, so recall is exact.

    uv run python -m evals.retrieval_stress --limit 5            # 5 mixed cases, each printed as it finishes
    uv run python -m evals.retrieval_stress --category typos     # one kind of question
    uv run python -m evals.retrieval_stress                      # all cases (fast setups)
    uv run python -m evals.retrieval_stress --rerank             # plus the slow reranker setups
"""

import argparse
import json
import re
import time
from collections import defaultdict
from pathlib import Path

import pymupdf

from app.container import get_container

ROOT = Path(__file__).resolve().parents[2]
PDFS = ROOT / "data" / "pdfs"
TRUTH = json.loads((Path(__file__).parent / "mock_truth.json").read_text())
NAMES = {"BHIT": "Bharat Infotech", "SAGR": "Sagar Pharma", "NAVM": "Navbharat Motors"}
FULL = {
    "BHIT": "Bharat Infotech Limited",
    "SAGR": "Sagar Pharma Limited",
    "NAVM": "Navbharat Motors Limited",
}
HEADINGS = {
    "chair": "Chairman's Message",
    "highlights": "Financial Highlights",
    "risks": "Risks and Concerns",
    "pnl": "Standalone Statement of Profit and Loss",
    "bs": "Standalone Balance Sheet",
}
K = 6


def inr(n: float) -> str:
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail, parts = s[:-3], s[-3:], []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    return ",".join(([head] if head else []) + parts + [tail])


_page_text: dict[tuple[str, int], list[str]] = {}


def pages_of(t: str, fy: int) -> list[str]:
    if (t, fy) not in _page_text:
        with pymupdf.open(PDFS / f"{t}_FY{fy}.pdf") as doc:
            _page_text[(t, fy)] = [p.get_text() for p in doc]
    return _page_text[(t, fy)]


def section_pages(t: str, fy: int, *sections: str) -> list[int]:
    out = []
    for i, txt in enumerate(pages_of(t, fy), start=1):
        if any(HEADINGS[s] in txt for s in sections):
            out.append(i)
    return out


def gold(t: str, fy: int, *sections: str) -> dict:
    return {"ticker": t, "fiscal_year": fy, "pages": section_pages(t, fy, *sections)}


# concept -> (answer sections, [phrasings from literal to indirect])
CONCEPTS = {
    "revenue": (
        ("chair", "highlights", "pnl"),
        [
            "revenue from operations",
            "turnover",
            "top line sales",
            "how much did the company sell in total",
        ],
    ),
    "profit": (
        ("chair", "highlights", "pnl"),
        [
            "profit after tax",
            "net profit",
            "net income",
            "bottom line",
            "how much money did it earn after paying taxes",
        ],
    ),
    "employees": (
        ("chair",),
        [
            "number of employees",
            "head count",
            "workforce size",
            "how many people work at the company",
        ],
    ),
    "dividend": (
        ("highlights", "risks"),
        ["dividend per share", "payout to shareholders", "dividend recommended by the board"],
    ),
    "debt": (
        ("bs",),
        ["borrowings", "total debt", "how much does the company owe", "loans outstanding"],
    ),
    "cash": (("bs",), ["cash and cash equivalents", "cash balance", "money in the bank"]),
    "assets": (("bs",), ["total assets", "everything the company owns"]),
    "risks": (
        ("risks",),
        [
            "key risks",
            "what could go wrong for the business",
            "threats to the business",
            "risk factors",
        ],
    ),
    "segments": (
        ("highlights",),
        ["segment revenue", "which business line is biggest", "revenue split by segment"],
    ),
    "margin": (("highlights",), ["pre-tax margin", "profitability percentage"]),
}
# indirect wording that the synonym list deliberately does not contain
HELD_OUT = [
    ("gross receipts of", ("chair", "highlights", "pnl")),
    ("income generated from selling products by", ("chair", "highlights", "pnl")),
    ("surplus left after expenses and tax at", ("chair", "highlights", "pnl")),
    ("earnings after tax of", ("chair", "highlights", "pnl")),
    ("team size at", ("chair",)),
    ("number of people on the payroll of", ("chair",)),
    ("liabilities to lenders of", ("bs",)),
    ("bank loans taken by", ("bs",)),
    ("liquid funds held by", ("bs",)),
    ("what the firm possesses in total, balance sheet of", ("bs",)),
    ("hazards facing", ("risks",)),
    ("downside factors and vulnerabilities of", ("risks",)),
    ("distribution to owners per share by", ("highlights", "risks")),
    ("regional or product-wise contribution at", ("highlights",)),
]
YEAR_FORMS = {  # how a person might write fiscal year 2024
    2024: [
        "FY2024",
        "FY24",
        "2023-24",
        "2023-2024",
        "year ended March 31, 2024",
        "March 2024",
        "financial year 2024",
    ],
    2023: ["FY2023", "FY23", "2022-23", "year ended March 31, 2023"],
}
TYPOS = {
    "revenue": "revnue",
    "profit": "proft",
    "employees": "employes",
    "dividend": "divident",
    "assets": "assest",
    "risks": "riscs",
    "borrowings": "borowings",
    "margin": "margn",
}


def build_cases() -> list[dict]:
    cases: list[dict] = []

    def add(cat, q, golds=None, must=None):
        cases.append({"cat": cat, "q": q, "gold": golds, "must": must})

    tick = list(NAMES)
    # 1) literal phrasing, ticker + FY2024
    for t in tick:
        for secs, phrases in CONCEPTS.values():
            add("literal", f"{phrases[0]} {t} FY2024", [gold(t, 2024, *secs)])
    # 2) indirect wording (synonyms / plain-English paraphrase), company named in words
    for t in tick:
        for secs, phrases in CONCEPTS.values():
            for p in phrases[1:3]:
                add("synonyms", f"{p} of {NAMES[t]} in FY2024", [gold(t, 2024, *secs)])
    # 3) the year written in different ways
    for t in tick:
        for form in YEAR_FORMS[2024][1:]:
            add(
                "year_formats",
                f"{t} revenue from operations {form}",
                [gold(t, 2024, *CONCEPTS["revenue"][0])],
            )
        for form in YEAR_FORMS[2023][1:]:
            add(
                "year_formats",
                f"{NAMES[t]} profit after tax {form}",
                [gold(t, 2023, *CONCEPTS["profit"][0])],
            )
    # 4) the company written in different ways
    for t in tick:
        for who in (FULL[t], NAMES[t].lower(), t.lower(), NAMES[t].split()[0], NAMES[t][:-1]):
            add("company_names", f"total assets of {who} FY2024", [gold(t, 2024, "bs")])
    # 5) typos in the metric word
    for t in tick:
        for c, bad in TYPOS.items():
            secs, phrases = CONCEPTS[{"borrowings": "debt"}.get(c, c)]
            add("typos", f"{bad} {t} FY2024", [gold(t, 2024, *secs)])
    # 6) exact figures (answer: a page whose text contains the number)
    for t in tick:
        d = TRUTH[t]["2024"]
        for _label, n in (
            ("revenue", d["revenue"]),
            ("pat", d["pat"]),
            ("assets", d["total_assets"]),
            ("employees", d["employees"]),
        ):
            for form in (inr(n), str(n), f"Rs {inr(n)} crore"):
                add("exact_figures", form, must=inr(n))
    # 7) two companies in one question
    for a, b in (("BHIT", "SAGR"), ("SAGR", "NAVM"), ("BHIT", "NAVM")):
        add(
            "multi_company",
            f"compare the profit after tax of {NAMES[a]} and {NAMES[b]} in FY2024",
            [gold(a, 2024, "highlights", "pnl"), gold(b, 2024, "highlights", "pnl")],
        )
        add(
            "multi_company",
            f"{a.lower()} vs {b.lower()} borrowings FY24",
            [gold(a, 2024, "bs"), gold(b, 2024, "bs")],
        )
    # 8) two years in one question
    for t in tick:
        add(
            "multi_year",
            f"{NAMES[t]} revenue in FY2022 and FY2024",
            [
                gold(t, 2022, "chair", "highlights", "pnl"),
                gold(t, 2024, "chair", "highlights", "pnl"),
            ],
        )
        add(
            "multi_year",
            f"how did {t} profit change between 2022-23 and 2023-24",
            [
                gold(t, 2023, "chair", "highlights", "pnl"),
                gold(t, 2024, "chair", "highlights", "pnl"),
            ],
        )
    # 8b) HELD-OUT wording: phrasings that are NOT in the synonym list, to check it is not just memorised
    for t in tick:
        for phrase, secs in HELD_OUT:
            add("held_out", f"{phrase} {NAMES[t]} FY2024", [gold(t, 2024, *secs)])
    # 9) long, chatty questions
    for t in tick:
        add(
            "chatty",
            f"I am an investor looking at {FULL[t]}. Could you tell me roughly how large the business got in the year ended March 2024?",
            [gold(t, 2024, "chair", "highlights", "pnl")],
        )
        add(
            "chatty",
            f"what should I worry about if I invest in {NAMES[t]}, according to their latest annual report (FY24)?",
            [gold(t, 2024, "risks")],
        )
    return cases


def contains_figure(text: str, figure: str) -> bool:
    return figure.replace(",", "") in re.sub(r"(?<=\d),(?=\d)", "", text)


def score(case, hits) -> tuple[float, int | None]:
    """(recall, rank of the first correct hit or None)."""
    locs = [(h.ticker, h.fiscal_year, h.page) for h in hits]
    if case["must"]:
        ranks = [i for i, h in enumerate(hits, 1) if contains_figure(h.text, case["must"])]
        return (1.0 if ranks else 0.0), (ranks[0] if ranks else None)
    found = [
        any((g["ticker"], g["fiscal_year"], p) in locs for p in g["pages"]) for g in case["gold"]
    ]
    first = [
        i
        for i, loc in enumerate(locs, 1)
        if any(
            loc[0] == g["ticker"] and loc[1] == g["fiscal_year"] and loc[2] in g["pages"]
            for g in case["gold"]
        )
    ]
    return sum(found) / len(found), (first[0] if first else None)


# improve=False is the plain baseline; improve=True adds typo fixing, synonyms and company/year detection
ARMS = [
    ("dense", dict(hybrid=False, rerank=False, improve=False)),
    ("hybrid", dict(hybrid=True, rerank=False, improve=False)),
    ("dense+improved", dict(hybrid=False, rerank=False, improve=True)),
    ("hybrid+improved", dict(hybrid=True, rerank=False, improve=True)),
    ("hybrid+rerank", dict(hybrid=True, rerank=True, improve=False)),  # slow: opt in with --rerank
    ("hybrid+rerank+improved", dict(hybrid=True, rerank=True, improve=True)),
]
SLOW = {"hybrid+rerank", "hybrid+rerank+improved"}


def diverse_order(cases: list[dict]) -> list[dict]:
    """Round-robin over categories, so even `--limit 5` samples five different kinds of question."""
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        by_cat[c["cat"]].append(c)
    out: list[dict] = []
    while any(by_cat.values()):
        for cat in list(by_cat):
            if by_cat[cat]:
                out.append(by_cat[cat].pop(0))
    return out


def mark(rec: float, rank: int | None) -> str:
    return f"✓#{rank}" if rec == 1.0 else (f"½#{rank}" if rec > 0 else "✗")


def run(args, retriever=None) -> dict:
    retriever = retriever or get_container().retriever
    arms = [a for a in ARMS if args.rerank or a[0] not in SLOW]
    cases = diverse_order(build_cases())
    if args.category:
        cases = [c for c in cases if c["cat"] == args.category]
    if args.limit:
        cases = cases[: args.limit]
    results: dict[str, dict[str, list]] = {a[0]: defaultdict(list) for a in arms}
    misses: list[str] = []
    width = max(len(a[0]) for a in arms)
    print(
        f"{len(cases)} cases x {len(arms)} search setups (top-{K}). ✓#n = right page found at rank n, ½ = some, ✗ = missed\n"
    )
    done: list[dict] = []
    try:
        for i, c in enumerate(cases, start=1):
            line = []
            for name, kw in arms:
                t0 = time.perf_counter()
                hits = retriever.search(c["q"], limit=K, **kw)
                ms = (time.perf_counter() - t0) * 1000
                rec, rank = score(c, hits)
                results[name][c["cat"]].append((rec, rank, ms))
                line.append(f"{name:<{width}} {mark(rec, rank):<5}")
                if rec < 1.0:
                    misses.append(f"[{name}] [{c['cat']}] {c['q']}")
            done.append(c)
            print(
                f"{i:>3}/{len(cases)}  [{c['cat']}]  {c['q']}", flush=True
            )  # printed the moment it finishes
            print("       " + "   ".join(line), flush=True)
    except KeyboardInterrupt:
        print("\n(interrupted: summary of the cases completed so far)")
    return {
        "results": results,
        "misses": misses,
        "n": len(done),
        "cases": done,
        "arms": [a[0] for a in arms],
    }


def table(out: dict) -> str:
    if not out["n"]:
        return "no cases ran"
    cats = sorted({c["cat"] for c in out["cases"]})
    arms = out["arms"]
    lines = [
        f"\nSummary: {out['n']} cases, top-{K}. Cell = recall% / MRR (1.00 means the right page was always first)\n"
    ]
    lines.append("| Category (n) | " + " | ".join(arms) + " |")
    lines.append("|---|" + "---|" * len(arms))
    for cat in [*cats, "ALL"]:
        row = []
        for a in arms:
            rows = [r for k, v in out["results"][a].items() if cat in (k, "ALL") for r in v]
            rec = sum(r[0] for r in rows) / len(rows)
            mrr = sum(1 / r[1] if r[1] else 0 for r in rows) / len(rows)
            row.append(f"{rec:.0%} / {mrr:.2f}")
        n = len(out["results"][arms[0]][cat]) if cat != "ALL" else out["n"]
        lines.append(f"| {cat} ({n}) | " + " | ".join(row) + " |")
    ms = [sum(r[2] for v in out["results"][a].values() for r in v) / out["n"] for a in arms]
    lines.append("| avg ms / query | " + " | ".join(f"{m:.0f}" for m in ms) + " |")
    return "\n".join(lines)


VARIANTS: list[tuple[str, dict]] = [
    ("baseline", {}),
    ("+auto-filter", {"query_auto_filters": True}),
    ("+numbers", {"index_normalize_numbers": True}),
    ("+clean chunks", {"index_drop_tiny_chunks": True}),
    ("+company name", {"index_company_name": True}),
    ("+typo fix", {"query_spell_correct": True}),
    ("+synonyms", {"query_synonyms": True}),
]
_OFF = dict(
    index_normalize_numbers=False,
    index_company_name=False,
    index_drop_tiny_chunks=False,
    query_spell_correct=False,
    query_synonyms=False,
    query_auto_filters=False,
)


def _raw_pages() -> dict[Path, list]:
    """Parse each PDF once (the slow part) and keep it for every variant."""
    from evals.pages_cache import raw_pages

    return {
        p: raw_pages(p) for p in sorted(PDFS.glob("*_FY*.pdf")) if p.stem.split("_")[0] in NAMES
    }


def build_variant(flags: dict, raw: dict, embedder, persist: Path | None = None):
    """An in-memory index built exactly like production ingestion, with the given options switched on."""
    from qdrant_client import QdrantClient

    from app.core.config import Settings
    from app.ingestion.chunker import chunk_pages
    from app.ingestion.filename import parse_report_filename
    from app.ingestion.pdf_loader import strip_boilerplate
    from app.ingestion.pipeline import EMBED_BATCH, embedding_inputs
    from app.retrieval.retriever import Retriever
    from app.retrieval.vector_store import VectorStore

    st = Settings(**{**_OFF, **flags})
    client = QdrantClient(path=str(persist)) if persist else QdrantClient(":memory:")
    store = VectorStore(client, "variant", embedder.dim)
    if persist and store.count() > 0:  # built on an earlier run: reuse it, no embedding needed
        return Retriever(embedder, store, None, st, FULL)
    for doc_id, (path, pages) in enumerate(raw.items(), start=1):
        name = parse_report_filename(path.name)
        pages = strip_boilerplate(pages, min_pages=8, share=st.index_boilerplate_share)
        chunks = chunk_pages(
            pages,
            document_id=doc_id,
            ticker=name.ticker,
            fiscal_year=name.fiscal_year,
            drop_tiny_text=st.index_drop_tiny_chunks,
        )
        dense_t, sparse_t = embedding_inputs(chunks, FULL, st)
        for i in range(0, len(chunks), EMBED_BATCH):
            d, sp = embedder.embed_documents(
                dense_t[i : i + EMBED_BATCH], sparse_t[i : i + EMBED_BATCH]
            )
            store.upsert(chunks[i : i + EMBED_BATCH], d, sp)
    return Retriever(embedder, store, None, st, FULL)


def run_sets(sets: list[tuple[str, dict]], title: str) -> None:
    from app.retrieval.embedder import FastEmbedder

    print("Parsing the PDFs once ...", flush=True)
    raw = _raw_pages()
    embedder = FastEmbedder()
    cases = build_cases()
    cats = sorted({c["cat"] for c in cases})
    rows: dict[str, list[str]] = {c: [] for c in [*cats, "ALL"]}
    print(f"{len(cases)} cases. {title} (hybrid search, top-{K})\n", flush=True)
    for label, flags in sets:
        r = build_variant(flags, raw, embedder)
        per: dict[str, list] = defaultdict(list)
        for c in cases:
            rec, rank = score(c, r.search(c["q"], limit=K, hybrid=True, rerank=False, improve=True))
            per[c["cat"]].append((rec, rank))
            per["ALL"].append((rec, rank))
        for cat in rows:
            x = per[cat]
            rows[cat].append(
                f"{sum(i[0] for i in x) / len(x):.0%} / {sum(1 / i[1] if i[1] else 0 for i in x) / len(x):.2f}"
            )
        print(
            f"  done {label:<20} ALL = {rows['ALL'][-1]}   ({r.store.count()} chunks)", flush=True
        )
    print("\nCell = recall% / MRR  (MRR 1.00 = the right page is always ranked first)\n")
    print("| Category | " + " | ".join(s[0] for s in sets) + " |")
    print("|---|" + "---|" * len(sets))
    for cat, row in rows.items():
        print(f"| {cat} | " + " | ".join(row) + " |")


def run_boost() -> None:
    """Does boosting primary statements on money questions help, and does it hurt anything else?"""
    from app.core.config import Settings

    base = {k: getattr(Settings(), k) for k in _OFF}
    sets = [
        ("no boost", base),
        ("boost .25", {**base, "query_statement_boost": 0.25}),
        ("boost .6", {**base, "query_statement_boost": 0.6}),
        (
            "boost .6 any question",
            {**base, "query_statement_boost": 0.6, "query_boost_financial_only": False},
        ),
    ]
    run_sets(sets, "Primary-statement boost (current defaults otherwise).")


def run_variants() -> None:
    sets, flags = [], {}
    for label, extra in VARIANTS:
        flags = {**flags, **extra}  # each fix is added on top of the previous ones
        sets.append((label, dict(flags)))
    run_sets(sets, "Each fix is added on top of the previous one.")


def run_ablation() -> None:
    allon = {k: True for k in _OFF}
    sets = [("all on", allon)] + [
        (f"without {k.split('_', 1)[1]}", {**allon, k: False}) for k in _OFF
    ]
    run_sets(sets, "All fixes on, then each one switched off in turn.")


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--limit", type=int, help="run only the first N cases (mixed across categories)"
    )
    ap.add_argument("--category", help="run one category only, e.g. typos")
    ap.add_argument("--rerank", action="store_true", help="also run the (slow) reranker setups")
    ap.add_argument("--show-misses", action="store_true", help="list every missed query at the end")
    ap.add_argument(
        "--ablate", action="store_true", help="switch each fix off in turn from the all-on setup"
    )
    ap.add_argument("--boost", action="store_true", help="compare primary-statement boost settings")
    ap.add_argument(
        "--variants", action="store_true", help="compare each retrieval fix on throwaway indexes"
    )
    args = ap.parse_args()
    if args.variants:
        run_variants()
        return
    if args.ablate:
        run_ablation()
        return
    if args.boost:
        run_boost()
        return
    out = run(args)
    print(table(out))
    if args.show_misses and out["misses"]:
        print(f"\nMisses ({len(out['misses'])}):")
        for m in out["misses"]:
            print("  ", m)
    get_container().store.client.close()


if __name__ == "__main__":
    main()
