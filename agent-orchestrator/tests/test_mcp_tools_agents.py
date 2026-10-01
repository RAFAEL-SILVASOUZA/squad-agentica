"""Testes das ferramentas MCP de agentes (Task 6).

Cobre: create, list, get, update, delete + erro de autenticação (sem usuário
no contextvar) + ID inválido. As tools são funções async decoradas com
``@mcp.tool()``; nos testes são chamadas diretamente como funções async.

Setup:
- ``get_current_mcp_user`` é patcheado para retornar o usuário de teste
  (evita o problema de contextvar em contextos diferentes do pytest-asyncio).
- ``async_session_factory`` é patcheado para usar a sessão do banco de teste.
- ``AgentService`` é patcheado para usar um storage mock (in-memory), evitando
  dependência do Garage real.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import AgentService
from app.db.models import User
from app.mcp_server.tools import ToolError
from app.mcp_server.tools.agents import (
    create_agent,
    delete_agent,
    get_agent,
    list_agents,
    update_agent,
)


# ---------------------------------------------------------------------------
# Mock storage (mesmo padrão de test_agents_crud.py)
# ---------------------------------------------------------------------------


class MockAgentStorage:
    """Mock in-memory do AgentStorage para os testes das tools MCP."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        self.store.pop(agent_id, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mock_storage() -> MockAgentStorage:
    return MockAgentStorage()


@pytest_asyncio.fixture
async def mcp_env(session: AsyncSession, test_user: User, mock_storage: MockAgentStorage):
    """Prepara o ambiente das tools MCP.

    - Patcheia ``get_current_mcp_user`` (módulo das tools) para retornar o
      usuário de teste.
    - Patcheia ``async_session_factory`` (módulo das tools) para usar a sessão
      do banco de teste.
    - Patcheia ``AgentService`` (módulo das tools) para usar o storage mock.

    Retorna o usuário de teste.
    """

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.agents.get_current_mcp_user",
            return_value=test_user,
        ),
        patch("app.mcp_server.tools.agents.async_session_factory", fake_session_factory),
        patch(
            "app.mcp_server.tools.agents.AgentService",
            lambda: AgentService(storage=mock_storage),
        ),
    ):
        yield test_user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCreateAgent:
    async def test_create_agent_minimal(self, mcp_env: User, mock_storage: MockAgentStorage):
        """create_agent com args mínimos cria o agente e retorna o id."""
        result = await create_agent(name="Agente de Teste")
        assert result["name"] == "Agente de Teste"
        assert result["id"] is not None
        assert result["type"] == "custom"
        assert result["model"] == "gpt-4o"
        assert result["maxIterations"] == 10
        assert result["timeout"] == 300
        assert result["shellAccess"] is False
        # O artefato deve estar no storage mock.
        assert result["id"] in mock_storage.store

    async def test_create_agent_full(
        self, mcp_env: User, mock_storage: MockAgentStorage
    ):
        """create_agent com todos os campos persiste os valores."""
        result = await create_agent(
            name="Agente Completo",
            description="Descrição",
            prompt="Prompt",
            strategy="Regra",
            type="planner",
            model="gpt-4o-mini",
            max_iterations=5,
            timeout=60,
            shell_access=True,
            skills=[{"id": "s1"}],
            tools=[{"id": "t1"}],
            mcp_servers=[{"serverId": "m1"}],
            knowledge=[{"id": "k1"}],
            integrations=[{"id": "i1"}],
            inputs=[{"name": "req", "type": "document", "required": True}],
            outputs=[{"name": "plan", "type": "document", "required": False}],
            actions=["finalize"],
        )
        assert result["name"] == "Agente Completo"
        assert result["type"] == "planner"
        assert result["model"] == "gpt-4o-mini"
        assert result["maxIterations"] == 5
        assert result["timeout"] == 60
        assert result["shellAccess"] is True
        assert result["skills"] == [{"id": "s1"}]
        assert result["mcpServers"] == [{"serverId": "m1"}]
        assert result["actions"] == ["finalize"]


class TestListAgents:
    async def test_list_agents_empty(self, mcp_env: User):
        """list_agents sem agentes retorna lista vazia."""
        result = await list_agents()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 20

    async def test_list_agents_with_items(self, mcp_env: User):
        """list_agents retorna os agentes criados."""
        await create_agent(name="Agente 1", type="planner")
        await create_agent(name="Agente 2", type="developer")
        result = await list_agents()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_agents_filter_by_type(self, mcp_env: User):
        """list_agents com type_filter filtra por tipo."""
        await create_agent(name="Agente 1", type="planner")
        await create_agent(name="Agente 2", type="developer")
        result = await list_agents(type_filter="planner")
        assert result["total"] == 1
        assert result["items"][0]["type"] == "planner"


class TestGetAgent:
    async def test_get_agent_success(self, mcp_env: User):
        """get_agent com id válido retorna o agente."""
        created = await create_agent(name="Encontrar-me")
        result = await get_agent(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "Encontrar-me"

    async def test_get_agent_not_found(self, mcp_env: User):
        """get_agent com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await get_agent(str(uuid.uuid4()))

    async def test_get_agent_invalid_id(self, mcp_env: User):
        """get_agent com id inválido (não-UUID) lança ToolError."""
        with pytest.raises(ToolError) as exc_info:
            await get_agent("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdateAgent:
    async def test_update_agent_partial(self, mcp_env: User):
        """update_agent com partial update altera só os campos informados."""
        created = await create_agent(name="Original", description="Desc original")
        result = await update_agent(created["id"], name="Atualizado")
        assert result["name"] == "Atualizado"
        # Campo não informado permanece.
        assert result["description"] == "Desc original"

    async def test_update_agent_not_found(self, mcp_env: User):
        """update_agent com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await update_agent(str(uuid.uuid4()), name="X")

    async def test_update_agent_no_fields(self, mcp_env: User):
        """update_agent sem nenhum campo lança ToolError."""
        created = await create_agent(name="Sem-update")
        with pytest.raises(ToolError):
            await update_agent(created["id"])


class TestDeleteAgent:
    async def test_delete_agent_success(self, mcp_env: User, mock_storage: MockAgentStorage):
        """delete_agent remove o agente."""
        created = await create_agent(name="Remover-me")
        assert created["id"] in mock_storage.store
        result = await delete_agent(created["id"])
        assert result["success"] is True
        assert created["id"] not in mock_storage.store

    async def test_delete_agent_not_found(self, mcp_env: User):
        """delete_agent com id inexistente lança ToolError."""
        with pytest.raises(ToolError):
            await delete_agent(str(uuid.uuid4()))


class TestAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession, mock_storage: MockAgentStorage):
        """Tool sem usuário no contextvar lança ToolError('Não autenticado.')."""

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        # get_current_mcp_user retorna None (simula ausência de autenticação).
        with (
            patch(
                "app.mcp_server.tools.agents.get_current_mcp_user",
                return_value=None,
            ),
            patch("app.mcp_server.tools.agents.async_session_factory", fake_session_factory),
            patch(
                "app.mcp_server.tools.agents.AgentService",
                lambda: AgentService(storage=mock_storage),
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_agent(name="Sem auth")
            assert "Não autenticado" in exc_info.value.message
