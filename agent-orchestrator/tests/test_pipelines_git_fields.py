"""Testes do campo ``repository`` no pipeline, PR no run, DELETE e duplicate.

Task 4 (2026-09-28-projeto-git-e-usabilidade): cobre
- roundtrip de ``repository`` no POST/PUT/GET de pipeline (400 ``invalid_repository``
  quando a integração não é do dono ou não é git);
- DELETE /api/pipelines/:id (204, cascade; 409 ``graph_running`` com run ativo);
- POST /api/pipelines/:id/duplicate (201, novos UUIDs, nome "<nome> (cópia)").

Usa o harness compartilhado ``full_client`` (agents + integrations + pipelines
+ pipeline_runs, storage de agentes mockado) de
``tests/integration_api_fixtures.py`` — os fixtures ``make_agent``/
``make_git_integration`` (``tests/conftest.py``) já dependem dele.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.db.models import PipelineRun, User
from app.runtime.workspace import WorkspaceManager


async def test_repository_roundtrip_delete_and_duplicate(
    full_client, make_agent, make_git_integration
):
    agent = await make_agent("A")
    integ = await make_git_integration()
    body = {
        "name": "Projeto X",
        "nodes": [
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "agentId": agent["id"],
                "position": {"x": 0, "y": 0},
                "label": "A",
                "agentSnapshot": {
                    "agentId": agent["id"],
                    "name": "A",
                    "inputs": [],
                    "outputs": [],
                    "actions": ["finalize"],
                },
            }
        ],
        "edges": [],
        "repository": {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main"},
    }
    created = await full_client.post("/api/pipelines", json=body)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["repository"] == {
        "integrationId": integ["id"],
        "fullName": "o/r",
        "baseBranch": "main",
    }

    # GET reflete o mesmo repository.
    fetched = await full_client.get(f"/api/pipelines/{pid}")
    assert fetched.json()["repository"] == created.json()["repository"]

    cleared = await full_client.put(f"/api/pipelines/{pid}", json={"repository": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["repository"] is None

    # PUT sem a chave "repository": mantém o valor atual (ainda None).
    kept = await full_client.put(f"/api/pipelines/{pid}", json={"description": "d"})
    assert kept.json()["repository"] is None

    # Reatribui o repository via PUT.
    restored = await full_client.put(
        f"/api/pipelines/{pid}",
        json={
            "repository": {
                "integrationId": integ["id"], "fullName": "o/r2", "baseBranch": "dev"
            }
        },
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["repository"] == {
        "integrationId": integ["id"],
        "fullName": "o/r2",
        "baseBranch": "dev",
    }

    dup = await full_client.post(f"/api/pipelines/{pid}/duplicate")
    assert dup.status_code == 201, dup.text
    dup_body = dup.json()
    assert dup_body["name"] == "Projeto X (cópia)"
    assert dup_body["status"] == "draft"
    assert len(dup_body["nodes"]) == 1
    assert dup_body["nodes"][0]["id"] != "11111111-1111-1111-1111-111111111111"
    assert dup_body["entryNodeId"] == dup_body["nodes"][0]["id"]
    assert dup_body["id"] != pid
    # A cópia mantém o repositório vinculado.
    assert dup_body["repository"] == restored.json()["repository"]

    assert (await full_client.delete(f"/api/pipelines/{pid}")).status_code == 204
    assert (await full_client.get(f"/api/pipelines/{pid}")).status_code == 404


async def test_invalid_repository_rejected(full_client, make_agent, make_git_integration):
    other_owner_integration_id = str(uuid.uuid4())
    body = {
        "name": "Sem repo válido",
        "nodes": [],
        "edges": [],
        "repository": {
            "integrationId": other_owner_integration_id,
            "fullName": "o/r",
            "baseBranch": "main",
        },
    }
    r = await full_client.post("/api/pipelines", json=body)
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_repository"


async def test_invalid_repository_missing_fields(full_client, make_git_integration):
    integ = await make_git_integration()
    r = await full_client.post(
        "/api/pipelines",
        json={"name": "Sem baseBranch", "nodes": [], "edges": [],
              "repository": {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": ""}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_repository"


async def test_delete_pipeline_with_active_run_conflicts(full_client, session, test_user: User):
    body = {"name": "Rodando", "nodes": [], "edges": []}
    created = await full_client.post("/api/pipelines", json=body)
    pid = created.json()["id"]

    run = PipelineRun(
        id=uuid.uuid4(),
        owner_id=test_user.owner_id,
        pipeline_id=uuid.UUID(pid),
        thread_id=f"{pid}:{uuid.uuid4()}",
        status="running",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.commit()

    r = await full_client.delete(f"/api/pipelines/{pid}")
    assert r.status_code == 409
    assert r.json()["code"] == "graph_running"


async def test_duplicate_unknown_pipeline_404(full_client):
    r = await full_client.post(f"/api/pipelines/{uuid.uuid4()}/duplicate")
    assert r.status_code == 404


async def test_delete_pipeline_removes_run_workspaces(
    full_client, session, test_user: User, monkeypatch, tmp_path
):
    """Ruling R2 (Task 5): DELETE /api/pipelines/:id remove os workspaces em
    disco dos runs da pipeline (``WorkspaceManager.remove_many``)."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "workspaces_dir", str(tmp_path))

    body = {"name": "Com workspace", "nodes": [], "edges": []}
    created = await full_client.post("/api/pipelines", json=body)
    pid = created.json()["id"]

    run = PipelineRun(
        id=uuid.uuid4(),
        owner_id=test_user.owner_id,
        pipeline_id=uuid.UUID(pid),
        thread_id=f"{pid}:{uuid.uuid4()}",
        status="completed",
        started_at=datetime.now(UTC),
    )
    session.add(run)
    await session.commit()

    ws = WorkspaceManager(tmp_path)
    ws.create_empty(str(run.id))
    assert ws.path(str(run.id)).exists()

    r = await full_client.delete(f"/api/pipelines/{pid}")
    assert r.status_code == 204
    assert not ws.path(str(run.id)).exists()
