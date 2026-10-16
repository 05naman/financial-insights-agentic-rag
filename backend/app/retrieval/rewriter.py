"""Query clean-up before search: fix typos against the reports' own vocabulary and add finance synonyms."""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from difflib import get_close_matches

from app.retrieval.text import normalize_numbers

# plain-English phrasing -> the words reports actually use (matched as whole words or phrases, lower case)
FINANCE_SYNONYMS: dict[str, str] = {
    "turnover": "revenue from operations",
    "top line": "revenue from operations",
    "sales": "revenue from operations",
    "net income": "profit for the year",
    "net profit": "profit for the year",
    "bottom line": "profit for the year",
    "earnings": "profit for the year",
    "after paying taxes": "profit for the year",
    "head count": "employees",
    "headcount": "employees",
    "workforce": "employees",
    "staff": "employees",
    "people work": "employees",
    "debt": "borrowings",
    "loans": "borrowings",
    "owe": "borrowings",
    "owes": "borrowings",
    "payout": "dividend per share",
    "shareholders": "dividend",
    "cash balance": "cash and cash equivalents",
    "money in the bank": "cash and cash equivalents",
    "owns": "total assets",
    "threats": "risks and concerns",
    "worry": "risks and concerns",
    "go wrong": "risks and concerns",
    "business line": "segment",
    "split by": "segment",
    "profitability": "margin",
}
_WORD = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True)
class RewrittenQuery:
    dense: str  # typos fixed; the wording stays natural for the embedding model
    sparse: str  # typos fixed + synonyms + numbers without commas, for the keyword index


class QueryRewriter:
    def __init__(
        self,
        vocabulary: Iterable[str] = (),
        protected: Iterable[str] = (),
        *,
        spell_correct: bool = True,
        synonyms: bool = True,
        numbers: bool = True,
    ):
        self.numbers = numbers  # must match how the index was built (commas removed or not)
        self.spell_correct = spell_correct
        self.synonyms = synonyms
        self.protected = {p.lower() for p in protected}
        self._by_len: dict[int, list[str]] = {}
        self.set_vocabulary(vocabulary)

    def set_vocabulary(self, vocabulary: Iterable[str]) -> None:
        self.vocab = {w.lower() for w in vocabulary if len(w) >= 3}
        self._by_len = {}
        for w in self.vocab:
            self._by_len.setdefault(len(w), []).append(w)

    def correct(self, text: str) -> str:
        """Replace words the reports never use with their closest word that they do use."""
        if not self.spell_correct or not self.vocab:
            return text

        def fix(m: re.Match[str]) -> str:
            w = m.group(0)
            lw = w.lower()
            if len(lw) < 4 or lw in self.vocab or lw in self.protected:
                return w
            pool = [c for n in (len(lw) - 1, len(lw), len(lw) + 1) for c in self._by_len.get(n, [])]
            best = get_close_matches(lw, pool, n=1, cutoff=0.78)
            return best[0] if best else w

        return _WORD.sub(fix, text)

    def expand(self, text: str) -> str:
        if not self.synonyms:
            return text
        low = text.lower()
        extra = [v for k, v in FINANCE_SYNONYMS.items() if re.search(rf"\b{re.escape(k)}\b", low)]
        return f"{text} {' '.join(dict.fromkeys(extra))}" if extra else text

    def rewrite(self, query: str) -> RewrittenQuery:
        fixed = self.correct(query)
        sparse = self.expand(fixed)
        return RewrittenQuery(
            dense=fixed, sparse=normalize_numbers(sparse) if self.numbers else sparse
        )
