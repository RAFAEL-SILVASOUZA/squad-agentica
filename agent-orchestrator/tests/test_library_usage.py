"""Tests for usageCount in library list endpoints (skills, tools, mcp-servers).

Verifica que o campo usageCount reflete o numero de agentes DISTINCT do
mesmo usuario que referenciam o item.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import Agent, CustomTool, MCPServer, Skill, User
from app.db.session import get_db
from app.skills.storage import SkillStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def library_app(session: AsyncSession, test_user: User):
    """App FastAPI com routers de skills, tools e mcp-servers."""
    from app.api.mcp_servers import router as mcp_router
    from app.api.skills import router as skills_router
    from app.api.tools import router as tools_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(skills_router, prefix="/api")
    app.include_router(tools_router, prefix="/api")
    app.include_router(mcp_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock o skill storage para evitar dependencia do Garage.
    mock_storage = AsyncMock(spec=SkillStorage)
    mock_storage.save_skill = AsyncMock()
    mock_storage.get_skill = AsyncMock(return_value="# Test")
    mock_storage.delete_skill = AsyncMock()

    import app.api.skills as skills_module
    original = skills_module.get_skill_storage
    skills_module.get_skill_storage = lambda: mock_storage

    yield app

    skills_module.get_skill_storage = original


@pytest_asyncio.fixture
async def library_client(library_app):
    """HTTP client para o app de testes de library."""
    transport = ASGITransport(app=library_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def other_user_fixture(session: AsyncSession) -> User:
    """Segundo usuario para testes de isolamento."""
    user = User(
        id=uuid.uuid4(),
        email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        name="Other User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user_client(library_app, other_user_fixture: User):
    """HTTP client autenticado como outro usuario."""
    transport = ASGITransport(app=library_app)

    async def override_get_current_user():
        return other_user_fixture

    library_app.dependency_overrides[get_current_user] = override_get_current_user

    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_skill_via_api(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/api/skills", json={
        "name": name,
        "description": "test skill",
        "category": "code",
        "definition": {"template": "x", "variables": []},
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_tool_via_api(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/api/tools", json={
        "name": name,
        "description": "test tool",
        "script": "print('hi')",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_mcp_via_api(client: AsyncClient, name: str) -> dict:
    resp = await client.post("/api/mcp-servers", json={
        "name": name,
        "description": "test mcp",
        "transport": "stdio",
        "command": "echo",
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _create_agent_direct(
    session: AsyncSession,
    owner_id: uuid.UUID,
    name: str,
    skills: list | None = None,
    tools: list | None = None,
    mcp_servers: list | None = None,
) -> Agent:
    """Cria um agente diretamente no banco (evita a complexidade do API de agents)."""
    agent = Agent(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name,
        type="custom",
        prompt="test",
        skills=skills or [],
        tools=tools or [],
        mcp_servers=mcp_servers or [],
    )
    session.add(agent)
    await session.commit()
    await session.refresh(agent)
    return agent


# ---------------------------------------------------------------------------
# Tests: Skills usageCount
# ---------------------------------------------------------------------------


class TestSkillsUsageCount:
    async def test_usage_count_distinct_agents(
        self, library_client, session: AsyncSession, test_user: User
    ):
        """Skill A referenciada por 2 agentes distintos -> usageCount=2."""
        skill_a = await _create_skill_via_api(library_client, "skill-a")
        skill_b = await _create_skill_via_api(library_client, "skill-b")

        # Agent1 referencia skill A duas vezes (mesmo agente, nao conta 2x)
        ref_a = [{"skillId": str(skill_a["id"]), "config": {}}]
        await _create_agent_direct(
            session, test_user.id, "agent-1", skills=ref_a + ref_a
        )
        # Agent2 referencia skill A uma vez
        await _create_agent_direct(
            session, test_user.id, "agent-2", skills=ref_a
        )

        resp = await library_client.get("/api/skills")
        assert resp.status_code == 200
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["skill-a"]["usageCount"] == 2
        assert items["skill-b"]["usageCount"] == 0

    async def test_usage_count_isolated_per_user(
        self, library_client, other_user_client, session: AsyncSession,
        test_user: User, other_user_fixture: User,
    ):
        """Agentes de outro usuario nao contam no usageCount."""
        skill_a = await _create_skill_via_api(library_client, "skill-a")
        ref_a = [{"skillId": str(skill_a["id"]), "config": {}}]

        # 2 agentes do user1
        await _create_agent_direct(session, test_user.id, "agent-1", skills=ref_a)
        await _create_agent_direct(session, test_user.id, "agent-2", skills=ref_a)

        # 1 agente do user2 referencia a mesma skill
        await _create_agent_direct(session, other_user_fixture.id, "agent-3", skills=ref_a)

        # Para user1: usageCount deve ser 2
        resp = await library_client.get("/api/skills")
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["skill-a"]["usageCount"] == 2


# ---------------------------------------------------------------------------
# Tests: Tools usageCount
# ---------------------------------------------------------------------------


class TestToolsUsageCount:
    async def test_usage_count_distinct_agents(
        self, library_client, session: AsyncSession, test_user: User
    ):
        """Tool A referenciada por 2 agentes distintos -> usageCount=2."""
        tool_a = await _create_tool_via_api(library_client, "tool-a")
        tool_b = await _create_tool_via_api(library_client, "tool-b")

        ref_a = [{"toolId": str(tool_a["id"]), "config": {}}]
        await _create_agent_direct(
            session, test_user.id, "agent-1", tools=ref_a + ref_a
        )
        await _create_agent_direct(
            session, test_user.id, "agent-2", tools=ref_a
        )

        resp = await library_client.get("/api/tools")
        assert resp.status_code == 200
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["tool-a"]["usageCount"] == 2
        assert items["tool-b"]["usageCount"] == 0

    async def test_usage_count_isolated_per_user(
        self, library_client, other_user_client, session: AsyncSession,
        test_user: User, other_user_fixture: User,
    ):
        """Agentes de outro usuario nao contam no usageCount."""
        tool_a = await _create_tool_via_api(library_client, "tool-a")
        ref_a = [{"toolId": str(tool_a["id"]), "config": {}}]

        await _create_agent_direct(session, test_user.id, "agent-1", tools=ref_a)
        await _create_agent_direct(session, test_user.id, "agent-2", tools=ref_a)
        await _create_agent_direct(session, other_user_fixture.id, "agent-3", tools=ref_a)

        resp = await library_client.get("/api/tools")
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["tool-a"]["usageCount"] == 2


# ---------------------------------------------------------------------------
# Tests: MCP Servers usageCount
# ---------------------------------------------------------------------------


class TestMCPServersUsageCount:
    async def test_usage_count_distinct_agents(
        self, library_client, session: AsyncSession, test_user: User
    ):
        """MCP Server A referenciado por 2 agentes distintos -> usageCount=2."""
        mcp_a = await _create_mcp_via_api(library_client, "mcp-a")
        mcp_b = await _create_mcp_via_api(library_client, "mcp-b")

        ref_a = [{"serverId": str(mcp_a["id"])}]
        await _create_agent_direct(
            session, test_user.id, "agent-1", mcp_servers=ref_a + ref_a
        )
        await _create_agent_direct(
            session, test_user.id, "agent-2", mcp_servers=ref_a
        )

        resp = await library_client.get("/api/mcp-servers")
        assert resp.status_code == 200
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["mcp-a"]["usageCount"] == 2
        assert items["mcp-b"]["usageCount"] == 0

    async def test_usage_count_isolated_per_user(
        self, library_client, other_user_client, session: AsyncSession,
        test_user: User, other_user_fixture: User,
    ):
        """Agentes de outro usuario nao contam no usageCount."""
        mcp_a = await _create_mcp_via_api(library_client, "mcp-a")
        ref_a = [{"serverId": str(mcp_a["id"])}]

        await _create_agent_direct(session, test_user.id, "agent-1", mcp_servers=ref_a)
        await _create_agent_direct(session, test_user.id, "agent-2", mcp_servers=ref_a)
        await _create_agent_direct(session, other_user_fixture.id, "agent-3", mcp_servers=ref_a)

        resp = await library_client.get("/api/mcp-servers")
        items = {item["name"]: item for item in resp.json()["items"]}
        assert items["mcp-a"]["usageCount"] == 2
