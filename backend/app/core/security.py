from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


MAX_PASSWORD_BYTES = 72  # bcrypt ignores or rejects anything longer


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    raw = password.encode()
    if len(raw) > MAX_PASSWORD_BYTES:
        return False  # can never match a stored hash; avoids a server error on over-long input
    return bcrypt.checkpw(raw, hashed.encode())


_dummy_hash: str | None = None


def dummy_verify(password: str) -> None:
    """Burn the same time as a real check, so unknown emails can't be told apart by response time."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password("not-a-real-password")
    verify_password(password, _dummy_hash)


def create_access_token(user_id: int) -> str:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(minutes=s.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, s.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().jwt_secret, algorithms=[ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
