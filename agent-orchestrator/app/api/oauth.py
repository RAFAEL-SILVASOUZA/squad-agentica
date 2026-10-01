"""OAuth 2.1 endpoints for the embedded MCP server.

Dono: mcp-oauth (Task 4). Implementa:
- RFC 9728: Protected Resource Metadata (GET /.well-known/oauth-protected-resource)
- RFC 8414: Authorization Server Metadata (GET /.well-known/oauth-authorization-server)
- RFC 7591: Dynamic Client Registration (POST /oauth/register)
- Authorization redirect (GET /oauth/authorize) -> 302 to portal consent page
- Consent endpoint (POST /api/mcp/consent) -> generates authorization code
- Token endpoint (POST /oauth/token) -> authorization_code + refresh_token grants
- Token revocation (POST /oauth/revoke) -> RFC 7009

Arquitetura: o backend NÃO valida a sessão do browser (não tem NEXTAUTH_SECRET).
O GET /oauth/authorize é apenas um redirect para a página de consent do portal.
O portal (com NEXTAUTH_SECRET) verifica o login e mostra o consent. Quando o
usuário autoriza, o portal chama POST /api/mcp/consent com o Bearer token do
usuário, que gera o código de autorização.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.db.models import MCPOAuthClient, MCPOAuthCode, MCPOAuthToken, User
from app.db.session import get_db

router = APIRouter(tags=["oauth"])

# Códigos de autorização expiram em 5 minutos.
_CODE_EXPIRY_MINUTES = 5


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    client_name: str = Field(min_length=1, max_length=200)
    redirect_uris: list[str] = Field(min_length=1)
    grant_types: list[str] = Field(default_factory=lambda: ["authorization_code", "refresh_token"])


class ConsentRequest(BaseModel):
    client_id: str
    redirect_uri: str
    scope: str = "mcp:full"
    code_challenge: str
    code_challenge_method: str = "S256"
    state: str | None = None
    resource: str | None = None


# ---------------------------------------------------------------------------
# MCP-specific JWT functions
# ---------------------------------------------------------------------------


def _mcp_audience() -> str:
    return f"{settings.mcp_base_url}/mcp/mcp"


def create_mcp_access_token(
    sub: str, scope: str, aud: str, jti: str, expires_hours: int
) -> str:
    """Create an MCP access token (typ="mcp")."""
    now = datetime.now(UTC)
    expire = now + timedelta(hours=expires_hours)
    payload: dict[str, Any] = {
        "sub": sub,
        "typ": "mcp",
        "aud": aud,
        "scope": scope,
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_mcp_refresh_token(sub: str, jti: str, expires_days: int) -> str:
    """Create an MCP refresh token (typ="mcp_refresh")."""
    now = datetime.now(UTC)
    expire = now + timedelta(days=expires_days)
    payload: dict[str, Any] = {
        "sub": sub,
        "typ": "mcp_refresh",
        "jti": jti,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_mcp_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate an MCP refresh token (typ="mcp_refresh")."""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("typ") != "mcp_refresh":
        raise JWTError(f"Expected token type 'mcp_refresh', got '{payload.get('typ')}'")
    return payload


def decode_mcp_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an MCP access token (typ="mcp")."""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
    if payload.get("typ") != "mcp":
        raise JWTError(f"Expected token type 'mcp', got '{payload.get('typ')}'")
    return payload


# ---------------------------------------------------------------------------
# PKCE validation
# ---------------------------------------------------------------------------


def validate_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Validate PKCE S256: base64url(sha256(code_verifier)) == code_challenge."""
    digest = hashlib.sha256(code_verifier.encode()).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return computed == code_challenge


# ---------------------------------------------------------------------------
# Helper: issue token pair
# ---------------------------------------------------------------------------


async def _issue_token_pair(
    db: AsyncSession,
    user_id: uuid.UUID,
    client_id: str,
    scope: str = "mcp:full",
) -> dict[str, Any]:
    """Generate and persist an MCP access + refresh token pair.

    Stores BOTH the access token jti and the refresh token jti in
    mcp_oauth_tokens so that revocation and rotation can track each.
    """
    access_jti = str(uuid.uuid4())
    refresh_jti = str(uuid.uuid4())
    aud = _mcp_audience()

    access_token = create_mcp_access_token(
        sub=str(user_id),
        scope=scope,
        aud=aud,
        jti=access_jti,
        expires_hours=settings.mcp_token_expire_hours,
    )
    refresh_token = create_mcp_refresh_token(
        sub=str(user_id),
        jti=refresh_jti,
        expires_days=settings.mcp_refresh_expire_days,
    )

    now = datetime.now(UTC)
    access_expires = now + timedelta(hours=settings.mcp_token_expire_hours)
    refresh_expires = now + timedelta(days=settings.mcp_refresh_expire_days)

    # Persist the access token record (for revocation tracking by MCP middleware).
    db.add(
        MCPOAuthToken(
            jti=access_jti,
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            expires_at=access_expires,
            revoked_at=None,
        )
    )
    # Persist the refresh token record (for rotation tracking).
    db.add(
        MCPOAuthToken(
            jti=refresh_jti,
            user_id=user_id,
            client_id=client_id,
            scope=scope,
            expires_at=refresh_expires,
            revoked_at=None,
        )
    )
    await db.commit()

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in": settings.mcp_token_expire_hours * 3600,
    }


