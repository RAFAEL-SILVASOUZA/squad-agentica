"""Ferramentas MCP de servidores MCP (CRUD + teste de conexão).

Registra as ferramentas de gerenciamento de servidores MCP no servidor MCP.
Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
delega a operação ao ``MCPRegistry``.

Erros do registry (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import AppError
from app.db.models import MCPServer
from app.db.session import async_session_factory
from app.mcp.client import test_mcp_connection_detail
from app.mcp.registry import MCPRegistry
from app.mcp.validator import validate_mcp_config
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MASKED = "***"


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _mask_env(env: dict[str, str] | None) -> dict[str, str]:
    """Mascara os valores de env (segredos nunca são devolvidos)."""
    return {k: _MASKED for k in (env or {})}


def _server_to_dict(server: MCPServer) -> dict[str, Any]:
    """Converte o model MCPServer para dict (camelCase, como a API)."""
    tools = [
        {
            "name": t.get("name", ""),
            "description": t.get("description", ""),
            "inputSchema": t.get("inputSchema", {}),
        }
        for t in (server.discovered_tools or [])
    ]
    return {
        "id": str(server.id),
        "name": server.name,
        "description": server.description,
        "transport": server.transport.value if hasattr(server.transport, "value") else str(server.transport),
        "command": server.command,
        "url": server.url,
        "env": _mask_env(server.env),
        "status": server.status.value if hasattr(server.status, "value") else str(server.status),
        "lastConnectedAt": server.last_connected_at.isoformat() if server.last_connected_at else None,
        "discoveredTools": tools,
        "createdAt": server.created_at.isoformat() if server.created_at else "",
        "updatedAt": server.updated_at.isoformat() if server.updated_at else "",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_mcp_server(
    name: str,
    description: str = "",
    transport: str = "stdio",
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Cria um novo servidor MCP.

    Valida a configuração de conexão antes de persistir. O transport pode ser
    'stdio' (requer command), 'sse' ou 'http' (requer url).
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    # Valida a configuração.
    errors = validate_mcp_config(
        transport=transport,
        command=command,
        url=url,
        env=env,
    )
    if errors:
        raise ToolError(f"Configuração inválida: {errors}")

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            server = await registry.create(
                owner_id=user.id,
                name=name,
                description=description,
                transport=transport,
                command=command,
                url=url,
                env=env or {},
            )
        except AppError as e:
            raise ToolError(f"Erro ao criar servidor MCP: {e.error}") from e
        return _server_to_dict(server)


@mcp.tool()
async def list_mcp_servers(
    page: int = 1,
    limit: int = 50,
    transport: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Lista os servidores MCP do usuário autenticado, com paginação e filtros opcionais."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            items, total = await registry.list(
                owner_id=user.id,
                page=page,
                limit=limit,
                transport=transport,
                status=status,
            )
        except AppError as e:
            raise ToolError(f"Erro ao listar servidores MCP: {e.error}") from e
        return {
            "items": [_server_to_dict(s) for s in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_mcp_server(server_id: str) -> dict[str, Any]:
    """Obtém um servidor MCP por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(server_id)

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            server = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Servidor MCP não encontrado: {e.error}") from e
        return _server_to_dict(server)


@mcp.tool()
async def update_mcp_server(
    server_id: str,
    name: str | None = None,
    description: str | None = None,
    transport: str | None = None,
    command: str | None = None,
    url: str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Atualiza um servidor MCP (partial update: só os campos informados são alterados).

    Se env for fornecido, faz merge com o env existente. Chaves com valor
    '***' mantêm o valor real gravado. Se transport/command/url mudarem,
    a configuração é revalidada.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(server_id)

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            existing = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Servidor MCP não encontrado: {e.error}") from e

        # Merge de env: valores mascarados mantêm o valor real.
        env_to_save = None
        if env is not None:
            merged = dict(existing.env or {})
            for k, v in env.items():
                if v == _MASKED and k in (existing.env or {}):
                    merged[k] = existing.env[k]
                else:
                    merged[k] = v
            env_to_save = merged

        # Se transport/command/url mudaram, valida a nova config.
        if transport or command or url or env is not None:
            errors = validate_mcp_config(
                transport=transport or existing.transport.value if hasattr(existing.transport, "value") else existing.transport,
                command=command if command is not None else existing.command,
                url=url if url is not None else existing.url,
                env=env_to_save if env_to_save is not None else (existing.env or {}),
            )
            if errors:
                raise ToolError(f"Configuração inválida: {errors}")

        try:
            server = await registry.update(
                server_id=parsed_id,
                owner_id=user.id,
                name=name,
                description=description,
                transport=transport,
                command=command,
                url=url,
                env=env_to_save,
            )
        except AppError as e:
            raise ToolError(f"Erro ao atualizar servidor MCP: {e.error}") from e
        return _server_to_dict(server)


@mcp.tool()
async def delete_mcp_server(server_id: str) -> dict[str, Any]:
    """Remove um servidor MCP (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(server_id)

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            await registry.delete(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Servidor MCP não encontrado: {e.error}") from e
        return {"deleted": True, "id": server_id}


@mcp.tool()
async def test_mcp_server(server_id: str) -> dict[str, Any]:
    """Testa a conexão com um servidor MCP (chama tools/list).

    Atualiza o status de conexão e as tools descobertas no banco.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(server_id)

    async with async_session_factory() as db:
        registry = MCPRegistry(db)
        try:
            server = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Servidor MCP não encontrado: {e.error}") from e

        try:
            status, tools, error = await test_mcp_connection_detail(
                transport=server.transport.value if hasattr(server.transport, "value") else server.transport,
                command=server.command,
                url=server.url,
                env=server.env,
            )
        except Exception as e:
            raise ToolError(f"Erro ao testar servidor MCP: {e}") from e

        await registry.update_connection_status(
            server_id=parsed_id,
            owner_id=user.id,
            status=status,
            discovered_tools=tools if status == "connected" else None,
        )

        return {
            "status": status,
            "discoveredTools": tools,
            "error": error,
        }
