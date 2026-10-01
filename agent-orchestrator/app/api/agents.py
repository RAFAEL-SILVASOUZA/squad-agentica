"""Agents CRUD API router.

Dono: be-agents (FASE 4). Rotas (prefixo /api):
- POST /api/agents → 201 Agent
- GET /api/agents?page=&limit=&type= → 200 {items, total, page, limit}
- GET /api/agents/{id} → 200 Agent / 404
- PUT /api/agents/{id} → 200 Agent / 404 / 409
- DELETE /api/agents/{id} → 204 / 404 / 409

Chat de construção (POST /api/agents/chat, POST /api/agents/{id}/chat)
é do nó Backend Agent Builder Chat (roda depois).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.service import AgentService
from app.auth.dependencies import get_current_user
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Integration, User
from app.db.session import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


# ---------------------------------------------------------------------------
# Schemas (request/response)
# ---------------------------------------------------------------------------


class AgentCreateRequest(BaseModel):
    """Body para POST /api/agents."""

    name: str = Field(..., min_length=1, max_length=200)
    type: str = Field(default="custom", max_length=100)
    description: str = Field(default="")
    prompt: str = Field(default="")
    strategy: str = Field(default="")
    skills: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    mcpServers: list[dict[str, Any]] = Field(default_factory=list)
    knowledge: list[dict[str, Any]] = Field(default_factory=list)
    integrations: list[dict[str, Any]] = Field(default_factory=list)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    model: str = Field(default="gpt-4o", max_length=100)
    # Adendo 8: escolha opcional de LLM por agente: {integrationId, model}.
    llm: dict[str, Any] | None = None
    maxIterations: int = Field(default=10, ge=1, le=1000)
    timeout: int = Field(default=300, ge=1, le=3600)
    shellAccess: bool = Field(default=False)


class AgentUpdateRequest(BaseModel):
    """Body para PUT /api/agents/{id}. Todos os campos opcionais (partial update)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    type: str | None = Field(default=None, max_length=100)
    description: str | None = None
    prompt: str | None = None
    strategy: str | None = None
    skills: list[dict[str, Any]] | None = None
    tools: list[dict[str, Any]] | None = None
    mcpServers: list[dict[str, Any]] | None = None
    knowledge: list[dict[str, Any]] | None = None
    integrations: list[dict[str, Any]] | None = None
    inputs: list[dict[str, Any]] | None = None
    outputs: list[dict[str, Any]] | None = None
    actions: list[str] | None = None
    model: str | None = Field(default=None, max_length=100)
    llm: dict[str, Any] | None = None
    maxIterations: int | None = Field(default=None, ge=1, le=1000)
    timeout: int | None = Field(default=None, ge=1, le=3600)
    shellAccess: bool | None = None


class AgentResponse(BaseModel):
    """Response para GET/POST/PUT /api/agents."""

    id: str
    ownerId: str
    name: str
    type: str
    description: str
    prompt: str
    strategy: str
    skills: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    mcpServers: list[dict[str, Any]]
    knowledge: list[dict[str, Any]]
    integrations: list[dict[str, Any]]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    actions: list[str]
    model: str
    # Adendo 8: escolha opcional de LLM por agente: {integrationId, model}.
    llm: dict[str, Any] | None = None
    # Modelo realmente usado (adendo 8): agente > padrão do usuário > ambiente.
    effectiveModel: str
    maxIterations: int
    timeout: int
    shellAccess: bool
    createdAt: str
    updatedAt: str


