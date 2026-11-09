from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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


def normalize_database_url(url: str) -> str:
    """Accept a connection string as hosts hand it out (Neon, Heroku style) and make it work with asyncpg.

    - `postgres://` / `postgresql://` -> `postgresql+asyncpg://`
    - `sslmode=require` -> `ssl=require` (asyncpg's spelling); `channel_binding` is dropped (not supported)
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+asyncpg://" + url[len(prefix) :]
    if not url.startswith("postgresql+asyncpg://"):
        return url
    parts = urlsplit(url)
    query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "channel_binding":
            continue
        query.append(("ssl" if key == "sslmode" else key, value))
    return urlunsplit(parts._replace(query=urlencode(query)))


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        url = normalize_database_url(get_settings().database_url)
        if url.startswith("sqlite"):
            path = url.split("///", 1)[-1]
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        # pre-ping: a serverless Postgres (Neon) suspends when idle and drops pooled connections
        _engine = create_async_engine(
            url,
            hide_parameters=True,  # keep emails/hashes out of errors
            pool_pre_ping=not url.startswith("sqlite"),
        )
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
