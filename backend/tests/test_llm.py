import httpx
import pytest
import respx

from app.llm.base import LLMError, Message
from app.llm.factory import FallbackLLM
from app.llm.groq import URL as GROQ_URL
from app.llm.groq import GroqProvider
from app.llm.ollama import OllamaProvider


@respx.mock
async def test_groq_parses_reply():
    respx.post(GROQ_URL).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})
    )
    out = await GroqProvider("key", "m").generate([Message("user", "yo")])
    assert out == "hi"


async def test_missing_key_raises():
    with pytest.raises(LLMError):
        await GroqProvider("", "m").generate([Message("user", "yo")])


@respx.mock
async def test_fallback_moves_to_next_provider():
    respx.post(GROQ_URL).mock(return_value=httpx.Response(500))
    respx.post("http://ollama.test/api/chat").mock(
        return_value=httpx.Response(200, json={"message": {"content": "from ollama"}})
    )
    llm = FallbackLLM([GroqProvider("key", "m"), OllamaProvider("http://ollama.test", "m")])
    assert await llm.generate([Message("user", "yo")]) == "from ollama"


@respx.mock
async def test_all_fail_raises():
    respx.post(GROQ_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(LLMError):
        await FallbackLLM([GroqProvider("key", "m")]).generate([Message("user", "yo")])


@respx.mock
async def test_retries_on_rate_limit_then_succeeds(monkeypatch):
    route = respx.post(GROQ_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"retry-after": "1"}),
            httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}),
        ]
    )
    assert await GroqProvider("key", "m").generate([Message("user", "yo")]) == "ok"
    assert route.call_count == 2
