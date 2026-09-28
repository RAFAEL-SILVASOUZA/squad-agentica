"""Tests for Git integration endpoints (test, repositories, branches).

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient

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


@pytest.fixture(autouse=True)
def fernet_key_fixture(monkeypatch):
    """Set up Fernet key for all tests in this module."""
    from cryptography.fernet import Fernet

    from app.core.config import settings

    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())


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

    async def test_non_git_integration_rejected(
        self, client: AsyncClient, session, test_user
    ) -> None:
        """Test that non-git integrations (e.g. gitlab) are rejected."""
        import uuid as uuid_module

        from app.db.models import Integration

        # Create a non-git integration directly in DB with test_user as owner
        integration = Integration(
            id=uuid_module.uuid4(),
            owner_id=test_user.id,
            type="gitlab",
            name="gitlab-test",
            config={"token": "gl_token"},
        )
        session.add(integration)
        await session.commit()

        # Test /test endpoint
        r = await client.post(f"/api/integrations/{integration.id}/test")
        assert r.status_code == 400
        assert r.json()["code"] == "not_a_git_integration"

        # Test /repositories endpoint
        r = await client.get(f"/api/integrations/{integration.id}/repositories")
        assert r.status_code == 400
        assert r.json()["code"] == "not_a_git_integration"

        # Test /branches endpoint
        r = await client.get(
            f"/api/integrations/{integration.id}/branches", params={"repo": "o/r"}
        )
        assert r.status_code == 400
        assert r.json()["code"] == "not_a_git_integration"
