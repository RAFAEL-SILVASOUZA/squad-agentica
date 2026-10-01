"""Ferramentas MCP de agentes (CRUD).

Registra as ferramentas de gerenciamento de agentes no servidor MCP. Cada
ferramenta lê o usuário autenticado via ``get_current_mcp_user`` (contextvar
populado pelo middleware de autenticação, Task 3) e delega a operação ao
``AgentService`` (mesmo service usado pelo router REST).

Erros do service (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.service import AgentService
from app.core.errors import AppError
from app.db.models import Agent
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_to_dict(agent: Agent) -> dict[str, Any]:
    """Converte o model SQLAlchemy de agente para dict (camelCase, como a API)."""
    return {
        "id": str(agent.id),
        "ownerId": str(agent.owner_id),
        "name": agent.name,
        "type": agent.type,
        "description": agent.description,
        "prompt": agent.prompt,
        "strategy": agent.strategy,
        "skills": agent.skills,
        "tools": agent.tools,
        "mcpServers": agent.mcp_servers,
        "knowledge": agent.knowledge,
        "integrations": agent.integrations,
        "inputs": agent.inputs,
        "outputs": agent.outputs,
        "actions": agent.actions,
        "model": agent.model,
        "llm": agent.llm,
        "maxIterations": agent.max_iterations,
        "timeout": agent.timeout,
        "shellAccess": agent.shell_access,
        "createdAt": agent.created_at.isoformat() if agent.created_at else "",
        "updatedAt": agent.updated_at.isoformat() if agent.updated_at else "",
    }


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_agent(
    name: str,
    description: str = "",
    prompt: str = "",
    strategy: str = "",
    type: str = "custom",
    model: str = "gpt-4o",
    max_iterations: int = 10,
    timeout: int = 300,
    shell_access: bool = False,
    skills: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    knowledge: list[dict[str, Any]] | None = None,
    integrations: list[dict[str, Any]] | None = None,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    actions: list[str] | None = None,
    llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cria um novo agente.

    Os campos de mochila (skills, tools, mcpServers, knowledge, integrations)
    e de contrato (inputs, outputs, actions) são opcionais e defaultam para
    listas vazias. O contrato (inputs/outputs/actions) é validado pelo
    service; um contrato inválido retorna erro.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    data: dict[str, Any] = {
        "name": name,
        "type": type,
        "description": description,
        "prompt": prompt,
        "strategy": strategy,
        "skills": skills or [],
        "tools": tools or [],
        "mcpServers": mcp_servers or [],
        "knowledge": knowledge or [],
        "integrations": integrations or [],
        "inputs": inputs or [],
        "outputs": outputs or [],
        "actions": actions or [],
        "model": model,
        "llm": llm,
        "maxIterations": max_iterations,
        "timeout": timeout,
        "shellAccess": shell_access,
    }

    async with async_session_factory() as db:
        service = AgentService()
        try:
            agent = await service.create_agent(db, user.id, data)
        except AppError as e:
            raise ToolError(f"Erro ao criar agente: {e.error}") from e
        return _agent_to_dict(agent)


@mcp.tool()
async def list_agents(
    page: int = 1,
    limit: int = 20,
    type_filter: str | None = None,
) -> dict[str, Any]:
    """Lista os agentes do usuário autenticado, com paginação e filtro opcional por tipo."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        service = AgentService()
        try:
            agents, total = await service.list_agents(
                db, user.id, page=page, limit=limit, type_filter=type_filter
            )
        except AppError as e:
            raise ToolError(f"Erro ao listar agentes: {e.error}") from e
        return {
            "items": [_agent_to_dict(a) for a in agents],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Obtém um agente por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(agent_id)

    async with async_session_factory() as db:
        service = AgentService()
        try:
            agent = await service.get_agent(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Erro ao obter agente: {e.error}") from e
        return _agent_to_dict(agent)


@mcp.tool()
async def update_agent(
    agent_id: str,
    name: str | None = None,
    description: str | None = None,
    prompt: str | None = None,
    strategy: str | None = None,
    type: str | None = None,
    model: str | None = None,
    max_iterations: int | None = None,
    timeout: int | None = None,
    shell_access: bool | None = None,
    skills: list[dict[str, Any]] | None = None,
    tools: list[dict[str, Any]] | None = None,
    mcp_servers: list[dict[str, Any]] | None = None,
    knowledge: list[dict[str, Any]] | None = None,
    integrations: list[dict[str, Any]] | None = None,
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    actions: list[str] | None = None,
    llm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Atualiza um agente (partial update: só os campos informados são alterados).

    Pelo menos um campo além de ``agent_id`` deve ser fornecido; caso
    contrário, retorna erro.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(agent_id)

    # Monta o dict de dados apenas com os campos não-None (partial update).
    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if description is not None:
        data["description"] = description
    if prompt is not None:
        data["prompt"] = prompt
    if strategy is not None:
        data["strategy"] = strategy
    if type is not None:
        data["type"] = type
    if model is not None:
        data["model"] = model
    if max_iterations is not None:
        data["maxIterations"] = max_iterations
    if timeout is not None:
        data["timeout"] = timeout
    if shell_access is not None:
        data["shellAccess"] = shell_access
    if skills is not None:
        data["skills"] = skills
    if tools is not None:
        data["tools"] = tools
    if mcp_servers is not None:
        data["mcpServers"] = mcp_servers
    if knowledge is not None:
        data["knowledge"] = knowledge
    if integrations is not None:
        data["integrations"] = integrations
    if inputs is not None:
        data["inputs"] = inputs
    if outputs is not None:
        data["outputs"] = outputs
    if actions is not None:
        data["actions"] = actions
    if llm is not None:
        data["llm"] = llm

    if not data:
        raise ToolError("Nenhum campo para atualizar foi fornecido.")

    async with async_session_factory() as db:
        service = AgentService()
        try:
            agent = await service.update_agent(db, user.id, parsed_id, data)
        except AppError as e:
            raise ToolError(f"Erro ao atualizar agente: {e.error}") from e
        return _agent_to_dict(agent)


@mcp.tool()
async def delete_agent(agent_id: str) -> dict[str, Any]:
    """Remove um agente (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(agent_id)

    async with async_session_factory() as db:
        service = AgentService()
        try:
            await service.delete_agent(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Erro ao remover agente: {e.error}") from e
        return {"success": True, "message": "Agente removido com sucesso."}
