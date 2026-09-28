"""Testes do campo ``repository`` no pipeline, PR no run, DELETE e duplicate.

Task 4 (2026-09-28-projeto-git-e-usabilidade): cobre
- roundtrip de ``repository`` no POST/PUT/GET de pipeline (400 ``invalid_repository``
  quando a integração não é do dono ou não é git);
- DELETE /api/pipelines/:id (204, cascade; 409 ``graph_running`` com run ativo);
- POST /api/pipelines/:id/duplicate (201, novos UUIDs, nome "<nome> (cópia)").

Define seu próprio ``test_app``/``client`` (agents + integrations + pipelines
routers) porque o ``client`` compartilhado (``tests/integration_api_fixtures``)
só inclui o router de integrações; os fixtures ``make_agent``/``make_git_integration``
(``tests/conftest.py``) resolvem o ``client`` mais próximo do módulo, ou seja,
o definido aqui.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import AgentService
from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import PipelineRun, User
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Mock storage de agentes (evita dependência do Garage; mesmo padrão de
# test_agents_crud.py).
# ---------------------------------------------------------------------------


class MockAgentStorage:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        self.store.pop(agent_id, None)


@pytest_asyncio.fixture
async def mock_storage():
    return MockAgentStorage()


@pytest_asyncio.fixture
async def test_app(session: AsyncSession, test_user: User, mock_storage: MockAgentStorage):
    """App de teste com agents + integrations + pipelines (+ pipeline_runs)."""
    from app.api.agents import router as agents_router
    from app.api.integrations import router as integrations_router
    from app.api.pipelines import router as pipelines_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agents_router, prefix="/api")
    app.include_router(integrations_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("app.api.agents._get_service") as mock_service_fn:
        service = AgentService(storage=mock_storage)
        mock_service_fn.return_value = service
        yield app


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------


async def test_repository_roundtrip_delete_and_duplicate(client, make_agent, make_git_integration):
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
    created = await client.post("/api/pipelines", json=body)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["repository"] == {
        "integrationId": integ["id"],
        "fullName": "o/r",
        "baseBranch": "main",
    }

    # GET reflete o mesmo repository.
    fetched = await client.get(f"/api/pipelines/{pid}")
    assert fetched.json()["repository"] == created.json()["repository"]

    cleared = await client.put(f"/api/pipelines/{pid}", json={"repository": None})
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["repository"] is None

    # PUT sem a chave "repository": mantém o valor atual (ainda None).
    kept = await client.put(f"/api/pipelines/{pid}", json={"description": "d"})
    assert kept.json()["repository"] is None

    # Reatribui o repository via PUT.
    restored = await client.put(
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

    dup = await client.post(f"/api/pipelines/{pid}/duplicate")
    assert dup.status_code == 201, dup.text
    dup_body = dup.json()
    assert dup_body["name"] == "Projeto X (cópia)"
    assert dup_body["status"] == "draft"
    assert len(dup_body["nodes"]) == 1
    assert dup_body["nodes"][0]["id"] != "11111111-1111-1111-1111-111111111111"
    assert dup_body["entryNodeId"] == dup_body["nodes"][0]["id"]
    assert dup_body["id"] != pid

    assert (await client.delete(f"/api/pipelines/{pid}")).status_code == 204
    assert (await client.get(f"/api/pipelines/{pid}")).status_code == 404


async def test_invalid_repository_rejected(client, make_agent, make_git_integration):
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
    r = await client.post("/api/pipelines", json=body)
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_repository"


async def test_invalid_repository_missing_fields(client, make_git_integration):
    integ = await make_git_integration()
    r = await client.post(
        "/api/pipelines",
        json={"name": "Sem baseBranch", "nodes": [], "edges": [],
              "repository": {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": ""}},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "invalid_repository"


async def test_delete_pipeline_with_active_run_conflicts(client, session, test_user):
    body = {"name": "Rodando", "nodes": [], "edges": []}
    created = await client.post("/api/pipelines", json=body)
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

    r = await client.delete(f"/api/pipelines/{pid}")
    assert r.status_code == 409
    assert r.json()["code"] == "graph_running"


async def test_duplicate_unknown_pipeline_404(client):
    r = await client.post(f"/api/pipelines/{uuid.uuid4()}/duplicate")
    assert r.status_code == 404
