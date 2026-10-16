from dataclasses import dataclass, field


@dataclass
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass
class SearchFilters:
    tickers: list[str] = field(default_factory=list)
    fiscal_years: list[int] = field(default_factory=list)


@dataclass
class SearchHit:
    id: str
    score: float
    text: str
    ticker: str
    fiscal_year: int
    page: int
    chunk_type: str
    kind: str = "other"

    @property
    def citation(self) -> str:
        return f"{self.ticker} FY{self.fiscal_year}, p.{self.page}"
