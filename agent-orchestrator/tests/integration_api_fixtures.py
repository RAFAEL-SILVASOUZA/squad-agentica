"""Shared fixtures for API integration tests.

Contains fixtures for test_user, owner_id, test_app, and client that are
reused across multiple test files. Also has ``full_app``/``full_client``
(agents + integrations + pipelines + pipeline_runs, com o storage de agentes
mockado) para testes que precisam orquestrar mais de um recurso — ex.:
criar um agente e uma integração antes de montar um pipeline.
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
    """HTTP client para testes de API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# full_app / full_client: harness com agents + integrations + pipelines +
# pipeline_runs, para testes que precisam orquestrar mais de um recurso
# (ex.: criar agente/integração antes de montar um pipeline). O storage de
# agentes é mockado (evita dependência do Garage real), mesmo padrão de
# test_agents_crud.py.
# ---------------------------------------------------------------------------


class MockAgentStorage:
    """Mock in-memory do ``AgentStorage`` (protocolo em ``app/agents/storage.py``)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        self.store.pop(agent_id, None)


@pytest_asyncio.fixture
async def mock_agent_storage() -> MockAgentStorage:
    return MockAgentStorage()


@pytest_asyncio.fixture
async def full_app(session: AsyncSession, test_user: User, mock_agent_storage: MockAgentStorage):
    """App de teste com agents + integrations + pipelines + pipeline_runs."""
    from app.api.agents import router as agents_router
    from app.api.integrations import router as integrations_router
    from app.api.pipeline_runs import router as pipeline_runs_router
    from app.api.pipelines import router as pipelines_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agents_router, prefix="/api")
    app.include_router(integrations_router, prefix="/api")
    app.include_router(pipelines_router, prefix="/api")
    app.include_router(pipeline_runs_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with patch("app.api.agents._get_service") as mock_service_fn:
        service = AgentService(storage=mock_agent_storage)
        mock_service_fn.return_value = service
        yield app


@pytest_asyncio.fixture
async def full_client(full_app):
    """HTTP client para o ``full_app`` (agents + integrations + pipelines)."""
    transport = ASGITransport(app=full_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
