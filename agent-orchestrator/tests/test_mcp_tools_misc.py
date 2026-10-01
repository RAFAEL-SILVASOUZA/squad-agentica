"""Testes das ferramentas MCP de MCP Servers e Integrações (Task 8).

Cobre: create, list, get, update, delete, test para ambos os módulos.
As tools são funções async decoradas com ``@mcp.tool()``; nos testes são
chamadas diretamente como funções async.

Setup:
- ``get_current_mcp_user`` é patcheado para retornar o usuário de teste.
- ``async_session_factory`` é patcheado para usar a sessão do banco de teste.
- ``test_mcp_connection_detail`` é patcheado para evitar conexão real.
- ``provider_for`` / ``build_llm_client`` / ``OpenAIEmbedder`` são patcheados
  para evitar chamadas de rede.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Integration, MCPServer, User
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mcp_servers_env(session: AsyncSession, test_user: User):
    """Ambiente para as tools de MCP servers."""

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.mcp_servers.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.mcp_servers.async_session_factory",
            fake_session_factory,
        ),
    ):
        yield test_user


@pytest_asyncio.fixture
async def integrations_env(session: AsyncSession, test_user: User):
    """Ambiente para as tools de integrações."""

    @asynccontextmanager
    async def fake_session_factory():
        yield session

    with (
        patch(
            "app.mcp_server.tools.integrations.get_current_mcp_user",
            return_value=test_user,
        ),
        patch(
            "app.mcp_server.tools.integrations.async_session_factory",
            fake_session_factory,
        ),
    ):
        yield test_user


# ---------------------------------------------------------------------------
# MCP Servers Tools
# ---------------------------------------------------------------------------


class TestCreateMCPServer:
    async def test_create_stdio(self, mcp_servers_env: User):
        """create_mcp_server com transport stdio cria o servidor."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server

        result = await create_mcp_server(
            name="meu-servidor",
            description="Servidor de teste",
            transport="stdio",
            command="npx my-mcp-server",
        )
        assert result["name"] == "meu-servidor"
        assert result["transport"] == "stdio"
        assert result["status"] == "disconnected"
        assert result["id"] is not None

    async def test_create_http(self, mcp_servers_env: User):
        """create_mcp_server com transport http cria o servidor."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server

        result = await create_mcp_server(
            name="servidor-http",
            transport="http",
            url="https://example.com/mcp",
        )
        assert result["name"] == "servidor-http"
        assert result["transport"] == "http"

    async def test_create_invalid_config(self, mcp_servers_env: User):
        """create_mcp_server com config inválida lança ToolError."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server

        # stdio sem command é inválido
        with pytest.raises(ToolError) as exc_info:
            await create_mcp_server(name="invalido", transport="stdio")
        assert "Configuração inválida" in exc_info.value.message

    async def test_create_duplicate_name(self, mcp_servers_env: User):
        """create_mcp_server com nome duplicado lança ToolError."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server

        await create_mcp_server(
            name="dup", transport="stdio", command="echo hi"
        )
        with pytest.raises(ToolError) as exc_info:
            await create_mcp_server(name="dup", transport="stdio", command="echo hi")
        assert "Erro ao criar servidor MCP" in exc_info.value.message


class TestListMCPServers:
    async def test_list_empty(self, mcp_servers_env: User):
        """list_mcp_servers sem servidores retorna lista vazia."""
        from app.mcp_server.tools.mcp_servers import list_mcp_servers

        result = await list_mcp_servers()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 50

    async def test_list_with_items(self, mcp_servers_env: User):
        """list_mcp_servers retorna os servidores criados."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, list_mcp_servers

        await create_mcp_server(name="srv1", transport="stdio", command="echo 1")
        await create_mcp_server(name="srv2", transport="http", url="https://x.com")
        result = await list_mcp_servers()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_env_masked(self, mcp_servers_env: User):
        """list_mcp_servers mascara os valores de env."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, list_mcp_servers

        await create_mcp_server(
            name="srv-env",
            transport="stdio",
            command="echo hi",
            env={"API_KEY": "secret123"},
        )
        result = await list_mcp_servers()
        item = result["items"][0]
        assert item["env"] == {"API_KEY": "***"}

    async def test_list_filter_by_transport(self, mcp_servers_env: User):
        """list_mcp_servers com filtro de transport."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, list_mcp_servers

        await create_mcp_server(name="s1", transport="stdio", command="echo 1")
        await create_mcp_server(name="s2", transport="http", url="https://x.com")
        result = await list_mcp_servers(transport="stdio")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "s1"


