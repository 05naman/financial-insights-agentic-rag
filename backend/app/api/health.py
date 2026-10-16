import httpx
from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/health/deps")
async def health_deps() -> dict:
    """Reports whether Qdrant is reachable (Postgres/Redis checks arrive with their phases)."""
    s = get_settings()
    result = {}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{s.qdrant_url}/healthz")
            result["qdrant"] = "ok" if r.status_code == 200 else f"http {r.status_code}"
    except httpx.HTTPError:
        result["qdrant"] = "unreachable"
    return result