# ---------------------------------------------------------------------------
# RFC 9728: Protected Resource Metadata
# ---------------------------------------------------------------------------


@router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata() -> dict[str, Any]:
    """RFC 9728: Protected Resource Metadata for the MCP server."""
    return {
        "resource": _mcp_audience(),
        "authorization_servers": [settings.mcp_base_url],
        "scopes_supported": ["mcp:full"],
    }


# ---------------------------------------------------------------------------
# RFC 8414: Authorization Server Metadata
# ---------------------------------------------------------------------------


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata() -> dict[str, Any]:
    """RFC 8414: Authorization Server Metadata."""
    return {
        "issuer": settings.mcp_base_url,
        "authorization_endpoint": f"{settings.mcp_base_url}/oauth/authorize",
        "token_endpoint": f"{settings.mcp_base_url}/oauth/token",
        "registration_endpoint": f"{settings.mcp_base_url}/oauth/register",
        "code_challenge_methods_supported": ["S256"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "response_types_supported": ["code"],
    }


# ---------------------------------------------------------------------------
# RFC 7591: Dynamic Client Registration
# ---------------------------------------------------------------------------


@router.post("/oauth/register", status_code=200)
async def register_client(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    """RFC 7591: Dynamic Client Registration.

    Generates a client_id (uuid4 string) and persists the client.
    """
    client_id = str(uuid.uuid4())
    client = MCPOAuthClient(
        id=uuid.uuid4(),
        client_id=client_id,
        client_name=body.client_name,
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
    )
    db.add(client)
    await db.commit()

    return {
        "client_id": client_id,
        "client_name": body.client_name,
        "redirect_uris": body.redirect_uris,
        "grant_types": body.grant_types,
    }


# ---------------------------------------------------------------------------
# GET /oauth/authorize (redirect to portal consent)
# ---------------------------------------------------------------------------


@router.get("/oauth/authorize", response_model=None)
async def authorize(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RedirectResponse | JSONResponse:
    """Authorization endpoint: validates client and redirects to portal consent.

    The portal (NextAuth) handles login check + consent UI.
    """
    q = request.query_params
    client_id = q.get("client_id", "")
    redirect_uri = q.get("redirect_uri", "")
    scope = q.get("scope", "mcp:full")
    code_challenge = q.get("code_challenge", "")
    code_challenge_method = q.get("code_challenge_method", "S256")
    state = q.get("state")
    resource = q.get("resource")

    # Validate client exists.
    if not client_id:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "error_description": "Missing client_id"},
        )
    result = await db.execute(
        select(MCPOAuthClient).where(MCPOAuthClient.client_id == client_id)
    )
    client = result.scalar_one_or_none()
    if client is None:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "error_description": "Unknown client_id"},
        )

    # Build redirect to portal consent page with all params preserved.
    params: dict[str, str] = {
        "client_id": client_id,
        "client_name": client.client_name,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": code_challenge_method,
    }
    if state:
        params["state"] = state
    if resource:
        params["resource"] = resource

    consent_url = f"{settings.portal_base_url}/mcp-consent?{urlencode(params)}"
    return RedirectResponse(url=consent_url, status_code=302)


# ---------------------------------------------------------------------------
# POST /api/mcp/consent (called by portal consent page)
# ---------------------------------------------------------------------------


@router.post("/api/mcp/consent", status_code=200, response_model=None)
async def consent(
    body: ConsentRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any] | JSONResponse:
    """Consent endpoint: generates a one-time authorization code.

    Called by the portal's consent page with the user's Bearer token.
    Validates the client and redirect_uri, then stores the code.
    """
    # Validate client exists.
    result = await db.execute(
        select(MCPOAuthClient).where(MCPOAuthClient.client_id == body.client_id)
    )
    client = result.scalar_one_or_none()
    if client is None:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_request", "error_description": "Unknown client_id"},
        )

    # Validate redirect_uri is registered for this client.
    if body.redirect_uri not in client.redirect_uris:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_request",
                "error_description": "redirect_uri not registered for this client",
            },
        )

    # Generate and store the authorization code.
    code = str(uuid.uuid4())
    auth_code = MCPOAuthCode(
        code=code,
        user_id=user.id,
        client_id=body.client_id,
        redirect_uri=body.redirect_uri,
        code_challenge=body.code_challenge,
        code_challenge_method=body.code_challenge_method,
        scope=body.scope,
        resource=body.resource,
    )
    db.add(auth_code)
    await db.commit()

    return {"code": code}


# ---------------------------------------------------------------------------
# POST /oauth/token
# ---------------------------------------------------------------------------


