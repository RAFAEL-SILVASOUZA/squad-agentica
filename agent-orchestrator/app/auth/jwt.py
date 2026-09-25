"""JWT issuance and validation (access + refresh tokens).

Dono: auth-backend (FASE 3). Contrato §5:
- Claims: sub (ownerId), iat, exp; tipo distinto typ = "access" vs "refresh".
- Access: 15 min. Refresh: 7 dias.
- Rotação de refresh: refresh token usado é invalidado após uso.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings


def _utcnow() -> datetime:
    return datetime.now(UTC)


def create_access_token(sub: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a short-lived access token (15 min default)."""
    now = _utcnow()
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": sub,
        "typ": "access",
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(sub: str, extra_claims: dict[str, Any] | None = None) -> str:
    """Create a long-lived refresh token (7 days default)."""
    now = _utcnow()
    expire = now + timedelta(days=settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": sub,
        "typ": "refresh",
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_typ: str = "access") -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError on failure.

    Args:
        token: The JWT string.
        expected_typ: Expected token type ("access" or "refresh").

    Returns:
        The decoded payload dict.

    Raises:
        JWTError: If the token is invalid, expired, or has wrong type.
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != expected_typ:
        raise JWTError(f"Expected token type '{expected_typ}', got '{payload.get('typ')}'")
    return payload


def validate_access_token(token: str) -> dict[str, Any]:
    """Validate an access token. Returns payload or raises JWTError."""
    return decode_token(token, expected_typ="access")


def validate_refresh_token(token: str) -> dict[str, Any]:
    """Validate a refresh token. Returns payload or raises JWTError."""
    return decode_token(token, expected_typ="refresh")
