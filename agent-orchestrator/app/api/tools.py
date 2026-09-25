"""Tools custom CRUD API router.

Dono: be-skills (FASE 4). Rotas (prefixo /api):
- GET /api/tools → 200 {items, total, page, limit}
- POST /api/tools → 201 Tool
- GET /api/tools/{id} → 200 Tool / 404
- PUT /api/tools/{id} → 200 Tool / 404 / 409
- DELETE /api/tools/{id} → 204 / 404
- POST /api/tools/{id}/deploy → 200 Tool / 404 / 422
- POST /api/tools/{id}/test → 200 {result} / 404
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.tools.registry import ToolRegistry
from app.tools.sandbox import ToolSandbox

router = APIRouter(prefix="/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ToolParamSchema(BaseModel):
    """Parametro de I/O de uma tool."""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(string|number|boolean|object|array)$")
    description: str = Field(default="")
    required: bool = Field(default=False)
    defaultValue: Any = Field(default=None)


class ToolCreateRequest(BaseModel):
    """Body para POST /api/tools."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    category: str = Field(default="custom", max_length=100)
    script: str = Field(..., min_length=1)
    inputs: list[ToolParamSchema] = Field(default_factory=list)
    outputs: list[ToolParamSchema] = Field(default_factory=list)


class ToolUpdateRequest(BaseModel):
    """Body para PUT /api/tools/{id}. Todos os campos opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, max_length=100)
    script: str | None = None
    inputs: list[ToolParamSchema] | None = None
    outputs: list[ToolParamSchema] | None = None


class ToolTestRequest(BaseModel):
    """Body para POST /api/tools/{id}/test."""

    args: dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=30, ge=1, le=120)


class ToolResponse(BaseModel):
    """Response para uma tool custom."""

    id: uuid.UUID
    name: str
    description: str
    category: str
    script: str
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    version: int
    status: str
    created_at: str
    updated_at: str


class ToolListResponse(BaseModel):
    """Response para listagem de tools."""

    items: list[ToolResponse]
    total: int
    page: int
    limit: int


class ToolTestResponse(BaseModel):
    """Response para teste de tool."""

    result: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(tool: Any) -> ToolResponse:
    """Converte um model CustomTool em ToolResponse."""
    io = tool.io or {}
    return ToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        category=tool.category,
        script=tool.script,
        inputs=io.get("inputs", []),
        outputs=io.get("outputs", []),
        version=tool.version,
        status=tool.status,
        created_at=tool.created_at.isoformat() if tool.created_at else "",
        updated_at=tool.updated_at.isoformat() if tool.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=ToolListResponse)
async def list_tools(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> ToolListResponse:
    """Lista tools custom do usuario."""
    registry = ToolRegistry(db)
    items, total = await registry.list(
        user.id, page=page, limit=limit, status=status, category=category
    )
    return ToolListResponse(
        items=[_to_response(t) for t in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=ToolResponse, status_code=201)
async def create_tool(
    body: ToolCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolResponse:
    """Cria uma tool custom (status=draft)."""
    registry = ToolRegistry(db)
    io = {
        "inputs": [p.model_dump() for p in body.inputs],
        "outputs": [p.model_dump() for p in body.outputs],
    }
    tool = await registry.create(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        script=body.script,
        io=io,
    )
    return _to_response(tool)


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(
    tool_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolResponse:
    """Obtem uma tool por id."""
    registry = ToolRegistry(db)
    tool = await registry.get(tool_id, user.id)
    return _to_response(tool)


@router.put("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: uuid.UUID,
    body: ToolUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolResponse:
    """Atualiza uma tool custom."""
    registry = ToolRegistry(db)
    io = None
    if body.inputs is not None or body.outputs is not None:
        existing = await registry.get(tool_id, user.id)
        io_data = existing.io or {}
        inputs = (
            [p.model_dump() for p in body.inputs]
            if body.inputs
            else io_data.get("inputs", [])
        )
        outputs = (
            [p.model_dump() for p in body.outputs]
            if body.outputs
            else io_data.get("outputs", [])
        )
        io = {"inputs": inputs, "outputs": outputs}
    tool = await registry.update(
        tool_id=tool_id,
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        script=body.script,
        io=io,
    )
    return _to_response(tool)


@router.delete("/{tool_id}", status_code=204)
async def delete_tool(
    tool_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Arquiva uma tool (soft delete)."""
    registry = ToolRegistry(db)
    await registry.delete(tool_id, user.id)
    return Response(status_code=204)


@router.post("/{tool_id}/deploy", response_model=ToolResponse)
async def deploy_tool(
    tool_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolResponse:
    """Deploy: valida o script e marca como deployed."""
    registry = ToolRegistry(db)
    tool = await registry.deploy(tool_id, user.id)
    return _to_response(tool)


@router.post("/{tool_id}/test", response_model=ToolTestResponse)
async def test_tool(
    tool_id: uuid.UUID,
    body: ToolTestRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ToolTestResponse:
    """Testa uma tool com parametros de exemplo."""
    registry = ToolRegistry(db)
    tool = await registry.get(tool_id, user.id)

    sandbox = ToolSandbox(timeout=body.timeout)
    result = await sandbox.execute(script=tool.script, args=body.args, timeout=body.timeout)
    return ToolTestResponse(result=result)
