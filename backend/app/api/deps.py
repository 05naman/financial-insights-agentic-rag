from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container, get_container
from app.core.config import get_settings
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import decode_access_token
from app.db.models import User
from app.db.repositories import ChatRepository, DocumentRepository, UserRepository
from app.db.session import get_session

SessionDep = Annotated[AsyncSession, Depends(get_session)]
ContainerDep = Annotated[Container, Depends(get_container)]
_bearer = HTTPBearer(auto_error=False)

_limiter: SlidingWindowLimiter | None = None
_auth_limiter: SlidingWindowLimiter | None = None


def get_limiter() -> SlidingWindowLimiter:
    global _limiter
    if _limiter is None:
        _limiter = SlidingWindowLimiter(get_settings().rate_limit_per_minute)
    return _limiter


def reset_limiter() -> None:
    global _limiter, _auth_limiter
    _limiter = None
    _auth_limiter = None


def auth_rate_limited(request: Request) -> None:
    """Per-IP throttle on login/register: slows password guessing and CPU-heavy hashing floods."""
    global _auth_limiter
    if _auth_limiter is None:
        _auth_limiter = SlidingWindowLimiter(get_settings().auth_rate_limit_per_minute)
    ip = request.client.host if request.client else "unknown"
    if not _auth_limiter.allow(f"ip:{ip}"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many attempts. Please wait a moment.",
            headers={"Retry-After": str(_auth_limiter.retry_after(f"ip:{ip}"))},
        )


async def get_current_user(
    session: SessionDep,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is None:
        raise unauthorized
    user_id = decode_access_token(creds.credentials)
    user = await UserRepository(session).get(user_id) if user_id else None
    if user is None:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def rate_limited(user: CurrentUser) -> User:
    limiter = get_limiter()
    if not limiter.allow(f"user:{user.id}"):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Too many requests, slow down",
            headers={"Retry-After": str(limiter.retry_after(f"user:{user.id}"))},
        )
    return user


RateLimitedUser = Annotated[User, Depends(rate_limited)]


def documents_repo(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


def chat_repo(session: SessionDep) -> ChatRepository:
    return ChatRepository(session)


def users_repo(session: SessionDep) -> UserRepository:
    return UserRepository(session)


DocumentsRepoDep = Annotated[DocumentRepository, Depends(documents_repo)]
ChatRepoDep = Annotated[ChatRepository, Depends(chat_repo)]
UsersRepoDep = Annotated[UserRepository, Depends(users_repo)]