class TestGetMCPServer:
    async def test_get_success(self, mcp_servers_env: User):
        """get_mcp_server com id válido retorna o servidor."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, get_mcp_server

        created = await create_mcp_server(
            name="get-me", transport="stdio", command="echo hi"
        )
        result = await get_mcp_server(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "get-me"

    async def test_get_not_found(self, mcp_servers_env: User):
        """get_mcp_server com id inexistente lança ToolError."""
        from app.mcp_server.tools.mcp_servers import get_mcp_server

        with pytest.raises(ToolError) as exc_info:
            await get_mcp_server(str(uuid.uuid4()))
        assert "Servidor MCP não encontrado" in exc_info.value.message

    async def test_get_invalid_id(self, mcp_servers_env: User):
        """get_mcp_server com id inválido lança ToolError."""
        from app.mcp_server.tools.mcp_servers import get_mcp_server

        with pytest.raises(ToolError) as exc_info:
            await get_mcp_server("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdateMCPServer:
    async def test_update_name(self, mcp_servers_env: User):
        """update_mcp_server altera o nome."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, update_mcp_server

        created = await create_mcp_server(
            name="original", transport="stdio", command="echo hi"
        )
        result = await update_mcp_server(created["id"], name="renomeado")
        assert result["name"] == "renomeado"

    async def test_update_env_merge(self, mcp_servers_env: User):
        """update_mcp_server com env faz merge preservando valores mascarados."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, update_mcp_server

        created = await create_mcp_server(
            name="env-test",
            transport="stdio",
            command="echo hi",
            env={"KEY1": "real-value", "KEY2": "other"},
        )
        # Atualiza KEY2 e mantém KEY1 mascarado
        result = await update_mcp_server(
            created["id"], env={"KEY1": "***", "KEY2": "new-value"}
        )
        assert result["env"] == {"KEY1": "***", "KEY2": "***"}

    async def test_update_not_found(self, mcp_servers_env: User):
        """update_mcp_server com id inexistente lança ToolError."""
        from app.mcp_server.tools.mcp_servers import update_mcp_server

        with pytest.raises(ToolError):
            await update_mcp_server(str(uuid.uuid4()), name="X")


class TestDeleteMCPServer:
    async def test_delete_success(self, mcp_servers_env: User):
        """delete_mcp_server remove o servidor."""
        from app.mcp_server.tools.mcp_servers import (
            create_mcp_server,
            delete_mcp_server,
            get_mcp_server,
        )

        created = await create_mcp_server(
            name="delete-me", transport="stdio", command="echo hi"
        )
        result = await delete_mcp_server(created["id"])
        assert result["deleted"] is True
        assert result["id"] == created["id"]
        # Confirma que foi removido
        with pytest.raises(ToolError):
            await get_mcp_server(created["id"])

    async def test_delete_not_found(self, mcp_servers_env: User):
        """delete_mcp_server com id inexistente lança ToolError."""
        from app.mcp_server.tools.mcp_servers import delete_mcp_server

        with pytest.raises(ToolError):
            await delete_mcp_server(str(uuid.uuid4()))


class TestTestMCPServer:
    async def test_test_connected(self, mcp_servers_env: User):
        """test_mcp_server com conexão bem-sucedida."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, test_mcp_server

        created = await create_mcp_server(
            name="test-srv", transport="stdio", command="echo hi"
        )
        with patch(
            "app.mcp_server.tools.mcp_servers.test_mcp_connection_detail",
            new_callable=AsyncMock,
            return_value=(
                "connected",
                [{"name": "tool1", "description": "desc", "inputSchema": {}}],
                None,
            ),
        ):
            result = await test_mcp_server(created["id"])
        assert result["status"] == "connected"
        assert len(result["discoveredTools"]) == 1
        assert result["error"] is None

    async def test_test_error(self, mcp_servers_env: User):
        """test_mcp_server com erro de conexão."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server, test_mcp_server

        created = await create_mcp_server(
            name="test-srv-err", transport="stdio", command="echo hi"
        )
        with patch(
            "app.mcp_server.tools.mcp_servers.test_mcp_connection_detail",
            new_callable=AsyncMock,
            return_value=("error", [], "Comando não encontrado"),
        ):
            result = await test_mcp_server(created["id"])
        assert result["status"] == "error"
        assert result["discoveredTools"] == []
        assert result["error"] == "Comando não encontrado"

    async def test_test_not_found(self, mcp_servers_env: User):
        """test_mcp_server com id inexistente lança ToolError."""
        from app.mcp_server.tools.mcp_servers import test_mcp_server

        with pytest.raises(ToolError):
            await test_mcp_server(str(uuid.uuid4()))


class TestMCPServersAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession):
        """Tool MCP server sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.mcp_servers import create_mcp_server

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.mcp_servers.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.mcp_servers.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_mcp_server(name="sem-auth", transport="stdio", command="x")
            assert "Não autenticado" in exc_info.value.message


