import logging
import time

from app.core.config import Settings, get_settings
from app.llm.base import LLMError, LLMProvider, Message
from app.llm.gemini import GeminiProvider
from app.llm.groq import GroqProvider
from app.llm.ollama import OllamaProvider

logger = logging.getLogger(__name__)


COOLDOWN_CAP_SECONDS = 3600


class FallbackLLM:
    """Tries each provider in order and returns the first successful reply.

    A model whose quota is used up for the day (it asked us to wait a long time) is skipped for a while,
    so later calls go straight to the next model instead of failing first."""

    def __init__(self, providers: list[LLMProvider]):
        if not providers:
            raise ValueError("at least one LLM provider is required")
        self.providers = providers
        self._cooldown: dict[str, float] = {}

    def _usable(self) -> list[LLMProvider]:
        now = time.monotonic()
        ready = [p for p in self.providers if self._cooldown.get(_label(p), 0) <= now]
        return ready or self.providers  # if every model is cooling down, try them all anyway

    async def generate(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        errors: list[str] = []
        for provider in self._usable():
            try:
                return await provider.generate(
                    messages, temperature=temperature, max_tokens=max_tokens
                )
            except LLMError as e:
                logger.warning("provider %s failed: %s", _label(provider), e)
                errors.append(str(e))
                if e.retry_after and e.retry_after > 60:
                    wait = min(e.retry_after, COOLDOWN_CAP_SECONDS)
                    self._cooldown[_label(provider)] = time.monotonic() + wait
                    logger.warning(
                        "skipping %s for the next %.0f minutes", _label(provider), wait / 60
                    )
        raise LLMError("all providers failed: " + " | ".join(errors))


def _label(p: LLMProvider) -> str:
    return p.label or p.name


def build_provider(spec: str, s: Settings) -> LLMProvider:
    """`gemini`, `groq` or `ollama`, optionally with a model: `groq:qwen/qwen3.8-27b`."""
    kind, _, model = spec.partition(":")
    t = s.llm_timeout_seconds
    if kind == "gemini":
        return GeminiProvider(s.gemini_api_key, model or s.gemini_model, t, s.gemini_thinking_level)
    if kind == "groq":
        return GroqProvider(s.groq_api_key, model or s.groq_model, t)
    if kind == "ollama":
        return OllamaProvider(s.ollama_base_url, model or s.ollama_model, t)
    raise ValueError(f"unknown LLM provider: {spec}")


def get_llm(settings: Settings | None = None) -> FallbackLLM:
    s = settings or get_settings()
    return FallbackLLM([build_provider(n, s) for n in s.llm_providers])
