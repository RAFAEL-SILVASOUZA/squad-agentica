"""Tests for MCP OAuth 2.1 endpoints (Task 4).

Covers:
- RFC 9728 protected resource metadata
- RFC 8414 authorization server metadata
- RFC 7591 dynamic client registration
- Authorization redirect (GET /oauth/authorize)
- Consent endpoint (POST /api/mcp/consent)
- Token endpoint (POST /oauth/token) with PKCE
- Refresh token rotation
- Token revocation (POST /oauth/revoke)
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.db.models import MCPOAuthClient, MCPOAuthToken, User
from app.db.session import get_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pkce_pair() -> tuple[str, str]:
    """Generate a valid PKCE code_verifier / code_challenge (S256) pair."""
    verifier = base64.urlsafe_b64encode(uuid.uuid4().bytes + uuid.uuid4().bytes).rstrip(b"=").decode()
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return verifier, challenge


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def oauth_app(session: AsyncSession, test_user: User):
    """FastAPI app with the OAuth router, wired to the test session and user."""
    from app.api.oauth import router as oauth_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(oauth_router)

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield app


@pytest_asyncio.fixture
async def oauth_client(oauth_app):
    """HTTP client for the OAuth app."""
    transport = ASGITransport(app=oauth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def registered_client(session: AsyncSession, oauth_client: AsyncClient) -> MCPOAuthClient:
    """Registers an OAuth client via the API and returns the DB row."""
    client_id = str(uuid.uuid4())
    redirect_uri = "http://localhost:3000/callback"
    resp = await oauth_client.post(
        "/oauth/register",
        json={
            "client_name": "Test Client",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["client_id"] == client_id or "client_id" in data

    # Fetch from DB
    result = await session.execute(
        select(MCPOAuthClient).where(MCPOAuthClient.client_id == data["client_id"])
    )
    client = result.scalar_one()
    return client


@pytest_asyncio.fixture
async def auth_code(
    session: AsyncSession,
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
) -> tuple[str, str, str]:
    """Creates an authorization code via the consent endpoint.

    Returns (code, code_verifier, code_challenge).
    """
    verifier, challenge = _pkce_pair()
    redirect_uri = registered_client.redirect_uris[0]

    resp = await oauth_client.post(
        "/api/mcp/consent",
        json={
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp:full",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test-state",
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    code = resp.json()["code"]
    return code, verifier, challenge


# ---------------------------------------------------------------------------
# RFC 9728: Protected Resource Metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protected_resource_metadata(oauth_client: AsyncClient):
    resp = await oauth_client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == f"{settings.mcp_base_url}/mcp/mcp"
    assert data["authorization_servers"] == [settings.mcp_base_url]
    assert "mcp:full" in data["scopes_supported"]


# ---------------------------------------------------------------------------
# RFC 8414: Authorization Server Metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorization_server_metadata(oauth_client: AsyncClient):
    resp = await oauth_client.get("/.well-known/oauth-authorization-server")
    assert resp.status_code == 200
    data = resp.json()
    assert data["issuer"] == settings.mcp_base_url
    assert data["authorization_endpoint"] == f"{settings.mcp_base_url}/oauth/authorize"
    assert data["token_endpoint"] == f"{settings.mcp_base_url}/oauth/token"
    assert data["registration_endpoint"] == f"{settings.mcp_base_url}/oauth/register"
    assert "S256" in data["code_challenge_methods_supported"]
    assert "authorization_code" in data["grant_types_supported"]
    assert "code" in data["response_types_supported"]


# ---------------------------------------------------------------------------
# RFC 7591: Dynamic Client Registration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_client(oauth_client: AsyncClient):
    resp = await oauth_client.post(
        "/oauth/register",
        json={
            "client_name": "My App",
            "redirect_uris": ["http://localhost:3000/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "client_id" in data
    assert data["client_name"] == "My App"
    assert data["redirect_uris"] == ["http://localhost:3000/callback"]
    assert data["grant_types"] == ["authorization_code", "refresh_token"]


# ---------------------------------------------------------------------------
# GET /oauth/authorize
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authorize_redirects_to_consent(
    oauth_client: AsyncClient, registered_client: MCPOAuthClient
):
    verifier, challenge = _pkce_pair()
    redirect_uri = registered_client.redirect_uris[0]
    resp = await oauth_client.get(
        "/oauth/authorize",
        params={
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp:full",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "xyz",
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 302
    location = resp.headers["location"]
    assert "/mcp-consent" in location
    assert registered_client.client_id in location


@pytest.mark.asyncio
async def test_authorize_invalid_client(oauth_client: AsyncClient):
    resp = await oauth_client.get(
        "/oauth/authorize",
        params={
            "client_id": "nonexistent-client",
            "redirect_uri": "http://localhost/callback",
            "scope": "mcp:full",
            "code_challenge": "abc",
            "code_challenge_method": "S256",
            "state": "xyz",
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/mcp/consent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consent_creates_code(
    oauth_client: AsyncClient, test_user: User, registered_client: MCPOAuthClient
):
    verifier, challenge = _pkce_pair()
    redirect_uri = registered_client.redirect_uris[0]
    resp = await oauth_client.post(
        "/api/mcp/consent",
        json={
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "scope": "mcp:full",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test-state",
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "code" in data
    assert len(data["code"]) > 0


@pytest.mark.asyncio
async def test_consent_invalid_redirect_uri(
    oauth_client: AsyncClient, test_user: User, registered_client: MCPOAuthClient
):
    verifier, challenge = _pkce_pair()
    resp = await oauth_client.post(
        "/api/mcp/consent",
        json={
            "client_id": registered_client.client_id,
            "redirect_uri": "http://evil.com/callback",
            "scope": "mcp:full",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "test-state",
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /oauth/token (authorization_code grant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_valid_code(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, verifier, challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == settings.mcp_token_expire_hours * 3600


@pytest.mark.asyncio
async def test_token_wrong_pkce(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, _verifier, _challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": "wrong-verifier-value",
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_token_reused_code(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, verifier, _challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]

    # First use: should succeed.
    resp1 = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp1.status_code == 200, resp1.text

    # Second use: should fail (code already used).
    resp2 = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp2.status_code == 400
    data = resp2.json()
    assert data["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_token_nonexistent_code(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
):
    verifier, challenge = _pkce_pair()
    redirect_uri = registered_client.redirect_uris[0]
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "nonexistent-code",
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["error"] == "invalid_grant"


# ---------------------------------------------------------------------------
# POST /oauth/token (refresh_token grant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_refresh(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, verifier, _challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]

    # Get initial tokens.
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    refresh_token = tokens["refresh_token"]

    # Use refresh token.
    resp2 = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": registered_client.client_id,
        },
    )
    assert resp2.status_code == 200, resp2.text
    new_tokens = resp2.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    assert new_tokens["access_token"] != tokens["access_token"]
    assert new_tokens["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_token_refresh_reused(
    oauth_client: AsyncClient,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, verifier, _challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]

    # Get initial tokens.
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    refresh_token = tokens["refresh_token"]

    # First refresh: should succeed.
    resp2 = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": registered_client.client_id,
        },
    )
    assert resp2.status_code == 200, resp2.text

    # Reuse the same refresh token: should fail (already rotated).
    resp3 = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": registered_client.client_id,
        },
    )
    assert resp3.status_code == 400
    data = resp3.json()
    assert data["error"] == "invalid_grant"


# ---------------------------------------------------------------------------
# POST /oauth/revoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_token(
    oauth_client: AsyncClient,
    session: AsyncSession,
    test_user: User,
    registered_client: MCPOAuthClient,
    auth_code: tuple[str, str, str],
):
    code, verifier, _challenge = auth_code
    redirect_uri = registered_client.redirect_uris[0]

    # Get tokens.
    resp = await oauth_client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": registered_client.client_id,
            "redirect_uri": redirect_uri,
            "resource": f"{settings.mcp_base_url}/mcp/mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    tokens = resp.json()
    access_token = tokens["access_token"]

    # Revoke the access token.
    resp2 = await oauth_client.post(
        "/oauth/revoke",
        data={"token": access_token},
    )
    assert resp2.status_code == 200

    # Verify the token is revoked in the DB.
    from jose import jwt as jose_jwt

    payload = jose_jwt.decode(
        access_token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        audience=f"{settings.mcp_base_url}/mcp/mcp",
    )
    jti = payload["jti"]
    result = await session.execute(
        select(MCPOAuthToken).where(MCPOAuthToken.jti == jti)
    )
    token_row = result.scalar_one()
    assert token_row.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_unknown_token(oauth_client: AsyncClient):
    """RFC 7009: always return 200, even for unknown tokens."""
    resp = await oauth_client.post(
        "/oauth/revoke",
        data={"token": "some-unknown-token"},
    )
    assert resp.status_code == 200
