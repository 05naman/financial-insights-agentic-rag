from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def _fits_bcrypt(cls, v: str) -> str:
        if len(v.encode()) > MAX_PASSWORD_BYTES:
            raise ValueError(f"too long: use {MAX_PASSWORD_BYTES} characters or fewer")
        return v


class LoginRequest(BaseModel):
    """No bcrypt-length rule here: a too-long password is simply a wrong password (401), not an error."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
