from dataclasses import dataclass
from typing import Literal

ChunkType = Literal["text", "table"]


@dataclass
class PageContent:
    page: int  # 1-based
    text: str  # markdown; tables appear inline as `| a | b |` rows


@dataclass
class Chunk:
    id: str
    text: str
    ticker: str
    fiscal_year: int
    page: int
    chunk_type: ChunkType
    document_id: int
    kind: str = "other"  # 'statement' for primary financial statement tables

    @property
    def payload(self) -> dict:
        return {
            "text": self.text,
            "ticker": self.ticker,
            "fiscal_year": self.fiscal_year,
            "page": self.page,
            "chunk_type": self.chunk_type,
            "document_id": self.document_id,
            "section_kind": self.kind,
        }
