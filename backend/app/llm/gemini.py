import httpx

from app.llm.base import LLMError, LLMProvider, Message
from app.llm.errors import to_llm_error
from app.llm.http import post_with_retry
from app.llm.usage import record

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(
        self, api_key: str, model: str, timeout: float = 60.0, thinking_level: str = "minimal"
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.thinking_level = thinking_level
        self.label = f"gemini:{model}"

    async def generate(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        system = "\n".join(m.content for m in messages if m.role == "system")
        contents = [
            {"role": "model" if m.role == "assistant" else "user", "parts": [{"text": m.content}]}
            for m in messages
            if m.role != "system"
        ]
        body: dict = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingLevel": self.thinking_level},
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        try:
            resp = await post_with_retry(
                f"{BASE_URL}/{self.model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json=body,
                timeout=self.timeout,
            )
            data = resp.json()
            usage = data.get("usageMetadata", {})
            record(self.label, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"))
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
            raise to_llm_error(self.label, e) from e
