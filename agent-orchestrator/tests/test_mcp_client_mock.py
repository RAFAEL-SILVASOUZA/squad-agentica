"""Tests for MCP client with mock/fake server.

Dono: be-skills (FASE 4). Testa o client MCP com mocks:
- HTTP: mock do httpx (tools/list, tools/call).
- Stdio: teste de conexao falha (comando inexistente).
- O teste de conexao bem-sucedida via stdio requer um servidor MCP real
  e e coberto nos testes de integracao (FASE 6).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.mcp.client import MCPClient
from app.mcp.client import test_mcp_connection as _test_mcp_connection

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMCPClientHTTP:
    """Testa o client MCP via HTTP com mock do httpx."""

    def _make_mock_response(self, result: dict) -> AsyncMock:
        """Cria um mock de response httpx."""
        mock_response = AsyncMock()
        mock_response.json = lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "result": result,
        }
        mock_response.raise_for_status = lambda: None
        return mock_response

    async def test_http_list_tools(self) -> None:
        """Mock do httpx para testar tools/list via HTTP."""
        mock_response = self._make_mock_response(
            {
                "tools": [
                    {"name": "test_tool", "description": "A test", "inputSchema": {}},
                    {
                        "name": "another_tool",
                        "description": "Another",
                        "inputSchema": {"type": "object"},
                    },
                ]
            }
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.mcp.client.httpx.AsyncClient", return_value=mock_client):
            client = MCPClient(
                transport="http",
                url="http://localhost:9000/mcp",
            )
            await client.connect()
            tools = await client.list_tools()
            assert len(tools) == 2
            assert tools[0]["name"] == "test_tool"
            assert tools[0]["description"] == "A test"
            assert tools[1]["name"] == "another_tool"

    async def test_http_call_tool(self) -> None:
        """Mock do httpx para testar tools/call via HTTP."""
        mock_response = self._make_mock_response({"content": [{"type": "text", "text": "done"}]})

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.mcp.client.httpx.AsyncClient", return_value=mock_client):
            client = MCPClient(
                transport="http",
                url="http://localhost:9000/mcp",
            )
            await client.connect()
            result = await client.call_tool("test_tool", {"arg": "val"})
            assert result["content"][0]["text"] == "done"

    async def test_http_error_response(self) -> None:
        """Mock do httpx para testar erro no servidor MCP."""
        mock_response = AsyncMock()
        mock_response.json = lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.mcp.client.httpx.AsyncClient", return_value=mock_client):
            client = MCPClient(
                transport="http",
                url="http://localhost:9000/mcp",
            )
            await client.connect()
            with pytest.raises(RuntimeError, match="MCP error"):
                await client.list_tools()


class TestMCPConnectionHelper:
    """Testa a funcao test_mcp_connection."""

    async def test_failed_connection(self) -> None:
        """Conexao falha retorna status=error."""
        status, tools = await _test_mcp_connection(
            transport="stdio",
            command="nonexistent-command-xyz",
        )
        assert status == "error"
        assert tools == []

    async def test_http_successful_connection(self) -> None:
        """Conexao HTTP bem-sucedida retorna status=connected e tools."""
        mock_response = AsyncMock()
        mock_response.json = lambda: {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "t1", "description": "Tool 1", "inputSchema": {}},
                ]
            },
        }
        mock_response.raise_for_status = lambda: None

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.mcp.client.httpx.AsyncClient", return_value=mock_client):
            status, tools = await _test_mcp_connection(
                transport="http",
                url="http://localhost:9000/mcp",
            )
            assert status == "connected"
            assert len(tools) == 1
            assert tools[0]["name"] == "t1"


class TestMCPClientValidation:
    """Testa validacoes basicas do client."""

    async def test_stdio_requires_command(self) -> None:
        """stdio sem command deve falhar."""
        client = MCPClient(transport="stdio", command=None)
        with pytest.raises(ValueError, match="command"):
            await client.connect()

    async def test_http_requires_url(self) -> None:
        """http sem url deve falhar."""
        client = MCPClient(transport="http", url=None)
        with pytest.raises(ValueError, match="url"):
            await client.connect()

    async def test_invalid_transport(self) -> None:
        """Transport invalido deve falhar."""
        client = MCPClient(transport="websocket")
        with pytest.raises(ValueError, match="Unsupported"):
            await client.connect()


def test_describe_missing_stdio_command():
    """F: a UI mostrava só "Falha na conexão"; o motivo agora vai na resposta."""
    from app.mcp.client import describe_connection_error

    msg = describe_connection_error(
        FileNotFoundError(2, "No such file or directory"), "stdio", "npx -y server", None
    )
    assert "npx" in msg and "não encontrado" in msg


def test_describe_unreachable_url():
    from app.mcp.client import describe_connection_error

    msg = describe_connection_error(
        ConnectionError("Name or service not known"), "sse", None, "http://x.local/sse"
    )
    assert msg == "Não foi possível conectar ao servidor MCP remoto."
