import re

import httpx

from app.llm.base import LLMError, LLMProvider, Message
from app.llm.errors import to_llm_error
from app.llm.http import post_with_retry
from app.llm.usage import record

URL = "https://api.groq.com/openai/v1/chat/completions"
REASONING_HEADROOM = (
    600  # reasoning models "think" first; those hidden tokens count against max_tokens
)
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


class GroqProvider(LLMProvider):
    name = "groq"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.label = f"groq:{model}"
        self.reasoning_model = model.startswith("openai/gpt-oss")
        self.thinking_model = (
            "qwen" in model
        )  # thinks too; its reasoning must stay out of the answer

    async def generate(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")
        body: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self.reasoning_model:
            body["reasoning_effort"] = "low"  # default effort can spend the whole budget thinking
        if self.thinking_model:
            body["reasoning_format"] = (
                "hidden"  # otherwise its chain of thought leaks into the reply
            )
        if self.reasoning_model or self.thinking_model:
            body["max_tokens"] = max_tokens + REASONING_HEADROOM
        try:
            resp = await post_with_retry(
                URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
                timeout=self.timeout,
            )
            data = resp.json()
            usage = data.get("usage", {})
            record(self.label, usage.get("prompt_tokens"), usage.get("completion_tokens"))
            content = _THINK.sub("", data["choices"][0]["message"].get("content") or "").strip()
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise to_llm_error(self.label, e) from e
        if not content.strip():
            raise LLMError(
                f"{self.label} returned an empty reply (its token budget went on thinking)"
            )
        return content