# ---------------------------------------------------------------------------
# Integrations Tools
# ---------------------------------------------------------------------------


class TestCreateIntegration:
    async def test_create_github(self, integrations_env: User):
        """create_integration com tipo github cria a integração."""
        from app.mcp_server.tools.integrations import create_integration

        result = await create_integration(
            type="github",
            name="meu-github",
            config={"owner": "myorg"},
        )
        assert result["name"] == "meu-github"
        assert result["type"] == "github"
        assert result["status"] == "active"
        assert result["id"] is not None

    async def test_create_llm(self, integrations_env: User):
        """create_integration com tipo llm cria a integração."""
        from app.mcp_server.tools.integrations import create_integration

        result = await create_integration(
            type="llm",
            name="meu-llm",
            config={"provider_kind": "mock", "model": "gpt-4o"},
        )
        assert result["name"] == "meu-llm"
        assert result["type"] == "llm"

    async def test_create_invalid_type(self, integrations_env: User):
        """create_integration com tipo inválido lança ToolError."""
        from app.mcp_server.tools.integrations import create_integration

        with pytest.raises(ToolError) as exc_info:
            await create_integration(type="invalid", name="x")
        assert "Erro ao criar integração" in exc_info.value.message

    async def test_create_duplicate_name(self, integrations_env: User):
        """create_integration com nome duplicado lança ToolError."""
        from app.mcp_server.tools.integrations import create_integration

        await create_integration(type="github", name="dup-int")
        with pytest.raises(ToolError) as exc_info:
            await create_integration(type="github", name="dup-int")
        assert "Erro ao criar integração" in exc_info.value.message


class TestListIntegrations:
    async def test_list_empty(self, integrations_env: User):
        """list_integrations sem integrações retorna lista vazia."""
        from app.mcp_server.tools.integrations import list_integrations

        result = await list_integrations()
        assert result["items"] == []
        assert result["total"] == 0
        assert result["page"] == 1
        assert result["limit"] == 50

    async def test_list_with_items(self, integrations_env: User):
        """list_integrations retorna as integrações criadas."""
        from app.mcp_server.tools.integrations import create_integration, list_integrations

        await create_integration(type="github", name="int1")
        await create_integration(type="llm", name="int2")
        result = await list_integrations()
        assert result["total"] == 2
        assert len(result["items"]) == 2

    async def test_list_config_masked(self, integrations_env: User):
        """list_integrations mascara segredos no config."""
        from app.mcp_server.tools.integrations import create_integration, list_integrations

        await create_integration(
            type="github",
            name="masked-int",
            config={"owner": "myorg", "token": "ghp_secret123"},
        )
        result = await list_integrations()
        item = result["items"][0]
        # token_encrypted deve aparecer como token: "***"
        assert item["config"].get("token") == "***"
        # owner permanece legível
        assert item["config"].get("owner") == "myorg"

    async def test_list_filter_by_type(self, integrations_env: User):
        """list_integrations com filtro de tipo."""
        from app.mcp_server.tools.integrations import create_integration, list_integrations

        await create_integration(type="github", name="gh1")
        await create_integration(type="llm", name="llm1")
        result = await list_integrations(type="github")
        assert result["total"] == 1
        assert result["items"][0]["name"] == "gh1"


class TestGetIntegration:
    async def test_get_success(self, integrations_env: User):
        """get_integration com id válido retorna a integração."""
        from app.mcp_server.tools.integrations import create_integration, get_integration

        created = await create_integration(type="github", name="get-me")
        result = await get_integration(created["id"])
        assert result["id"] == created["id"]
        assert result["name"] == "get-me"

    async def test_get_not_found(self, integrations_env: User):
        """get_integration com id inexistente lança ToolError."""
        from app.mcp_server.tools.integrations import get_integration

        with pytest.raises(ToolError) as exc_info:
            await get_integration(str(uuid.uuid4()))
        assert "Integração não encontrada" in exc_info.value.message

    async def test_get_invalid_id(self, integrations_env: User):
        """get_integration com id inválido lança ToolError."""
        from app.mcp_server.tools.integrations import get_integration

        with pytest.raises(ToolError) as exc_info:
            await get_integration("id-invalido")
        assert "ID inválido" in exc_info.value.message


