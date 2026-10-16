from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    citations: list
    steps: list
    created_at: datetime


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: Literal["naive", "hybrid", "agentic"] = "agentic"


class CitationOut(BaseModel):
    ticker: str
    fiscal_year: int
    page: int
    text: str


class AnswerOut(BaseModel):
    answer: str
    citations: list[CitationOut]
    steps: list[dict]
    llm_calls: int
    mode: str
