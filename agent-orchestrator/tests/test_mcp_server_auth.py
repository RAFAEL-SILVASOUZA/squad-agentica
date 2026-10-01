"""Testes do middleware ASGI de autenticação MCP (Task 3).

Cobre:
- Request sem Authorization → 401 com WWW-Authenticate
- Token malformado → 401
- Token expirado → 401
- Token válido (typ="mcp", aud correto, jti no banco, user existe) → não 401
- Token revogado → 401
- Token com aud errado → 401
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.db.models import MCPOAuthClient, MCPOAuthToken, User
from app.mcp_server.auth import MCPAuthMiddleware


# ---------------------------------------------------------------------------
# App ASGI mínimo para testar o middleware em isolamento.
# ---------------------------------------------------------------------------


async def _dummy_app(scope, receive, send):
    """App ASGI que responde 200 para qualquer request HTTP."""
    if scope["type"] == "http":
        body = b'{"ok":true}'
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})
    else:
        # lifespan: responde diretamente.
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return


def _make_mcp_token(
    sub: str,
    jti: str,
    aud: str | None = None,
    typ: str = "mcp",
    exp_delta: timedelta = timedelta(hours=1),
    **extra: Any,
) -> str:
    """Cria um JWT MCP de teste."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": sub,
        "typ": typ,
        "jti": jti,
        "aud": aud or f"{settings.mcp_base_url}/mcp/mcp",
        "scope": "mcp:full",
        "iat": now,
        "exp": now + exp_delta,
    }
    payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mcp_client(session, test_user, monkeypatch):
    """Client ASGI com o MCPAuthMiddleware + session factory do banco de teste.

    Cria um MCPOAuthClient e um MCPOAuthToken válidos no banco de teste.
    """
    import app.mcp_server.auth as auth_module

    # Monkeypatch a session factory para usar o engine de teste.
    test_factory = async_sessionmaker(
        session.bind, class_=type(session), expire_on_commit=False
    )
    monkeypatch.setattr(auth_module, "async_session_factory", test_factory)

    # Cria o cliente OAuth (FK do token).
    client_id = f"test-client-{uuid.uuid4().hex[:8]}"
    oauth_client = MCPOAuthClient(
        id=uuid.uuid4(),
        client_id=client_id,
        client_name="Test Client",
        redirect_uris=["http://localhost/callback"],
        grant_types=["authorization_code", "refresh_token"],
    )
    session.add(oauth_client)
    await session.commit()

    # Cria um token MCP válido no banco.
    jti = str(uuid.uuid4())
    token_record = MCPOAuthToken(
        jti=jti,
        user_id=test_user.id,
        client_id=client_id,
        scope="mcp:full",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        revoked_at=None,
    )
    session.add(token_record)
    await session.commit()

    # Monta o app com middleware.
    app = MCPAuthMiddleware(_dummy_app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_authorization_header(mcp_client):
    """Request sem header Authorization → 401 com WWW-Authenticate."""
    resp = await mcp_client.get("/mcp/mcp")
    assert resp.status_code == 401
    www_auth = resp.headers.get("www-authenticate", "")
    assert "Bearer" in www_auth
    assert "resource_metadata" in www_auth
    assert "mcp:full" in www_auth


@pytest.mark.asyncio
async def test_malformed_token(mcp_client):
    """Token malformado (não é JWT) → 401."""
    resp = await mcp_client.get(
        "/mcp/mcp",
        headers={"Authorization": "Bearer not-a-valid-jwt-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token(mcp_client, test_user):
    """Token expirado → 401."""
    jti = str(uuid.uuid4())
    token = _make_mcp_token(
        sub=str(test_user.id),
        jti=jti,
        exp_delta=timedelta(hours=-1),  # expirado há 1 hora
    )
    resp = await mcp_client.get(
        "/mcp/mcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_token(mcp_client, test_user, session):
    """Token válido (typ=mcp, aud correto, jti no banco, user existe) → 200."""
    # Usa o jti que já foi criado no fixture mcp_client.
    # Precisamos recuperar o jti do token criado no fixture.
    from sqlalchemy import select

    result = await session.execute(
        select(MCPOAuthToken.jti).where(MCPOAuthToken.user_id == test_user.id)
    )
    jti = result.scalar_one()

    token = _make_mcp_token(sub=str(test_user.id), jti=jti)
    resp = await mcp_client.get(
        "/mcp/mcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    # O dummy app responde 200. Se o middleware rejeitasse, seria 401.
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_revoked_token(mcp_client, test_user, session):
    """Token revogado (revoked_at setado) → 401."""
    from sqlalchemy import select

    # Recupera o jti do token criado no fixture.
    result = await session.execute(
        select(MCPOAuthToken.jti).where(MCPOAuthToken.user_id == test_user.id)
    )
    jti = result.scalar_one()

    # Revoga o token.
    token_record = await session.get(MCPOAuthToken, jti)
    token_record.revoked_at = datetime.now(UTC)
    await session.commit()

    token = _make_mcp_token(sub=str(test_user.id), jti=jti)
    resp = await mcp_client.get(
        "/mcp/mcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_wrong_audience(mcp_client, test_user, session):
    """Token com aud errado → 401."""
    from sqlalchemy import select

    result = await session.execute(
        select(MCPOAuthToken.jti).where(MCPOAuthToken.user_id == test_user.id)
    )
    jti = result.scalar_one()

    # Cria token com aud diferente do esperado.
    token = _make_mcp_token(
        sub=str(test_user.id),
        jti=jti,
        aud="http://wrong-host/mcp/mcp",
    )
    resp = await mcp_client.get(
        "/mcp/mcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
