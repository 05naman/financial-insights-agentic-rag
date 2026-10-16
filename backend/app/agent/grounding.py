import re
from dataclasses import dataclass, field

from app.retrieval.schemas import SearchHit

# matches "TCS FY2024 p.45" with or without brackets, so grouped "[A p.1, B p.2]" also works
CITATION_RE = re.compile(r"([A-Za-z0-9&\-]+) FY(\d{4}) p\.(\d+)")
_NUM_RE = re.compile(r"(?<!\w)\d[\d,]*(?:\.\d+)?(%?)")  # "Rs.9000" must still be read as 9000


@dataclass
class GroundingReport:
    unsupported_numbers: list[str] = field(default_factory=list)
    invalid_citations: list[str] = field(default_factory=list)
    has_citation: bool = True

    @property
    def ok(self) -> bool:
        return not self.unsupported_numbers and not self.invalid_citations and self.has_citation


def extract_numbers(text: str) -> list[tuple[str, float, bool]]:
    """Return (raw, value, has_percent) for each number, commas removed (Indian grouping ok)."""
    out = []
    for m in _NUM_RE.finditer(text):
        raw = m.group(0)
        try:
            out.append((raw, float(raw.rstrip("%").replace(",", "")), bool(m.group(1))))
        except ValueError:
            continue
    return out


def _is_trivial(value: float, raw: str, has_pct: bool) -> bool:
    is_int = "." not in raw
    if 1900 <= value <= 2100 and is_int and not has_pct:  # years
        return True
    return is_int and value <= 10 and not has_pct  # "3 years", "two"


def _matches(raw: str, value: float, support: list[float]) -> bool:
    """A number is supported if it equals a source/calculated number, or is that number rounded to the
    decimals shown (8.57 -> 8.6). It is NOT a fuzzy percentage match: 2,42,000 must not pass for 2,40,893."""
    decimals = len(raw.rstrip("%").partition(".")[2]) if "." in raw else 0
    tol = 0.5 * 10**-decimals + 1e-9
    return any(abs(value - s) <= tol for s in support)


def check_grounding(
    answer: str,
    evidence: list[SearchHit],
    calc_values: list[float],
    question: str = "",
    *,
    require_citation: bool = True,
) -> GroundingReport:
    report = GroundingReport()
    cited = CITATION_RE.findall(answer)
    allowed = {(h.ticker, str(h.fiscal_year), str(h.page)) for h in evidence}
    for t, y, p in cited:
        if (t.upper(), y, p) not in allowed:
            report.invalid_citations.append(f"[{t} FY{y} p.{p}]")
    report.has_citation = bool(cited) or not require_citation

    body = CITATION_RE.sub(" ", answer)
    support = [v for h in evidence for _, v, _ in extract_numbers(h.text)]
    support += calc_values
    support += [v for _, v, _ in extract_numbers(question)]
    for raw, value, pct in extract_numbers(body):
        if _is_trivial(value, raw, pct):
            continue
        if not _matches(raw, value, support):
            report.unsupported_numbers.append(raw)
    return report
