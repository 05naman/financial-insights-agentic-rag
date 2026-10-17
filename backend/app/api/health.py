import asyncio

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import ContainerDep, CurrentUser, SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Public liveness probe for the host: says nothing about the system."""
    return {"status": "ok"}


@router.get("/health/deps")
async def health_deps(_: CurrentUser, session: SessionDep, container: ContainerDep) -> dict:
    """Logged-in check of the parts the app depends on: the database and the search index."""
    result: dict[str, str | int] = {}
    try:
        await session.execute(text("SELECT 1"))
        result["database"] = "ok"
    except Exception:
        result["database"] = "unreachable"
    try:
        result["search_index_passages"] = await asyncio.to_thread(container.store.count)
        result["search_index"] = "ok"
    except Exception:
        result["search_index"] = "unreachable"
    return result
