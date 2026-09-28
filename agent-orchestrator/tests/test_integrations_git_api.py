"""Tests for Git integration endpoints (test, repositories, branches).

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db
from app.integrations.git_providers import GitProviderError, Repo

# ---------------------------------------------------------------------------
# Fake Provider for Testing
# ---------------------------------------------------------------------------


class FakeProvider:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def list_repos(self) -> list[Repo]:
        if self.fail:
            raise GitProviderError("Listar repositórios: token inválido ou sem acesso")
        return [Repo("o/r", "main")]

    async def list_branches(self, repo: str) -> list[str]:
        return ["main", "dev"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    """Cria um usuario de teste no banco."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def owner_id(test_user: User) -> uuid.UUID:
    return test_user.id


@pytest.fixture(autouse=True)
def fernet_key_fixture(monkeypatch):
    """Set up Fernet key for all tests in this module."""
    from cryptography.fernet import Fernet

    from app.core.config import settings

    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())


@pytest_asyncio.fixture
async def test_app(session: AsyncSession, test_user: User):
    """Cria uma app FastAPI de teste com o router de integrações."""
    from app.api.integrations import router as integrations_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(integrations_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield app


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create(client: AsyncClient) -> str:
    """Helper to create a GitHub integration and return its ID."""
    r = await client.post(
        "/api/integrations",
        json={"type": "github", "name": "gh", "config": {"token": "ghp_x"}},
    )
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGitIntegrationEndpoints:
    async def test_test_connection_ok_and_error(self, client: AsyncClient) -> None:
        """Test POST /api/integrations/{id}/test endpoint."""
        iid = await _create(client)
        with patch("app.api.integrations.provider_for", return_value=FakeProvider()):
            r = await client.post(f"/api/integrations/{iid}/test")
        assert r.json() == {"ok": True, "repositories": 1}

        with patch("app.api.integrations.provider_for", return_value=FakeProvider(fail=True)):
            r = await client.post(f"/api/integrations/{iid}/test")
        assert r.json()["ok"] is False and "token inválido" in r.json()["error"]

    async def test_repositories_and_branches(self, client: AsyncClient) -> None:
        """Test GET /api/integrations/{id}/repositories and /branches endpoints."""
        iid = await _create(client)
        with patch("app.api.integrations.provider_for", return_value=FakeProvider()):
            repos = await client.get(f"/api/integrations/{iid}/repositories")
            branches = await client.get(f"/api/integrations/{iid}/branches", params={"repo": "o/r"})
        assert repos.json() == {"items": [{"fullName": "o/r", "defaultBranch": "main"}]}
        assert branches.json() == {"items": ["main", "dev"]}