class AgentListResponse(BaseModel):
    """Response para GET /api/agents."""

    items: list[AgentResponse]
    total: int
    page: int
    limit: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _resolve_effective_model(
    db: AsyncSession, agent, user: User | None
) -> str:
    """Modelo efetivo do agente (adendo 8): agente > padrão do usuário > ambiente.

    1) escolha no agente (``agent.llm``): o ``model`` escolhido, ou o modelo
       padrão da integração referenciada (adendo 8.4: se o modelo some da
       conexão, usa o padrão da conexão);
    2) padrão do usuário (``user.preferences['default_llm_integration_id']``);
    3) padrão do ambiente (``LLM_MODEL``) ou o ``model`` do agente.

    O ``LLM_MODEL`` do ambiente deixa de sobrescrever um modelo escolhido
    explicitamente: só vale quando não há escolha (regra 3).
    """
    # 1) escolha no agente.
    if agent.llm:
        integration_id = str(agent.llm.get("integrationId") or "")
        chosen_model = str(agent.llm.get("model") or "")
        if integration_id:
            cfg = await _llm_integration_config(db, agent.owner_id, integration_id)
            if cfg is not None:
                if chosen_model:
                    return chosen_model
                return str(cfg.get("default_model") or agent.model)
        if chosen_model:
            return chosen_model

    # 2) padrão do usuário.
    if user is not None and user.preferences:
        default_id = str(user.preferences.get("default_llm_integration_id") or "")
        if default_id:
            cfg = await _llm_integration_config(db, agent.owner_id, default_id)
            if cfg is not None:
                return str(cfg.get("default_model") or agent.model)

    # 3) padrão do ambiente (LLM_MODEL) ou o model do agente.
    return settings.llm_model or agent.model


async def _llm_integration_config(
    db: AsyncSession, owner_id: uuid.UUID, integration_id: str
) -> dict[str, Any] | None:
    """Config de uma integração LLM do dono (ou None se não existir)."""
    try:
        iid = uuid.UUID(integration_id)
    except (ValueError, TypeError):
        return None
    result = await db.execute(
        select(Integration).where(
            Integration.id == iid,
            Integration.owner_id == owner_id,
            Integration.type == "llm",
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        return None
    return integration.config or {}


async def _agent_to_response(
    agent, db: AsyncSession, user: User | None = None
) -> AgentResponse:
    """Converte o model SQLAlchemy para o schema de resposta (camelCase)."""
    effective_model = await _resolve_effective_model(db, agent, user)
    return AgentResponse(
        id=str(agent.id),
        ownerId=str(agent.owner_id),
        name=agent.name,
        type=agent.type,
        description=agent.description,
        prompt=agent.prompt,
        strategy=agent.strategy,
        skills=agent.skills,
        tools=agent.tools,
        mcpServers=agent.mcp_servers,
        knowledge=agent.knowledge,
        integrations=agent.integrations,
        inputs=agent.inputs,
        outputs=agent.outputs,
        actions=agent.actions,
        model=agent.model,
        llm=agent.llm,
        effectiveModel=effective_model,
        maxIterations=agent.max_iterations,
        timeout=agent.timeout,
        shellAccess=agent.shell_access,
        createdAt=agent.created_at.isoformat() if agent.created_at else "",
        updatedAt=agent.updated_at.isoformat() if agent.updated_at else "",
    )


def _get_service() -> AgentService:
    """Cria uma instância do AgentService (o storage é resolvido aqui)."""
    return AgentService()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=AgentResponse)
async def create_agent(
    body: AgentCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AgentResponse:
    """Cria um agente. Valida contrato, persiste no Postgres + Garage."""
    service = _get_service()
    data = body.model_dump(exclude_none=True)
    agent = await service.create_agent(db, user.id, data)
    return await _agent_to_response(agent, db, user)


@router.get("", response_model=AgentListResponse)
async def list_agents(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    type: str | None = Query(default=None, description="Filtro por tipo de agente"),
) -> AgentListResponse:
    """Lista agentes do usuário com paginação e filtro opcional por type."""
    service = _get_service()
    agents, total = await service.list_agents(db, user.id, page=page, limit=limit, type_filter=type)
    return AgentListResponse(
        items=[await _agent_to_response(a, db, user) for a in agents],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AgentResponse:
    """Obtém um agente por id."""
    service = _get_service()
    agent = await service.get_agent(db, user.id, agent_id)
    return await _agent_to_response(agent, db, user)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    body: AgentUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> AgentResponse:
    """Atualiza um agente (partial update)."""
    service = _get_service()
    data = body.model_dump(exclude_none=True)
    if not data:
        details = {"errors": [{"rule": "body", "message": "At least one field must be provided"}]}
        raise AppError(400, "validation error", "empty_update", details)
    agent = await service.update_agent(db, user.id, agent_id, data)
    return await _agent_to_response(agent, db, user)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Remove um agente."""
    service = _get_service()
    await service.delete_agent(db, user.id, agent_id)
    return Response(status_code=204)
