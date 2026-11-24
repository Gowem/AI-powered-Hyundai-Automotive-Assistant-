"""Email/password authentication with an httpOnly JWT cookie."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.ratelimit import limiter
from app.schemas import LoginIn, RegisterIn, UserOut
from app.security import (
    clear_auth_cookie,
    create_access_token,
    dummy_verify,
    get_current_user,
    hash_password,
    set_auth_cookie,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request, response: Response, body: RegisterIn, db: AsyncSession = Depends(get_db)
) -> UserOut:
    if not settings.ALLOW_REGISTRATION:
        raise HTTPException(status_code=403, detail="Registration is disabled")
    existing = await db.scalar(select(User).where(User.email == body.email))
    if existing is not None:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=(body.full_name or "").strip() or None,
        last_login_at=datetime.now(UTC),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    set_auth_cookie(response, create_access_token(user.id))
    return UserOut.model_validate(user)


@router.post("/login", response_model=UserOut)
@limiter.limit("5/minute")
async def login(request: Request, response: Response, body: LoginIn, db: AsyncSession = Depends(get_db)) -> UserOut:
    user = await db.scalar(select(User).where(User.email == body.email))
    if user is None:
        dummy_verify()
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login_at = datetime.now(UTC)
    await db.commit()
    set_auth_cookie(response, create_access_token(user.id))
    return UserOut.model_validate(user)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> Response:
    response.status_code = 204
    clear_auth_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
