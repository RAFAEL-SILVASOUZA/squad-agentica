"""MCP servers CRUD API router.

Dono: be-skills (FASE 4). Rotas (prefixo /api):
- GET /api/mcp-servers → 200 {items, total, page, limit}
- POST /api/mcp-servers → 201 MCPServer
- GET /api/mcp-servers/{id} → 200 MCPServer / 404
- PUT /api/mcp-servers/{id} → 200 MCPServer / 404 / 409
- DELETE /api/mcp-servers/{id} → 204 / 404
- POST /api/mcp-servers/{id}/test → 200 {status, discoveredTools} / 404
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.db.models import User
from app.db.session import get_db
from app.mcp.client import test_mcp_connection_detail
from app.mcp.registry import MCPRegistry
from app.mcp.validator import validate_mcp_config

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class MCPServerCreateRequest(BaseModel):
    """Body para POST /api/mcp-servers."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    transport: str = Field(..., pattern="^(stdio|sse|http)$")
    command: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=500)
    env: dict[str, str] = Field(default_factory=dict)


class MCPServerUpdateRequest(BaseModel):
    """Body para PUT /api/mcp-servers/{id}. Todos os campos opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    transport: str | None = Field(default=None, pattern="^(stdio|sse|http)$")
    command: str | None = Field(default=None, max_length=500)
    url: str | None = Field(default=None, max_length=500)
    env: dict[str, str] | None = None


class MCPToolInfoResponse(BaseModel):
    """Info de uma tool descoberta via MCP."""

    name: str
    description: str
    inputSchema: dict[str, Any]


class MCPServerResponse(BaseModel):
    """Response para um servidor MCP."""

    id: uuid.UUID
    name: str
    description: str
    transport: str
    command: str | None
    url: str | None
    env: dict[str, str]
    status: str
    lastConnectedAt: str | None
    discoveredTools: list[MCPToolInfoResponse]
    createdAt: str
    updatedAt: str


class MCPServerListResponse(BaseModel):
    """Response para listagem de servidores MCP."""

    items: list[MCPServerResponse]
    total: int
    page: int
    limit: int


class MCPServerTestResponse(BaseModel):
    """Response para teste de conexao MCP."""

    status: str
    discoveredTools: list[MCPToolInfoResponse]
    # Motivo legível quando status == "error" (acréscimo ao contrato mínimo).
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MASKED = "***"


def _mask_env(env: dict[str, str] | None) -> dict[str, str]:
    """Mascara os valores de ``env`` (F12/contrato §8: segredos nunca são
    devolvidos em resposta). As chaves permanecem (o portal mostra quais
    variáveis estão configuradas); os valores viram ``***``."""
    return {k: _MASKED for k in (env or {})}


def _to_response(server: Any) -> MCPServerResponse:
    """Converte um model MCPServer em MCPServerResponse."""
    tools = [
        MCPToolInfoResponse(
            name=t.get("name", ""),
            description=t.get("description", ""),
            inputSchema=t.get("inputSchema", {}),
        )
        for t in (server.discovered_tools or [])
    ]
    return MCPServerResponse(
        id=server.id,
        name=server.name,
        description=server.description,
        transport=server.transport,
        command=server.command,
        url=server.url,
        env=_mask_env(server.env),
        status=server.status,
        lastConnectedAt=server.last_connected_at.isoformat() if server.last_connected_at else None,
        discoveredTools=tools,
        createdAt=server.created_at.isoformat() if server.created_at else "",
        updatedAt=server.updated_at.isoformat() if server.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=MCPServerListResponse)
async def list_mcp_servers(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    transport: str | None = Query(default=None),
    status: str | None = Query(default=None),
) -> MCPServerListResponse:
    """Lista servidores MCP do usuario."""
    registry = MCPRegistry(db)
    items, total = await registry.list(
        user.id, page=page, limit=limit, transport=transport, status=status
    )
    return MCPServerListResponse(
        items=[_to_response(s) for s in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=MCPServerResponse, status_code=201)
async def create_mcp_server(
    body: MCPServerCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MCPServerResponse:
    """Registra um servidor MCP."""
    # Valida a configuracao.
    errors = validate_mcp_config(
        transport=body.transport,
        command=body.command,
        url=body.url,
        env=body.env,
    )
    if errors:
        raise AppError(422, "validation failed", "mcp_config_invalid", {"errors": errors})

    registry = MCPRegistry(db)
    server = await registry.create(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        transport=body.transport,
        command=body.command,
        url=body.url,
        env=body.env,
    )
    return _to_response(server)


@router.get("/{server_id}", response_model=MCPServerResponse)
async def get_mcp_server(
    server_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MCPServerResponse:
    """Obtem um servidor MCP por id."""
    registry = MCPRegistry(db)
    server = await registry.get(server_id, user.id)
    return _to_response(server)


@router.put("/{server_id}", response_model=MCPServerResponse)
async def update_mcp_server(
    server_id: uuid.UUID,
    body: MCPServerUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MCPServerResponse:
    """Atualiza um servidor MCP."""
    registry = MCPRegistry(db)
    existing = await registry.get(server_id, user.id)

    # F12: se o cliente devolve o valor mascarado (``***``) de uma chave
    # existente, mantemos o valor real gravado (o valor real nunca é exposto,
    # então "não mexer" é expresso assim).
    env_to_save = None
    if body.env is not None:
        merged = dict(existing.env or {})
        for k, v in body.env.items():
            if v == _MASKED and k in (existing.env or {}):
                merged[k] = existing.env[k]
            else:
                merged[k] = v
        env_to_save = merged

    # Se transport/command/url mudaram, valida a nova config.
    if body.transport or body.command or body.url or body.env is not None:
        errors = validate_mcp_config(
            transport=body.transport or existing.transport,
            command=body.command if body.command is not None else existing.command,
            url=body.url if body.url is not None else existing.url,
            env=env_to_save if env_to_save is not None else (existing.env or {}),
        )
        if errors:
            raise AppError(422, "validation failed", "mcp_config_invalid", {"errors": errors})

    server = await registry.update(
        server_id=server_id,
        owner_id=user.id,
        name=body.name,
        description=body.description,
        transport=body.transport,
        command=body.command,
        url=body.url,
        env=env_to_save,
    )
    return _to_response(server)


@router.delete("/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove um servidor MCP."""
    registry = MCPRegistry(db)
    await registry.delete(server_id, user.id)
    return Response(status_code=204)


@router.post("/{server_id}/test", response_model=MCPServerTestResponse)
async def test_mcp_server(
    server_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MCPServerTestResponse:
    """Testa a conexao com o servidor MCP (chama tools/list)."""
    registry = MCPRegistry(db)
    server = await registry.get(server_id, user.id)

    # Testa a conexao.
    status, tools, error = await test_mcp_connection_detail(
        transport=server.transport,
        command=server.command,
        url=server.url,
        env=server.env,
    )

    # Atualiza o status no banco.
    await registry.update_connection_status(
        server_id=server_id,
        owner_id=user.id,
        status=status,
        discovered_tools=tools if status == "connected" else None,
    )

    tool_infos = [
        MCPToolInfoResponse(
            name=t.get("name", ""),
            description=t.get("description", ""),
            inputSchema=t.get("inputSchema", {}),
        )
        for t in tools
    ]
    return MCPServerTestResponse(status=status, discoveredTools=tool_infos, error=error)
