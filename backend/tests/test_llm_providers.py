import json
import logging

import httpx
import pytest
import respx

from app.core.config import Settings
from app.llm import usage
from app.llm.base import LLMError, Message
from app.llm.factory import FallbackLLM, build_provider
from app.llm.groq import REASONING_HEADROOM, URL, GroqProvider
from app.llm.http import post_with_retry

MSG = [Message("user", "hi")]


def ok(content="hello", prompt=11, completion=3):
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": content}}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": completion},
        },
    )


def test_provider_specs_can_name_a_model():
    s = Settings(groq_model="default-model", gemini_model="gem-default", llm_providers=[])
    assert build_provider("groq:qwen/qwen3.8-27b", s).model == "qwen/qwen3.8-27b"
    assert build_provider("groq", s).model == "default-model"
    assert build_provider("gemini:gemini-3.6-flash", s).model == "gemini-3.6-flash"
    assert build_provider("groq:openai/gpt-oss-120b", s).label == "groq:openai/gpt-oss-120b"
    with pytest.raises(ValueError):
        build_provider("openai:gpt", s)


@respx.mock
async def test_reasoning_models_get_low_effort_and_headroom_but_plain_models_do_not():
    route = respx.post(URL).mock(return_value=ok())
    await GroqProvider("k", "openai/gpt-oss-120b").generate(MSG, max_tokens=500)
    body = json.loads(route.calls[0].request.content)
    assert body["reasoning_effort"] == "low" and body["max_tokens"] == 500 + REASONING_HEADROOM
    await GroqProvider("k", "some-lab/plain-chat-model").generate(MSG, max_tokens=500)
    body = json.loads(route.calls[1].request.content)
    assert (
        "reasoning_effort" not in body
        and "reasoning_format" not in body
        and body["max_tokens"] == 500
    )


@respx.mock
async def test_an_empty_reply_is_a_failure_so_the_next_model_gets_a_turn():
    respx.post(URL).mock(return_value=ok(content=""))
    with pytest.raises(LLMError, match="empty reply"):
        await GroqProvider("k", "openai/gpt-oss-20b").generate(MSG)


@respx.mock
async def test_token_usage_is_tallied_and_logged_without_any_content(caplog):
    usage.reset()
    caplog.set_level(logging.INFO)
    respx.post(URL).mock(return_value=ok(content="SECRET ANSWER TEXT", prompt=100, completion=7))
    await GroqProvider("k", "qwen/qwen3.8-27b").generate([Message("user", "SECRET QUESTION")])
    snap = usage.snapshot()["groq:qwen/qwen3.8-27b"]
    assert snap == {"calls": 1, "prompt_tokens": 100, "completion_tokens": 7, "total_tokens": 107}
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "tokens prompt=100 completion=7" in logged and "SECRET" not in logged


@respx.mock
async def test_a_long_retry_after_fails_fast_instead_of_waiting(monkeypatch):
    import app.llm.http as http

    slept = []

    async def record_sleep(s):
        slept.append(s)

    monkeypatch.setattr(http, "_sleep", record_sleep)
    route = respx.post("http://x.test/").mock(
        return_value=httpx.Response(429, headers={"retry-after": "7200"})
    )
    with pytest.raises(httpx.HTTPStatusError):
        await post_with_retry("http://x.test/", headers={}, json={}, timeout=5)
    assert slept == [] and route.call_count == 1  # daily quota: no waiting, no retries

    respx.post("http://y.test/").mock(
        side_effect=[httpx.Response(429, headers={"retry-after": "3"}), ok()]
    )
    await post_with_retry("http://y.test/", headers={}, json={}, timeout=5)
    assert slept == [3.0]  # a short wait (per-minute limit) is still waited out


@respx.mock
async def test_quota_error_carries_how_long_to_wait():
    respx.post(URL).mock(return_value=httpx.Response(429, headers={"retry-after": "5400"}))
    with pytest.raises(LLMError) as e:
        await GroqProvider("k", "qwen/qwen3.8-27b").generate(MSG)
    assert e.value.retry_after == 5400


class Scripted:
    def __init__(self, label, result):
        self.name, self.label, self.result, self.calls = label.split(":")[0], label, result, 0

    async def generate(self, messages, *, temperature=0.2, max_tokens=1024):
        self.calls += 1
        if isinstance(self.result, LLMError):
            raise self.result
        return self.result


async def test_exhausted_model_is_skipped_on_later_calls_but_a_blip_is_not():
    spent = Scripted("groq:a", LLMError("daily limit", retry_after=7200))
    blip = Scripted("groq:b", LLMError("overloaded", retry_after=5))
    good = Scripted("gemini:c", "answer")
    llm = FallbackLLM([spent, blip, good])
    assert await llm.generate(MSG) == "answer"
    assert await llm.generate(MSG) == "answer"
    assert spent.calls == 1  # asked once, then rested
    assert blip.calls == 2  # a brief hiccup does not bench a model


async def test_if_every_model_is_resting_they_are_all_tried_anyway():
    a = Scripted("groq:a", LLMError("daily limit", retry_after=7200))
    llm = FallbackLLM([a])
    with pytest.raises(LLMError, match="all providers failed"):
        await llm.generate(MSG)
    with pytest.raises(LLMError):
        await llm.generate(MSG)
    assert a.calls == 2


def test_agent_evidence_budget_comes_from_settings():
    from app.container import Container
    from tests.conftest import FakeEmbedder

    c = Container.__new__(Container)
    c.settings = Settings(
        agent_top_k=3, agent_max_evidence=4, agent_passage_chars=500, companies_file="/nonexistent"
    )
    c.llm, c.retriever, c.embedder = object(), object(), FakeEmbedder()
    cfg = c.qa_service({}).deps.config
    assert (cfg.top_k, cfg.max_evidence, cfg.max_passage_chars) == (3, 4, 500)


@respx.mock
async def test_qwen_reasoning_is_hidden_and_any_leaked_think_block_is_removed():
    route = respx.post(URL).mock(
        return_value=ok(content="<think>let me re-read the evidence</think>The answer is 42.")
    )
    out = await GroqProvider("k", "qwen/qwen3.8-27b").generate(MSG, max_tokens=300)
    body = json.loads(route.calls[0].request.content)
    assert body["reasoning_format"] == "hidden" and body["max_tokens"] == 300 + REASONING_HEADROOM
    assert out == "The answer is 42."
    await GroqProvider("k", "openai/gpt-oss-120b").generate(MSG)
    assert "reasoning_format" not in json.loads(route.calls[1].request.content)
