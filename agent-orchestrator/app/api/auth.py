"""Auth API router: register, login, refresh, me.

Dono: auth-backend (FASE 3). Contrato §5:
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/refresh
- GET /api/auth/me
- Rate limiting do login (5/min per IP), 429 no envelope.
- Mensagens genéricas (não revelam se o e-mail existe).
- Nunca logar senha nem token.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_refresh_token,
)
from app.auth.rate_limiter import login_rate_limiter
from app.auth.refresh_store import refresh_store
from app.auth.schemas import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Register a new user. Returns 409 if email already exists."""
    # Check if email already exists.
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none() is not None:
        raise AppError(409, "conflict", "email_already_exists")

    password_hash = hash_password(body.password)
    user = User(
        id=uuid.uuid4(),
        email=body.email,
        name=body.name,
        password_hash=password_hash,
        owner_id=uuid.uuid4(),  # Will be set to user.id after insert.
    )
    # V1: owner_id = id do próprio user (contrato §5, seed pattern).
    user.owner_id = user.id
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return UserResponse(id=str(user.id), email=user.email, name=user.name)


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Login with email/password. Returns access + refresh tokens.

    Rate limited: 5 requests/min per (IP, email). Generic error message (does
    not reveal if the email exists).
    """
    # O login real chega pelo authorize() do NextAuth, no servidor do portal:
    # o IP é sempre o do container do portal. Só por IP, todos os usuários
    # dividiam 5 logins/min (o 6º login do minuto falhava para qualquer um).
    # A chave inclui o e-mail: segue limitando força bruta numa conta.
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"{client_ip}:{body.email.strip().lower()}"
    allowed, retry_after = login_rate_limiter.is_allowed(rate_key)
    if not allowed:
        raise AppError(
            429,
            "rate_limited",
            "rate_limited",
            {"retryAfter": retry_after},
        )

    # Look up user by email.
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Generic error: same message for wrong email and wrong password.
    if user is None or not verify_password(body.password, user.password_hash):
        raise AppError(401, "unauthorized", "invalid_credentials")

    # Issue tokens.
    sub = str(user.id)
    access_token = create_access_token(sub)
    refresh_token = create_refresh_token(sub)

    # Register refresh token in the rotation store.
    try:
        refresh_payload = decode_token(refresh_token, expected_typ="refresh")
        refresh_store.issue(refresh_payload["jti"], sub)
    except JWTError:
        # Should not happen with a freshly created token.
        pass

    return TokenResponse(
        accessToken=access_token,
        refreshToken=refresh_token,
        tokenType="Bearer",
        expiresIn=settings.access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Rotate the refresh token and issue a new access + refresh pair.

    The old refresh token is invalidated after use (rotation).
    Reusing an already-rotated token returns 401.
    """
    try:
        payload = validate_refresh_token(body.refresh_token)
    except JWTError:
        raise AppError(401, "unauthorized", "invalid_refresh_token") from None

    sub = payload.get("sub")
    jti = payload.get("jti")
    if sub is None or jti is None:
        raise AppError(401, "unauthorized", "invalid_refresh_token")

    # Verify user still exists.
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise AppError(401, "unauthorized", "invalid_refresh_token") from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError(401, "unauthorized", "invalid_refresh_token")

    # Rotate: mark old as used, issue new.
    new_access = create_access_token(sub)
    new_refresh = create_refresh_token(sub)

    try:
        new_payload = decode_token(new_refresh, expected_typ="refresh")
        new_jti = new_payload["jti"]
    except JWTError:
        raise AppError(500, "internal error", "internal_error") from None

    rotated = refresh_store.rotate(jti, new_jti, sub)
    if not rotated:
        # Replay detected: old token was already used.
        raise AppError(401, "unauthorized", "refresh_token_reused")

    return TokenResponse(
        accessToken=new_access,
        refreshToken=new_refresh,
        tokenType="Bearer",
        expiresIn=settings.access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Return the current authenticated user's profile."""
    return UserResponse(id=str(user.id), email=user.email, name=user.name)
