from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    fiscal_year: int
    filename: str
    page_count: int
    chunk_count: int
    status: str
    error: str | None
    created_at: datetime
