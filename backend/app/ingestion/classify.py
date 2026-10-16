"""Cheap, rule-based tagging used to prefer authoritative passages for money questions."""

import re

# the primary statements and summary tables: the authoritative source for a reported figure.
# (Notes pages restate numbers, but the statement itself is where a person expects to find them.)
_STATEMENT = re.compile(
    r"statements? of (profit and loss|profit or loss|income|comprehensive income|cash flows?|changes in equity)"
    r"|balance sheet|financial highlights|financial performance|key financials?|summary of (the )?financial",
    re.IGNORECASE,
)

_FINANCIAL_WORDS = re.compile(
    r"\b(revenue|income|profit|loss|earn\w*|sales|turnover|tax(es)?|margin|ebitda|eps|dividend|assets?|"
    r"liabilit\w+|borrowings?|debt|loans?|cash|equity|expenses?|expenditure|costs?|receipts|surplus|"
    r"net worth|capital|reserves|depreciation)\b",  # units (Rs, crore) are not metrics: a bare figure lookup is not boosted
    re.IGNORECASE,
)


def classify_chunk(text: str, chunk_type: str) -> str:
    """'statement' for a table that sits under a primary financial statement heading, else 'other'."""
    return "statement" if chunk_type == "table" and _STATEMENT.search(text[:300]) else "other"


def is_financial_query(query: str) -> bool:
    """True when the question is about reported money figures (so statement tables deserve a boost)."""
    return bool(_FINANCIAL_WORDS.search(query))