class TestUpdateIntegration:
    async def test_update_name(self, integrations_env: User):
        """update_integration altera o nome."""
        from app.mcp_server.tools.integrations import create_integration, update_integration

        created = await create_integration(type="github", name="original")
        result = await update_integration(created["id"], name="renomeado")
        assert result["name"] == "renomeado"

    async def test_update_config_merge(self, integrations_env: User):
        """update_integration com config faz merge preservando valores mascarados."""
        from app.mcp_server.tools.integrations import create_integration, update_integration

        created = await create_integration(
            type="github",
            name="merge-test",
            config={"owner": "myorg", "token": "ghp_real123"},
        )
        # Atualiza owner e mantém token mascarado
        result = await update_integration(
            created["id"], config={"owner": "neworg", "token": "***"}
        )
        assert result["config"].get("owner") == "neworg"
        # token deve continuar mascarado
        assert result["config"].get("token") == "***"

    async def test_update_not_found(self, integrations_env: User):
        """update_integration com id inexistente lança ToolError."""
        from app.mcp_server.tools.integrations import update_integration

        with pytest.raises(ToolError):
            await update_integration(str(uuid.uuid4()), name="X")


class TestDeleteIntegration:
    async def test_delete_success(self, integrations_env: User):
        """delete_integration remove a integração."""
        from app.mcp_server.tools.integrations import (
            create_integration,
            delete_integration,
            get_integration,
        )

        created = await create_integration(type="github", name="delete-me")
        result = await delete_integration(created["id"])
        assert result["deleted"] is True
        assert result["id"] == created["id"]
        with pytest.raises(ToolError):
            await get_integration(created["id"])

    async def test_delete_not_found(self, integrations_env: User):
        """delete_integration com id inexistente lança ToolError."""
        from app.mcp_server.tools.integrations import delete_integration

        with pytest.raises(ToolError):
            await delete_integration(str(uuid.uuid4()))


class TestTestIntegration:
    async def test_test_github_success(self, integrations_env: User):
        """test_integration com github bem-sucedido."""
        from app.mcp_server.tools.integrations import create_integration, test_integration

        created = await create_integration(
            type="github", name="test-gh", config={"owner": "org"}
        )
        mock_provider = AsyncMock()
        mock_provider.list_repos = AsyncMock(return_value=[1, 2, 3])
        with patch(
            "app.mcp_server.tools.integrations.provider_for",
            return_value=mock_provider,
        ):
            result = await test_integration(created["id"])
        assert result["ok"] is True
        assert result["repositories"] == 3

    async def test_test_github_error(self, integrations_env: User):
        """test_integration com github em erro."""
        from app.mcp_server.tools.integrations import create_integration, test_integration
        from app.integrations.git_providers import GitProviderError

        created = await create_integration(
            type="github", name="test-gh-err", config={"owner": "org"}
        )
        mock_provider = AsyncMock()
        mock_provider.list_repos = AsyncMock(
            side_effect=GitProviderError("token inválido")
        )
        with patch(
            "app.mcp_server.tools.integrations.provider_for",
            return_value=mock_provider,
        ):
            result = await test_integration(created["id"])
        assert result["ok"] is False
        assert "token inválido" in result["error"]

    async def test_test_llm_success(self, integrations_env: User):
        """test_integration com llm bem-sucedido."""
        from app.mcp_server.tools.integrations import create_integration, test_integration

        created = await create_integration(
            type="llm",
            name="test-llm",
            config={"provider_kind": "mock", "model": "gpt-4o"},
        )
        with patch(
            "app.core.llm_providers.build_llm_client"
        ) as mock_build:
            mock_client = AsyncMock()
            mock_client.chat = AsyncMock(return_value="ok")
            mock_build.return_value = mock_client
            result = await test_integration(created["id"])
        assert result["ok"] is True
        assert result["model"] == "gpt-4o"

    async def test_test_not_found(self, integrations_env: User):
        """test_integration com id inexistente lança ToolError."""
        from app.mcp_server.tools.integrations import test_integration

        with pytest.raises(ToolError):
            await test_integration(str(uuid.uuid4()))


class TestIntegrationsAuth:
    async def test_tool_without_user_raises(self, session: AsyncSession):
        """Tool de integração sem usuário no contextvar lança ToolError."""
        from app.mcp_server.tools.integrations import create_integration

        @asynccontextmanager
        async def fake_session_factory():
            yield session

        with (
            patch(
                "app.mcp_server.tools.integrations.get_current_mcp_user",
                return_value=None,
            ),
            patch(
                "app.mcp_server.tools.integrations.async_session_factory",
                fake_session_factory,
            ),
        ):
            with pytest.raises(ToolError) as exc_info:
                await create_integration(type="github", name="sem-auth")
            assert "Não autenticado" in exc_info.value.message
