"""Tests for MCP Admin endpoints.

Covers:
- GET /api/mcp/tokens: List tokens for user
- DELETE /api/mcp/tokens/{jti}: Revoke token
- GET /api/mcp/tools: List registered tools
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import MCPOAuthClient, MCPOAuthToken, User
from app.db.session import get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_app(session: AsyncSession, test_user: User):
    """FastAPI app with the MCP Admin router, wired to test session and user."""
    from app.api.mcp_admin import router as admin_router

    app = FastAPI()
    register_exception_handlers(app)
    # The router in mcp_admin.py has prefix /mcp. 
    # The main app adds /api, so here we just include it.
    app.include_router(admin_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield app


@pytest_asyncio.fixture
async def admin_client(admin_app):
    """HTTP client for the Admin app."""
    transport = ASGITransport(app=admin_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tokens_empty(admin_client: AsyncClient):
    resp = await admin_client.get("/api/mcp/tokens")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_tokens_with_data(
    admin_client: AsyncClient, session: AsyncSession, test_user: User
):
    # Setup: Create a client and a token
    client = MCPOAuthClient(
        id=uuid.uuid4(),
        client_id="test-client-1",
        client_name="Test Client One",
        redirect_uris=[],
        grant_types=[],
    )
    session.add(client)
    
    token = MCPOAuthToken(
        jti="token-123",
        user_id=test_user.id,
        client_id="test-client-1",
        scope="mcp:full",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(token)
    await session.commit()

    resp = await admin_client.get("/api/mcp/tokens")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["jti"] == "token-123"
    assert data[0]["client_name"] == "Test Client One"


@pytest.mark.asyncio
async def test_revoke_token_success(
    admin_client: AsyncClient, session: AsyncSession, test_user: User
):
    # Setup: Create a client and a token
    client = MCPOAuthClient(
        id=uuid.uuid4(),
        client_id="test-client-2",
        client_name="Test Client Two",
        redirect_uris=[],
        grant_types=[],
    )
    session.add(client)
    
    token = MCPOAuthToken(
        jti="revoke-me",
        user_id=test_user.id,
        client_id="test-client-2",
        scope="mcp:full",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(token)
    await session.commit()

    resp = await admin_client.delete("/api/mcp/tokens/revoke-me")
    assert resp.status_code == 200
    assert resp.json() == {"revoked": True}

    # Verify in DB
    result = await session.execute(
        select(MCPOAuthToken).where(MCPOAuthToken.jti == "revoke-me")
    )
    token_row = result.scalar_one()
    assert token_row.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_token_not_found(admin_client: AsyncClient):
    resp = await admin_client.delete("/api/mcp/tokens/non-existent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_revoke_token_wrong_user(
    admin_client: AsyncClient, session: AsyncSession, test_user: User
):
    # Setup: Token for another user
    other_user_id = uuid.uuid4()
    other_user = User(
        id=other_user_id,
        email="other@test.com",
        name="Other User",
        password_hash="hash",
        owner_id=other_user_id,
    )
    session.add(other_user)
    await session.commit()
    
    client = MCPOAuthClient(
        id=uuid.uuid4(),
        client_id="test-client-3",
        client_name="Test Client Three",
        redirect_uris=[],
        grant_types=[],
    )
    session.add(client)
    
    token = MCPOAuthToken(
        jti="other-token",
        user_id=other_user_id,
        client_id="test-client-3",
        scope="mcp:full",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    session.add(token)
    await session.commit()

    resp = await admin_client.delete("/api/mcp/tokens/other-token")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_tools(admin_client: AsyncClient):
    resp = await admin_client.get("/api/mcp/tools")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    # Should be non-empty if tools are registered in app.mcp_server.tools
    assert len(data) > 0
    for tool in data:
        assert "name" in tool
        assert "description" in tool


@pytest.mark.asyncio
async def test_unauthorized_access():
    # Create app without the user override
    from app.api.mcp_admin import router as admin_router
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(admin_router, prefix="/api")
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # No auth header provided, should return 401 (handled by get_current_user)
        resp = await client.get("/api/mcp/tokens")
        assert resp.status_code == 401
