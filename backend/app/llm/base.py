from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal


@dataclass
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


class LLMError(Exception):
    """Raised when a provider call fails or all providers fail.

    `retry_after` (seconds) is set when the provider said when it would accept calls again."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMProvider(ABC):
    name: str
    label: str = ""  # e.g. 'groq:qwen/qwen3.8-27b': the provider and model, for logs and usage

    @abstractmethod
    async def generate(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        """Return the model's text reply for the given chat messages."""
