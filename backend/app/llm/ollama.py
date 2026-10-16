import httpx

from app.llm.base import LLMProvider, Message
from app.llm.errors import to_llm_error


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.label = f"ollama:{model}"

    async def generate(
        self, messages: list[Message], *, temperature: float = 0.2, max_tokens: int = 1024
    ) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=body)
                resp.raise_for_status()
            return resp.json()["message"]["content"]
        except (httpx.HTTPError, KeyError) as e:
            raise to_llm_error(self.label, e) from e
