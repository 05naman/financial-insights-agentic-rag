import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)
RETRY_STATUSES = {429, 500, 502, 503, 504}


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(
        seconds
    )  # a seam, so tests can skip backoff without patching asyncio itself


async def post_with_retry(
    url: str,
    *,
    headers: dict,
    json: dict,
    timeout: float,
    retries: int = 3,
    base_delay: float = 2.0,
    max_wait: float = 60.0,
) -> httpx.Response:
    """POST, retrying rate-limit/overload responses with exponential backoff (honours Retry-After)."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(retries + 1):
            resp = await client.post(url, headers=headers, json=json)
            if resp.status_code not in RETRY_STATUSES or attempt == retries:
                resp.raise_for_status()
                return resp
            try:
                delay = float(resp.headers.get("retry-after", ""))
            except ValueError:
                delay = base_delay * 2**attempt
            if delay > max_wait:
                # the provider wants minutes or hours: that is a used-up quota, not a blip.
                # Do not sit and wait; fail now so the next model can answer.
                resp.raise_for_status()
            delay = min(delay, 30.0)
            logger.warning("LLM returned %s, retrying in %.1fs", resp.status_code, delay)
            await _sleep(delay)
    raise RuntimeError("unreachable")
