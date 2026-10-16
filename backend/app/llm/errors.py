import httpx

from app.llm.base import LLMError


def to_llm_error(prefix: str, exc: Exception) -> LLMError:
    """Wrap a failed provider call, keeping how long the provider asked us to wait (if it said)."""
    retry_after = None
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            retry_after = float(exc.response.headers.get("retry-after", ""))
        except ValueError:
            retry_after = None
    return LLMError(f"{prefix} failed: {exc}", retry_after=retry_after)
