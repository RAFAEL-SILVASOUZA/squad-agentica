"""MCP client: conecta a servidores MCP via stdio, sse e http.

Dono: be-skills (FASE 4). Spec 6.7:
- stdio: spawn de processo externo, comunicacao via stdin/stdout (JSON-RPC).
- sse: Server-Sent Events (HTTP streaming).
- http: HTTP POST (JSON-RPC).
- Chama tools/list para descoberta de tools.
- Invoca tools via tools/call.

Protocolo MCP (Model Context Protocol):
- Baseado em JSON-RPC 2.0.
- Methods: initialize, tools/list, tools/call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
import signal
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Excel tools podem devolver planilhas paginadas com JSON maior que o limite
# padrão do StreamReader (64 KiB). Mantemos um teto para não aceitar linhas
# ilimitadas vindas de processos stdio.
STDIO_MAX_LINE_BYTES = 8 * 1024 * 1024

# Timeouts (segundos).
CONNECT_TIMEOUT = 30
LIST_TIMEOUT = 15
CALL_TIMEOUT = 30


class MCPClient:
    """Client para comunicacao com servidores MCP."""

    def __init__(
        self,
        transport: str,
        command: str | None = None,
        url: str | None = None,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> None:
        self._transport = transport
        self._command = command
        self._url = url
        self._env = env or {}
        self._cwd = cwd
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def connect(self) -> None:
        """Conecta ao servidor MCP e faz o handshake initialize."""
        if self._transport == "stdio":
            await self._connect_stdio()
        elif self._transport in ("sse", "http"):
            await self._connect_http()
        else:
            raise ValueError(f"Unsupported transport: {self._transport}")

    async def _connect_stdio(self) -> None:
        """Conecta via stdio (spawn de processo)."""
        if not self._command:
            raise ValueError("command is required for stdio transport")

        # Prepara ambiente.
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": "en_US.UTF-8",
        }
        env.update(self._env)

        # Split command (simples: nao usa shell).
        parts = shlex.split(self._command)
        self._process = await asyncio.create_subprocess_exec(
            *parts,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            cwd=self._cwd,
            start_new_session=True,
            limit=STDIO_MAX_LINE_BYTES,
        )

        # Handshake: initialize.
        await self._send_jsonrpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-portal", "version": "0.1.0"},
            },
        )
        self._process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await self._process.stdin.drain()

    async def _connect_http(self) -> None:
        """Conecta via HTTP/SSE (verifica acessibilidade)."""
        if not self._url:
            raise ValueError("url is required for sse/http transport")

        # Testa conectividade com um request simples.
        async with httpx.AsyncClient(timeout=CONNECT_TIMEOUT) as client:
            if self._transport == "http":
                resp = await client.post(
                    self._url,
                    json={
                        "jsonrpc": "2.0",
                        "id": self._next_id(),
                        "method": "initialize",
                        "params": {
                            "protocolVersion": "2024-11-05",
                            "capabilities": {},
                            "clientInfo": {"name": "agent-portal", "version": "0.1.0"},
                        },
                    },
                )
                resp.raise_for_status()
            else:  # sse
                # SSE: GET com Accept: text/event-stream.
                resp = await client.get(
                    self._url,
                    headers={"Accept": "text/event-stream"},
                    timeout=CONNECT_TIMEOUT,
                )
                resp.raise_for_status()

    async def _send_jsonrpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Envia um request JSON-RPC via stdio e espera a resposta."""
        if self._process is None or self._process.stdin is None or self._process.stdout is None:
            raise ConnectionError("Not connected to MCP server")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode("utf-8"))
        await self._process.stdin.drain()

        # Notificações podem vir antes da resposta correlacionada.
        timeout = {"initialize": CONNECT_TIMEOUT, "tools/call": CALL_TIMEOUT}.get(
            method, LIST_TIMEOUT
        )
        async with asyncio.timeout(timeout):
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    raise ConnectionError("MCP server closed connection")
                response = json.loads(line.decode("utf-8"))
                if response.get("id") == request["id"]:
                    break
        if "error" in response:
            raise RuntimeError(f"MCP error: {response['error']}")
        return response.get("result", {})

    async def list_tools(self) -> list[dict[str, Any]]:
        """Chama tools/list e retorna as tools descobertas.

        Returns:
            Lista de MCPToolInfo: [{name, description, inputSchema}].
        """
        if self._transport == "stdio":
            result = await self._send_jsonrpc("tools/list", {})
        else:
            result = await self._http_request("tools/list", {})

        tools = result.get("tools", [])
        return [
            {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "inputSchema": t.get("inputSchema", {}),
            }
            for t in tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoca uma tool no servidor MCP.

        Returns:
            Resultado da tool ou {"error": "..."}.
        """
        params = {"name": name, "arguments": arguments}

        if self._transport == "stdio":
            result = await self._send_jsonrpc("tools/call", params)
        else:
            result = await self._http_request("tools/call", params)

        return result

    async def _http_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Faz um request JSON-RPC via HTTP."""
        if not self._url:
            raise ValueError("url is required")

        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }

        timeout = LIST_TIMEOUT if method == "tools/list" else CALL_TIMEOUT

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(self._url, json=request)
            resp.raise_for_status()
            data = resp.json()

        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})

    async def disconnect(self) -> None:
        """Desconecta do servidor MCP."""
        if self._process is not None:
            try:
                os.killpg(self._process.pid, signal.SIGTERM)
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError):
                try:
                    os.killpg(self._process.pid, signal.SIGKILL)
                    await self._process.wait()
                except (ProcessLookupError, OSError):
                    pass
            self._process = None


async def test_mcp_connection(
    transport: str,
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Testa a conexao com um servidor MCP e retorna (status, tools).

    Returns:
        Tuple (status, discovered_tools).
        status: "connected" | "error".
    """
    status, tools, _ = await test_mcp_connection_detail(transport, command, url, env)
    return status, tools


async def test_mcp_connection_detail(
    transport: str,
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, list[dict[str, Any]], str | None]:
    """Como ``test_mcp_connection``, mais o motivo legível da falha.

    Sem o motivo a UI só mostrava "Falha na conexão" (a causa ficava no log).
    """
    client = MCPClient(
        transport=transport,
        command=command,
        url=url,
        env=env,
    )
    try:
        await client.connect()
        tools = await client.list_tools()
        return "connected", tools, None
    except Exception as e:
        logger.warning("MCP connection test failed: %s", type(e).__name__)
        return "error", [], describe_connection_error(e, transport, command, url)
    finally:
        await client.disconnect()


def describe_connection_error(
    exc: BaseException, transport: str, command: str | None, url: str | None
) -> str:
    """Mensagem em pt-BR para a falha de conexão MCP (sem segredos)."""
    if isinstance(exc, FileNotFoundError) and transport == "stdio":
        try:
            program = os.path.basename(shlex.split(command)[0]) if command else ""
        except ValueError:
            program = ""
        return (
            f"Comando '{program}' não encontrado no servidor. Servidores stdio rodam "
            "dentro do container do orchestrator: o programa precisa estar instalado lá."
        )
    if isinstance(exc, TimeoutError):
        return "O servidor MCP excedeu o tempo limite de resposta."
    if transport in ("sse", "http"):
        return "Não foi possível conectar ao servidor MCP remoto."
    return "Não foi possível executar a chamada ao servidor MCP."
