import re
from dataclasses import dataclass

from app.agent.grounding import check_grounding
from app.retrieval.schemas import SearchHit
from app.services.qa import AnswerResult

INSUFFICIENT = "insufficient evidence"


def normalize(text: str) -> str:
    return re.sub(r"[\s,₹]", "", text.lower())


_NUMERIC = re.compile(r"^[\d.,]+$")


def contains(answer: str, expected: str) -> bool:
    """Numbers must match as whole numbers (24.1 does not match 124.1 or 24.15); words match loosely."""
    if _NUMERIC.match(expected.strip()):
        text = re.sub(
            r"(?<=\d),(?=\d)", "", answer.lower()
        )  # drop thousands separators inside numbers
        want = re.escape(expected.replace(",", ""))
        return re.search(rf"(?<![\d.]){want}(?![\d]|\.\d)", text) is not None
    return normalize(expected) in normalize(answer)


@dataclass
class Score:
    correct: bool
    citation_ok: bool | None  # None when not applicable
    grounded: bool
    retrieval_recall: float | None  # share of gold locations that were retrieved


def retrieval_recall(gold: list[dict], retrieved: list[tuple[str, int, int]]) -> float:
    """A gold item ({ticker, fiscal_year, pages}) counts as found if ANY acceptable page of that
    company-year was retrieved. Recall = found / total gold items."""
    if not gold:
        return 1.0
    got = set(retrieved)
    found = sum(
        1
        for g in gold
        if any((g["ticker"].upper(), g["fiscal_year"], p) in got for p in g["pages"])
    )
    return found / len(gold)


def score_answer(q: dict, result: AnswerResult) -> Score:
    answer = result.answer
    if q.get("unanswerable"):
        correct = INSUFFICIENT in answer.lower()
    else:
        correct = INSUFFICIENT not in answer.lower() and all(
            any(contains(answer, alt) for alt in group) for group in q["expected_contains"]
        )

    citation_ok = None
    expected = q.get("expected_sources")
    if expected and not q.get("unanswerable"):
        cited = {(c.ticker, c.fiscal_year) for c in result.citations}
        citation_ok = all((e["ticker"].upper(), e["fiscal_year"]) in cited for e in expected)

    cited_hits = [
        SearchHit("", 0, c.text, c.ticker, c.fiscal_year, c.page, "text") for c in result.citations
    ]
    grounded = (
        check_grounding(
            answer, cited_hits, [], q["question"], require_citation=False
        ).unsupported_numbers
        == []
    )
    recall = None
    if q.get("gold") and not q.get("unanswerable"):
        recall = retrieval_recall(q["gold"], result.retrieved)
    return Score(correct, citation_ok, grounded, recall)
