import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import CurrentUser, UsersRepoDep, auth_rate_limited
from app.core.security import create_access_token, dummy_verify, hash_password, verify_password
from app.schemas.auth import Credentials, LoginRequest, Token, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


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
async def login(body: LoginRequest, users: UsersRepoDep):
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
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return UserOut(id=user.id, email=user.email)
