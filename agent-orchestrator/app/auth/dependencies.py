"""FastAPI dependencies for authentication.

Dono: auth-backend (FASE 3). Contrato §5:
- get_current_user: protege opt-out. Toda rota exige usuário exceto
  /api/auth/register, /api/auth/login, /api/auth/refresh e health checks.
- Um router novo criado por outro nó nasce protegido (dependência global
  com lista de exceções).
- Validação de token para WebSocket (função reutilizável).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import validate_access_token
from app.core.errors import AppError
from app.db.models import User
from app.db.session import get_db

# Paths that do NOT require authentication (opt-out list).
# Contrato §5: /api/auth/* (register/login/refresh) e health checks.
PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/refresh",
        "/health",
        "/api/health",
    }
)

# Bearer scheme (auto_error=False so we can return our own 401 envelope).
_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """FastAPI dependency: validates the Bearer token and returns the User.

    Raises AppError(401) if token is missing, invalid, or expired.
    """
    if credentials is None or not credentials.credentials:
        raise AppError(401, "unauthorized", "not_authenticated")

    try:
        payload = validate_access_token(credentials.credentials)
    except JWTError:
        raise AppError(401, "unauthorized", "not_authenticated") from None

    sub = payload.get("sub")
    if sub is None:
        raise AppError(401, "unauthorized", "not_authenticated")

    # Load user from DB.
    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise AppError(401, "unauthorized", "not_authenticated") from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise AppError(401, "unauthorized", "not_authenticated")

    return user


async def require_auth(request: Request) -> None:
    """Global dependency: enforces authentication on all routes except PUBLIC_PATHS.

    This is registered as a global dependency on the FastAPI app, so any new
    router automatically requires authentication. Routes in PUBLIC_PATHS are
    exempt.
    """
    path = request.url.path
    if path in PUBLIC_PATHS:
        return

    # Delegate to get_current_user logic (extracts and validates the token).
    # We call it directly to avoid double DB query if the route also uses
    # get_current_user as a parameter dependency.
    credentials = await _bearer(request)
    if credentials is None or not credentials.credentials:
        raise AppError(401, "unauthorized", "not_authenticated")

    try:
        validate_access_token(credentials.credentials)
    except JWTError:
        raise AppError(401, "unauthorized", "not_authenticated") from None


def validate_ws_token(token: str) -> dict:
    """Validate a JWT token for WebSocket handshake.

    Called by rt-websocket during the WebSocket connection handshake.
    Returns the decoded payload on success.

    Raises:
        AppError(401): If the token is invalid or expired.
    """
    try:
        payload = validate_access_token(token)
    except JWTError:
        raise AppError(401, "unauthorized", "not_authenticated") from None
    return payload