@router.post("/oauth/token", status_code=200)
async def token(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """Token endpoint: handles authorization_code and refresh_token grants.

    Accepts both form-encoded and JSON bodies.
    """
    # Parse body (form-encoded or JSON).
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data: dict[str, Any] = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    grant_type = data.get("grant_type", "")

    if grant_type == "authorization_code":
        return await _handle_authorization_code(data, db)
    elif grant_type == "refresh_token":
        return await _handle_refresh_token(data, db)
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "unsupported_grant_type",
                "error_description": f"Unsupported grant_type: {grant_type}",
            },
        )


async def _handle_authorization_code(
    data: dict[str, Any], db: AsyncSession
) -> JSONResponse:
    """Handle the authorization_code grant."""
    code = data.get("code", "")
    code_verifier = data.get("code_verifier", "")
    client_id = data.get("client_id", "")
    redirect_uri = data.get("redirect_uri", "")

    # Look up the authorization code.
    result = await db.execute(
        select(MCPOAuthCode).where(MCPOAuthCode.code == code)
    )
    auth_code = result.scalar_one_or_none()

    if auth_code is None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Authorization code not found",
            },
        )

    # Check if code was already used.
    if auth_code.used_at is not None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Authorization code already used",
            },
        )

    # Check if code is expired (5 minutes).
    created_at = auth_code.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if datetime.now(UTC) - created_at > timedelta(minutes=_CODE_EXPIRY_MINUTES):
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Authorization code expired",
            },
        )

    # Validate PKCE.
    if not validate_pkce(code_verifier, auth_code.code_challenge):
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "PKCE validation failed",
            },
        )

    # Validate redirect_uri matches.
    if redirect_uri and redirect_uri != auth_code.redirect_uri:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "redirect_uri mismatch",
            },
        )

    # Validate client_id matches.
    if client_id and client_id != auth_code.client_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "client_id mismatch",
            },
        )

    # Mark code as used.
    auth_code.used_at = datetime.now(UTC)
    await db.commit()

    # Issue token pair.
    tokens = await _issue_token_pair(
        db,
        user_id=auth_code.user_id,
        client_id=auth_code.client_id,
        scope=auth_code.scope,
    )
    return JSONResponse(status_code=200, content=tokens)


async def _handle_refresh_token(
    data: dict[str, Any], db: AsyncSession
) -> JSONResponse:
    """Handle the refresh_token grant (with rotation)."""
    refresh_token = data.get("refresh_token", "")
    client_id = data.get("client_id", "")

    # Decode and validate the refresh token.
    try:
        payload = decode_mcp_refresh_token(refresh_token)
    except JWTError:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Invalid or expired refresh token",
            },
        )

    sub = payload.get("sub")
    jti = payload.get("jti")
    if not sub or not jti:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Invalid refresh token payload",
            },
        )

    # Look up the refresh token record in mcp_oauth_tokens.
    # _issue_token_pair stores both the access and refresh jti values,
    # so the refresh jti is always present here for rotation tracking.
    result = await db.execute(
        select(MCPOAuthToken).where(MCPOAuthToken.jti == jti)
    )
    token_record = result.scalar_one_or_none()

    if token_record is None:
        # Refresh token jti not found: either never stored or already cleaned up.
        # Treat as invalid.
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Refresh token not recognized",
            },
        )

    if token_record.revoked_at is not None:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "Refresh token already revoked (rotation)",
            },
        )

    # Validate client_id matches.
    if client_id and client_id != token_record.client_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "invalid_grant",
                "error_description": "client_id mismatch",
            },
        )

    # Revoke the old refresh token (rotation).
    token_record.revoked_at = datetime.now(UTC)

    # Issue new token pair.
    user_id = uuid.UUID(sub)
    tokens = await _issue_token_pair(
        db,
        user_id=user_id,
        client_id=token_record.client_id,
        scope=token_record.scope,
    )
    await db.commit()

    return JSONResponse(status_code=200, content=tokens)


# ---------------------------------------------------------------------------
# POST /oauth/revoke (RFC 7009)
# ---------------------------------------------------------------------------


@router.post("/oauth/revoke", status_code=200)
async def revoke(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JSONResponse:
    """RFC 7009: Token Revocation.

    Always returns 200, even if the token is unknown (per spec).
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data: dict[str, Any] = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    token_value = data.get("token", "")
    if not token_value:
        return JSONResponse(status_code=200, content={})

    # Try to decode the token (could be access or refresh).
    # Skip audience validation: we only need the jti for revocation.
    try:
        payload = jwt.decode(
            token_value,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        # Unknown/invalid token: still return 200 per RFC 7009.
        return JSONResponse(status_code=200, content={})

    jti = payload.get("jti")
    if not jti:
        return JSONResponse(status_code=200, content={})

    # Revoke the token (if it exists in mcp_oauth_tokens).
    result = await db.execute(
        select(MCPOAuthToken).where(MCPOAuthToken.jti == jti)
    )
    token_record = result.scalar_one_or_none()
    if token_record is not None and token_record.revoked_at is None:
        token_record.revoked_at = datetime.now(UTC)
        await db.commit()

    return JSONResponse(status_code=200, content={})
