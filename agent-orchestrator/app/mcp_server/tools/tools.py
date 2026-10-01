"""Ferramentas MCP de Tools custom (CRUD).

Registra as ferramentas de gerenciamento de tools custom no servidor MCP.
Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
delega a operação ao ``ToolRegistry`` (mesmo service usado pelo router REST).

Erros do registry (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.core.errors import AppError
from app.db.models import CustomTool
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError
from app.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PARAM_TYPES = {"string", "number", "boolean", "object", "array"}


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _normalize_param(p: dict[str, Any]) -> dict[str, Any]:
    """Normaliza um parâmetro de I/O (valida type, preenche defaults)."""
    param = dict(p)
    ptype = param.get("type")
    if ptype and ptype not in _VALID_PARAM_TYPES:
        raise ToolError(
            f"Tipo de parâmetro inválido: {ptype}. "
            "Use string, number, boolean, object ou array."
        )
    param.setdefault("type", "string")
    param.setdefault("description", "")
    param.setdefault("required", False)
    return param


def _tool_to_dict(tool: CustomTool) -> dict[str, Any]:
    """Converte o model CustomTool para dict (camelCase, como a API)."""
    io = tool.io or {}
    status_val = (
        tool.status.value if hasattr(tool.status, "value") else str(tool.status)
    )
    return {
        "id": str(tool.id),
        "name": tool.name,
        "description": tool.description,
        "category": tool.category,
        "script": tool.script,
        "inputs": io.get("inputs", []),
        "outputs": io.get("outputs", []),
        "version": tool.version,
        "status": status_val,
        "createdAt": tool.created_at.isoformat() if tool.created_at else "",
        "updatedAt": tool.updated_at.isoformat() if tool.updated_at else "",
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_tool(
    name: str,
    description: str = "",
    category: str = "custom",
    script: str = "",
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Cria uma nova tool custom (status=draft).

    ``script`` é o código Python da tool. ``inputs``/``outputs`` são listas de
    parâmetros ``{name, type, description, required, defaultValue}``.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    io = {
        "inputs": [_normalize_param(p) for p in (inputs or [])],
        "outputs": [_normalize_param(p) for p in (outputs or [])],
    }

    async with async_session_factory() as db:
        registry = ToolRegistry(db)
        try:
            tool = await registry.create(
                owner_id=user.id,
                name=name,
                description=description,
                category=category,
                script=script,
                io=io,
            )
        except AppError as e:
            raise ToolError(f"Erro ao criar tool: {e.error}") from e
        return _tool_to_dict(tool)


@mcp.tool()
async def list_tools(
    page: int = 1,
    limit: int = 50,
    status: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Lista as tools custom do usuário autenticado, com paginação e filtros opcionais."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        registry = ToolRegistry(db)
        try:
            items, total = await registry.list(
                user.id, page=page, limit=limit, status=status, category=category
            )
        except AppError as e:
            raise ToolError(f"Erro ao listar tools: {e.error}") from e
        return {
            "items": [_tool_to_dict(t) for t in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_tool(tool_id: str) -> dict[str, Any]:
    """Obtém uma tool custom por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(tool_id)

    async with async_session_factory() as db:
        registry = ToolRegistry(db)
        try:
            tool = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Tool não encontrada: {e.error}") from e
        return _tool_to_dict(tool)


@mcp.tool()
async def update_tool(
    tool_id: str,
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    script: str | None = None,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Atualiza uma tool custom (partial update: só os campos informados são alterados).

    Se ``script`` mudar, o status volta para 'draft'. Pelo menos um campo além
    de ``tool_id`` deve ser fornecido; caso contrário, retorna erro.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(tool_id)

    if all(
        v is None
        for v in (name, description, category, script, inputs, outputs)
    ):
        raise ToolError("Nenhum campo para atualizar foi fornecido.")

    async with async_session_factory() as db:
        registry = ToolRegistry(db)

        io = None
        if inputs is not None or outputs is not None:
            existing = await registry.get(parsed_id, user.id)
            io_data = existing.io or {}
            io = {
                "inputs": [_normalize_param(p) for p in inputs] if inputs else io_data.get("inputs", []),
                "outputs": [_normalize_param(p) for p in outputs] if outputs else io_data.get("outputs", []),
            }

        try:
            tool = await registry.update(
                tool_id=parsed_id,
                owner_id=user.id,
                name=name,
                description=description,
                category=category,
                script=script,
                io=io,
            )
        except AppError as e:
            raise ToolError(f"Erro ao atualizar tool: {e.error}") from e
        return _tool_to_dict(tool)


@mcp.tool()
async def delete_tool(tool_id: str) -> dict[str, Any]:
    """Arquiva uma tool custom (soft delete, status=archived)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(tool_id)

    async with async_session_factory() as db:
        registry = ToolRegistry(db)
        try:
            await registry.delete(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Tool não encontrada: {e.error}") from e
        return {"deleted": True, "id": tool_id}
