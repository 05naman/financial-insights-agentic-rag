import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.llm import usage
from app.llm.base import LLMError, Message
from app.llm.factory import get_llm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/llm", tags=["llm"])


class LLMTestRequest(BaseModel):
    prompt: str = "Say hello in one short sentence."


@router.post("/test")
async def llm_test(req: LLMTestRequest, _: CurrentUser) -> dict:
    """Smoke test: sends a prompt through the provider fallback chain."""
    try:
        reply = await get_llm().generate([Message("user", req.prompt)], max_tokens=100)
    except LLMError as e:
        logger.warning("llm test failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail="The language model is unavailable or rate-limited. Please try again shortly.",
        ) from e
    return {"reply": reply}


@router.get("/usage")
async def llm_usage(_: CurrentUser) -> dict:
    """Tokens used per model since the server started (counts only). Watch it against free-tier daily limits."""
    return usage.snapshot()
