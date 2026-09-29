"""Tests for agents CRUD API (D4 4.1).

Cobre: create, list, get, update, delete + isolamento por owner +
falha do Garage (500 envelope).
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import AgentService
from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db

# ---------------------------------------------------------------------------
# Mock storage
# ---------------------------------------------------------------------------


class MockAgentStorage:
    """Mock do AgentStorage para testes (in-memory)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail_on_save = False
        self.fail_on_delete = False

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        if self.fail_on_save:
            raise ConnectionError("Garage unavailable")
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        if agent_id not in self.store:
            raise FileNotFoundError(f"Agent {agent_id} not found")
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        if self.fail_on_delete:
            raise ConnectionError("Garage unavailable")
        self.store.pop(agent_id, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_storage():
    return MockAgentStorage()


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    """Cria um usuário de teste no banco."""
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


@pytest_asyncio.fixture
async def second_user(session: AsyncSession) -> User:
    """Cria um segundo usuário para testar isolamento."""
    user = User(
        id=uuid.uuid4(),
        email="second@example.com",
        name="Second User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_app(session: AsyncSession, test_user: User, mock_storage: MockAgentStorage):
    """Cria uma app FastAPI de teste com o router de agentes."""
    from app.api.agents import router as agents_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agents_router, prefix="/api")

    # Override get_db: yield the same session.
    async def override_get_db():
        yield session

    # Override get_current_user.
    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Patch the service to use mock storage.
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
# Tests: CRUD
# ---------------------------------------------------------------------------


class TestEffectiveModel:
    async def test_effective_model_reflects_llm_model(self, client: AsyncClient, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "llm_model", "Qwen3.8-27B-Q8_0")
        created = await client.post("/api/agents", json={"name": "Modelo A", "model": "gpt-4o"})
        assert created.json()["model"] == "gpt-4o"
        assert created.json()["effectiveModel"] == "Qwen3.8-27B-Q8_0"
        got = await client.get(f"/api/agents/{created.json()['id']}")
        assert got.json()["effectiveModel"] == "Qwen3.8-27B-Q8_0"

    async def test_effective_model_falls_back_to_agent_model(
        self, client: AsyncClient, monkeypatch
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "llm_model", "")
        created = await client.post("/api/agents", json={"name": "Modelo B", "model": "gpt-4o"})
        assert created.json()["effectiveModel"] == "gpt-4o"


class TestCreateAgent:
    async def test_create_agent_success(self, client: AsyncClient, mock_storage: MockAgentStorage):
        response = await client.post(
            "/api/agents",
            json={
                "name": "My Planner",
                "type": "planner",
                "description": "A planning agent",
                "prompt": "You are a planner.",
                "inputs": [{"name": "req", "type": "document", "required": True}],
                "outputs": [{"name": "plan", "type": "document", "required": False}],
                "actions": ["follow", "finalize"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Planner"
        assert data["type"] == "planner"
        assert data["id"] is not None
        assert data["shellAccess"] is False
        assert data["maxIterations"] == 10
        # Artifact should be in storage.
        assert data["id"] in mock_storage.store

    async def test_create_agent_invalid_contract(self, client: AsyncClient):
        response = await client.post(
            "/api/agents",
            json={
                "name": "Bad Agent",
                "inputs": [{"name": "x", "type": "invalid_type", "required": True}],
                "actions": ["bad_action"],
            },
        )
        assert response.status_code == 400
        data = response.json()
        assert data["code"] == "invalid_graph"
        assert "errors" in data["details"]
        assert len(data["details"]["errors"]) >= 2

    async def test_create_agent_duplicate_name(self, client: AsyncClient):
        await client.post("/api/agents", json={"name": "Unique Agent"})
        response = await client.post("/api/agents", json={"name": "Unique Agent"})
        assert response.status_code == 409
        assert response.json()["code"] == "agent_name_exists"

    async def test_create_agent_garage_failure(
        self, client: AsyncClient, mock_storage: MockAgentStorage
    ):
        mock_storage.fail_on_save = True
        response = await client.post("/api/agents", json={"name": "Fail Agent"})
        assert response.status_code == 500
        assert response.json()["code"] == "storage_error"


class TestListAgents:
    async def test_list_agents_empty(self, client: AsyncClient):
        response = await client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["limit"] == 20

    async def test_list_agents_with_items(self, client: AsyncClient):
        await client.post("/api/agents", json={"name": "Agent 1", "type": "planner"})
        await client.post("/api/agents", json={"name": "Agent 2", "type": "developer"})
        response = await client.get("/api/agents")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_agents_filter_by_type(self, client: AsyncClient):
        await client.post("/api/agents", json={"name": "Agent 1", "type": "planner"})
        await client.post("/api/agents", json={"name": "Agent 2", "type": "developer"})
        response = await client.get("/api/agents?type=planner")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["type"] == "planner"

    async def test_list_agents_pagination(self, client: AsyncClient):
        for i in range(5):
            await client.post("/api/agents", json={"name": f"Agent {i}"})
        response = await client.get("/api/agents?page=1&limit=2")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["page"] == 1
        assert data["limit"] == 2


class TestGetAgent:
    async def test_get_agent_success(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json={"name": "Find Me"})
        agent_id = create_resp.json()["id"]
        response = await client.get(f"/api/agents/{agent_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Find Me"

    async def test_get_agent_not_found(self, client: AsyncClient):
        response = await client.get(f"/api/agents/{uuid.uuid4()}")
        assert response.status_code == 404
        assert response.json()["code"] == "agent_not_found"

    async def test_get_agent_owner_isolation(
        self, client: AsyncClient, session: AsyncSession, second_user: User
    ):
        """User A cannot see User B's agent."""
        create_resp = await client.post("/api/agents", json={"name": "Private Agent"})
        agent_id = create_resp.json()["id"]

        # Verify the agent is not accessible by a different owner_id.
        service = AgentService(storage=MockAgentStorage())
        with pytest.raises(Exception) as exc_info:
            await service.get_agent(session, second_user.id, uuid.UUID(agent_id))
        assert exc_info.value.code == "agent_not_found"


class TestUpdateAgent:
    async def test_update_agent_success(self, client: AsyncClient, mock_storage: MockAgentStorage):
        create_resp = await client.post("/api/agents", json={"name": "Original"})
        agent_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/agents/{agent_id}",
            json={"name": "Updated", "description": "New description"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated"
        assert data["description"] == "New description"
        # Storage should have the updated artifact.
        assert agent_id in mock_storage.store

    async def test_update_agent_not_found(self, client: AsyncClient):
        response = await client.put(f"/api/agents/{uuid.uuid4()}", json={"name": "X"})
        assert response.status_code == 404

    async def test_update_agent_invalid_contract(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json={"name": "Valid"})
        agent_id = create_resp.json()["id"]

        response = await client.put(
            f"/api/agents/{agent_id}",
            json={"inputs": [{"name": "x", "type": "bad_type", "required": True}]},
        )
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_graph"

    async def test_update_agent_empty_body(self, client: AsyncClient):
        create_resp = await client.post("/api/agents", json={"name": "Valid"})
        agent_id = create_resp.json()["id"]

        response = await client.put(f"/api/agents/{agent_id}", json={})
        assert response.status_code == 400


class TestDeleteAgent:
    async def test_delete_agent_success(self, client: AsyncClient, mock_storage: MockAgentStorage):
        create_resp = await client.post("/api/agents", json={"name": "Delete Me"})
        agent_id = create_resp.json()["id"]
        assert agent_id in mock_storage.store

        response = await client.delete(f"/api/agents/{agent_id}")
        assert response.status_code == 204
        assert agent_id not in mock_storage.store

    async def test_delete_agent_not_found(self, client: AsyncClient):
        response = await client.delete(f"/api/agents/{uuid.uuid4()}")
        assert response.status_code == 404

    async def test_delete_agent_garage_failure(
        self, client: AsyncClient, mock_storage: MockAgentStorage
    ):
        create_resp = await client.post("/api/agents", json={"name": "Keep Me"})
        agent_id = create_resp.json()["id"]

        mock_storage.fail_on_delete = True
        response = await client.delete(f"/api/agents/{agent_id}")
        assert response.status_code == 500
        assert response.json()["code"] == "storage_error"
