"""Password hashing, JWT handling and the current-user dependency."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, Request, Response, status
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import User

settings = get_settings()
password_hash = PasswordHash((Argon2Hasher(),))  # Argon2id by default

# Pre-computed hash used to equalise timing when the user does not exist.
_DUMMY_HASH = password_hash.hash("dummy-password-for-timing-1")

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(password, hashed)
    except Exception:  # noqa: BLE001 - malformed hashes must simply fail verification
        return False


def dummy_verify() -> None:
    verify_password("not-the-password", _DUMMY_HASH)


def create_access_token(user_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRES_MINUTES)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> uuid.UUID:
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["sub", "exp", "iat"]})
    return uuid.UUID(payload["sub"])


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="lax",
        path="/",
        max_age=settings.JWT_EXPIRES_MINUTES * 60,
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.COOKIE_NAME, path="/", httponly=True, secure=settings.COOKIE_SECURE, samesite="lax"
    )


_UNAUTHORISED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(settings.COOKIE_NAME)
    if not token:
        raise _UNAUTHORISED
    try:
        user_id = decode_token(token)
    except (jwt.PyJWTError, ValueError):
        raise _UNAUTHORISED from None
    user = await db.get(User, user_id)
    if user is None:
        raise _UNAUTHORISED
    return user
