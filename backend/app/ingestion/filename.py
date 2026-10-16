import re
from dataclasses import dataclass

_PATTERN = re.compile(r"^(?P<ticker>[A-Za-z0-9&\-]+)_FY(?P<year>\d{4})\.pdf$", re.IGNORECASE)


class InvalidFilenameError(ValueError):
    pass


@dataclass(frozen=True)
class ReportName:
    ticker: str
    fiscal_year: int


def parse_report_filename(filename: str) -> ReportName:
    """`TCS_FY2024.pdf` -> ReportName('TCS', 2024)."""
    m = _PATTERN.match(filename)
    if not m:
        raise InvalidFilenameError(f"'{filename}' does not match TICKER_FYyyyy.pdf")
    return ReportName(m["ticker"].upper(), int(m["year"]))
