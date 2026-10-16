"""Deterministic company/year detection for search queries.

The agent's planner (an LLM) normally supplies company and year filters. This parser does the same job with
plain rules, so search still narrows to the right report when no LLM is available or it returns nothing.
It understands: tickers (bhit), company names (Bharat Infotech Limited), small typos (Bharat Infotec),
and years written as FY2024, FY24, 2023-24, 2023-2024, "March 31, 2024" or a bare 2024.
"""

import re
from difflib import SequenceMatcher

from app.retrieval.schemas import SearchFilters

_SUFFIXES = {"limited", "ltd", "inc", "pvt", "private", "plc", "corp", "corporation"}
_WORD = re.compile(r"[a-z0-9&]+")


def _aliases(ticker: str, name: str | None) -> list[list[str]]:
    """Word lists that identify a company: its ticker, full name, and name without 'Limited'."""
    out = [[ticker.lower()]]
    if name:
        words = _WORD.findall(name.lower())
        core = [w for w in words if w not in _SUFFIXES]
        out += [words, core] if core != words else [words]
    return out


def _first_word(name: str | None) -> str | None:
    core = [w for w in _WORD.findall((name or "").lower()) if w not in _SUFFIXES]
    return core[0] if core and len(core[0]) >= 5 else None


def _similar(a: str, b: str) -> bool:
    return a == b or (len(a) >= 5 and len(b) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.86)


def detect_companies(query: str, names: dict[str, str], tickers: list[str]) -> list[str]:
    words = _WORD.findall(query.lower())
    # a distinctive first word ("Sagar") also identifies a company, but only if no other company shares it
    firsts = [_first_word(names.get(t)) for t in tickers]
    found: list[str] = []
    for t, first in zip(tickers, firsts, strict=True):
        extra = [[first]] if first and firsts.count(first) == 1 else []
        for alias in [*_aliases(t, names.get(t)), *extra]:
            n = len(alias)
            if any(
                all(_similar(words[i + j], alias[j]) for j in range(n))
                for i in range(len(words) - n + 1)
            ):
                found.append(t)
                break
    return found


_RANGE = re.compile(r"\b(20\d{2})\s*[-–/]\s*(\d{4}|\d{2})\b")
_FY4 = re.compile(r"\bfy\s*[-']?\s*(20\d{2})\b", re.I)
_FY2 = re.compile(r"\bfy\s*[-']?\s*(\d{2})\b", re.I)
_MARCH = re.compile(r"\bmarch\s*(?:31(?:st)?,?\s*)?(20\d{2})\b", re.I)
_BARE = re.compile(r"(?<![\d,.])(20\d{2})(?![\d,]|\.\d)")


def detect_years(query: str) -> list[int]:
    """Fiscal years mentioned. FY ends in March, so '2023-24' and 'March 2024' both mean FY2024."""
    years: list[int] = []

    def add(y: int) -> None:
        if 1990 <= y <= 2100 and y not in years:
            years.append(y)

    rest = query
    for m in _RANGE.finditer(query):
        end = m.group(2)
        add(int(end) if len(end) == 4 else int(m.group(1)[:2] + end))
    rest = _RANGE.sub(" ", rest)
    for pat in (_FY4, _MARCH):
        for m in pat.finditer(rest):
            add(int(m.group(1)))
        rest = pat.sub(" ", rest)
    for m in _FY2.finditer(rest):
        add(2000 + int(m.group(1)))
    rest = _FY2.sub(" ", rest)
    for m in _BARE.finditer(rest):
        add(int(m.group(1)))
    return sorted(years)


def parse_query(query: str, names: dict[str, str], tickers: list[str]) -> SearchFilters:
    """Companies and fiscal years mentioned in `query` (empty lists when none are found)."""
    return SearchFilters(
        tickers=detect_companies(query, names, tickers), fiscal_years=detect_years(query)
    )
