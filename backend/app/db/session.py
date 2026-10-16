from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = get_settings().database_url
        if url.startswith("sqlite"):
            path = url.split("///", 1)[-1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(url, hide_parameters=True)  # keep emails/hashes out of errors
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def init_db() -> None:
    from app.db import models  # noqa: F401  (register tables)

    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def reset_engine() -> None:
    """For tests: drop the cached engine so a new DATABASE_URL takes effect."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
