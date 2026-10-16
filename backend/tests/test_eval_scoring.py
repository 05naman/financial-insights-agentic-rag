from app.services.qa import AnswerResult, Citation
from evals.scoring import score_answer

Q = {
    "question": "TCS revenue FY2024?",
    "expected_contains": [["2,40,893", "240893"]],
    "expected_sources": [{"ticker": "TCS", "fiscal_year": 2024}],
}


def result(answer, cites=()):
    return AnswerResult(answer, [Citation(*c) for c in cites])


def test_correct_answer_with_citation():
    r = result(
        "Revenue was Rs 240893 crore [TCS FY2024 p.1]", [("TCS", 2024, 1, "Revenue 2,40,893")]
    )
    s = score_answer(Q, r)
    assert s.correct and s.citation_ok and s.grounded


def test_wrong_answer_and_missing_citation():
    s = score_answer(Q, result("Revenue was Rs 1,00,000 crore"))
    assert not s.correct and s.citation_ok is False


def test_unanswerable_requires_refusal():
    q = {"question": "Future price?", "unanswerable": True}
    assert score_answer(q, result("Insufficient evidence in the provided reports.")).correct
    assert not score_answer(q, result("It will be Rs 5,000.")).correct


def test_retrieval_recall_accepts_any_gold_page():
    from evals.scoring import retrieval_recall

    gold = [
        {"ticker": "TCS", "fiscal_year": 2024, "pages": [3, 5]},
        {"ticker": "TCS", "fiscal_year": 2023, "pages": [3]},
    ]
    assert retrieval_recall(gold, [("TCS", 2024, 5), ("TCS", 2023, 3)]) == 1.0
    assert retrieval_recall(gold, [("TCS", 2024, 5)]) == 0.5
    assert retrieval_recall(gold, [("TCS", 2024, 9)]) == 0.0
    assert retrieval_recall([], []) == 1.0
