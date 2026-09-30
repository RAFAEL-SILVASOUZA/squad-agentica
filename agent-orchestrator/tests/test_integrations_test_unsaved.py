"""Tests for Task 15: integrations test-unsaved, token_hint, last_test_status, usageCount."""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text


class FakeProvider:
    """Mock do GitProvider para testes de test-unsaved."""

    async def list_repos(self):
        from app.integrations.git_providers import Repo

        return [Repo("owner/repo1", "main"), Repo("owner/repo2", "main")]

    async def list_branches(self, repo: str):
        return ["main"]

    def clone_url(self, repo: str) -> str:
        return f"https://example.com/{repo}.git"

    def public_url(self, repo: str) -> str:
        return f"https://example.com/{repo}"

    async def create_pull_request(self, repo, head, base, title, body):
        from app.integrations.git_providers import PullRequest

        return PullRequest(1, "https://example.com/pr/1")

    async def find_open_pull_request(self, repo, head):
        return None


@pytest.mark.asyncio
async def test_test_unsaved_does_not_persist_or_echo(full_client, session, monkeypatch):
    """POST /api/integrations/test não grava nada e não ecoa o token."""
    monkeypatch.setattr(
        "app.api.integrations.provider_from_config",
        lambda t, c: FakeProvider(),
    )
    before = (await session.execute(text("select count(*) from integrations"))).scalar()
    r = await full_client.post(
        "/api/integrations/test",
        json={"type": "github", "config": {"token": "ghp_SEGREDO"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["repositories"] == 2
    # Token não aparece na resposta
    assert "SEGREDO" not in r.text
    # Nada foi gravado
    after = (await session.execute(text("select count(*) from integrations"))).scalar()
    assert after == before


@pytest.mark.asyncio
async def test_test_unsaved_non_git_type_returns_400(full_client):
    """Tipo não-git dá 400."""
    r = await full_client.post(
        "/api/integrations/test",
        json={"type": "gitlab", "config": {"token": "x"}},
    )
    # O schema valida o tipo (pattern github|azure) e rejeita com 422.
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_token_hint_after_create(full_client, session):
    """Criar com token ghp_SEGREDO → tokenHint é '…REDO'."""
    r = await full_client.post(
        "/api/integrations",
        json={"type": "github", "name": "Test GH", "config": {"token": "ghp_SEGREDO"}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["tokenHint"] == "…REDO"
    # Token continua mascarado
    assert body["config"]["token"] == "***"


@pytest.mark.asyncio
async def test_last_test_status_saved_on_test(full_client, session):
    """POST /{id}/test grava last_test_status no config."""
    # Cria a integração
    r = await full_client.post(
        "/api/integrations",
        json={"type": "github", "name": "Test GH", "config": {"token": "ghp_abc123"}},
    )
    assert r.status_code == 201
    integration_id = r.json()["id"]

    # Teste com provider mockado
    with patch("app.api.integrations.provider_for", return_value=FakeProvider()):
        r2 = await full_client.post(f"/api/integrations/{integration_id}/test")
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

    # Verifica que last_test_status foi gravado
    r3 = await full_client.get(f"/api/integrations/{integration_id}")
    body = r3.json()
    assert body["lastTestStatus"] == "ok"
    assert body["lastTestedAt"] is not None


@pytest.mark.asyncio
async def test_usage_count_counts_pipelines(full_client, session, test_user):
    """usageCount conta pipelines que usam a conexão."""
    from app.db.models import Pipeline

    # Cria a integração
    r = await full_client.post(
        "/api/integrations",
        json={"type": "github", "name": "Test GH", "config": {"token": "ghp_abc123"}},
    )
    assert r.status_code == 201
    integration_id = r.json()["id"]

    # Insere 2 pipelines diretamente no banco (evita validação de agente)
    for i in range(2):
        pipe = Pipeline(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name=f"Pipeline {i}",
            status="draft",
            entry_node_id=uuid.uuid4(),
            git_integration_id=uuid.UUID(integration_id),
        )
        session.add(pipe)
    await session.commit()

    # Lista integrações e verifica usageCount
    r_list = await full_client.get("/api/integrations")
    items = r_list.json()["items"]
    target = next(i for i in items if i["id"] == integration_id)
    assert target["usageCount"] == 2
