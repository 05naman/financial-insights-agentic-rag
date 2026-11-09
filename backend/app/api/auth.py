import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import (
    CurrentUser,
    RefreshTokensRepoDep,
    UsersRepoDep,
    auth_rate_limited,
)
from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    dummy_verify,
    hash_password,
    hash_token,
    new_refresh_token,
    verify_password,
)
from app.schemas.auth import Credentials, LoginRequest, Token, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"
COOKIE_PATH = "/auth"  # the browser sends the cookie only to the auth routes
# Two tabs can refresh at the same moment; the loser presents a token that was "just" used. That is
# normal, not theft, so it is allowed for a few seconds. Later reuse means the token leaked.
REUSE_LEEWAY = timedelta(seconds=10)


def require_xhr(request: Request) -> None:
    """Refresh and logout run on a cookie. A custom header can't be added by another site's page
    without a CORS pre-flight (which we only allow for our own frontend), so this blocks CSRF."""
    if request.headers.get("x-requested-with") != "fetch":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Missing request header")


def _cookie_options() -> dict:
    s = get_settings()
    return {
        "httponly": True,  # JavaScript can't read it, so a script injected into the page can't steal it
        "secure": s.environment != "local",
        "samesite": s.cookie_samesite,
        "path": COOKIE_PATH,
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite hands back naive datetimes


async def _issue_refresh_token(
    response: Response, tokens: RefreshTokensRepoDep, user_id: int, family_id: str
) -> None:
    raw, hashed = new_refresh_token()
    days = get_settings().refresh_token_days
    await tokens.create(user_id, hashed, family_id, datetime.now(UTC) + timedelta(days=days))
    response.set_cookie(REFRESH_COOKIE, raw, max_age=days * 86400, **_cookie_options())


def _unauthorized(detail: str = "Session expired. Please sign in again.") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


@router.post(
    "/register",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(auth_rate_limited)],
)
async def register(body: Credentials, users: UsersRepoDep):
    if await users.get_by_email(body.email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = await users.create(body.email, await asyncio.to_thread(hash_password, body.password))
    logger.info("user registered id=%s", user.id)
    return UserOut(id=user.id, email=user.email)


@router.post("/login", response_model=Token, dependencies=[Depends(auth_rate_limited)])
async def login(
    body: LoginRequest, response: Response, users: UsersRepoDep, tokens: RefreshTokensRepoDep
):
    user = await users.get_by_email(body.email)
    if user is None:
        await asyncio.to_thread(dummy_verify, body.password)
    ok = user is not None and await asyncio.to_thread(
        verify_password, body.password, user.hashed_password
    )
    if not user or not ok:
        logger.warning(
            "login failed"
        )  # no email: avoids logging personal data and username probing
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    logger.info("login ok user=%s", user.id)
    await _issue_refresh_token(response, tokens, user.id, uuid.uuid4().hex)
    return Token(access_token=create_access_token(user.id))


@router.post(
    "/refresh",
    response_model=Token,
    dependencies=[Depends(auth_rate_limited), Depends(require_xhr)],
)
async def refresh(
    request: Request, response: Response, users: UsersRepoDep, tokens: RefreshTokensRepoDep
):
    """Trade the refresh cookie for a new access token and a new refresh cookie (rotation)."""
    raw = request.cookies.get(REFRESH_COOKIE)
    row = await tokens.get_by_hash(hash_token(raw)) if raw else None
    if row is None or row.revoked_at is not None or _aware(row.expires_at) <= datetime.now(UTC):
        raise _unauthorized()
    if row.used_at is None:
        await tokens.mark_used(row)
    elif datetime.now(UTC) - _aware(row.used_at) > REUSE_LEEWAY:
        await tokens.revoke_family(row.family_id)  # a used token came back: assume it was stolen
        logger.warning("refresh token reuse detected: family revoked user=%s", row.user_id)
        raise _unauthorized()
    user = await users.get(row.user_id)
    if user is None:
        raise _unauthorized()
    await _issue_refresh_token(response, tokens, user.id, row.family_id)
    return Token(access_token=create_access_token(user.id))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_xhr)])
async def logout(request: Request, tokens: RefreshTokensRepoDep) -> Response:
    """End this sign-in for real: the refresh token can never be used again."""
    raw = request.cookies.get(REFRESH_COOKIE)
    row = await tokens.get_by_hash(hash_token(raw)) if raw else None
    if row is not None:
        await tokens.revoke_family(row.family_id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, **_cookie_options())
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return UserOut(id=user.id, email=user.email)
