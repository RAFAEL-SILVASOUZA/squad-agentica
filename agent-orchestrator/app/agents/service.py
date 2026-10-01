"""Agent service: CRUD operations with dual persistence (Postgres + Garage).

Dono: be-agents (FASE 4). Usado pelo router (app/api/agents.py) e pelo
chat de construção (Backend Agent Builder Chat).

Assinaturas públicas:
- create_agent(db, owner_id, data) -> Agent
- get_agent(db, owner_id, agent_id) -> Agent
- list_agents(db, owner_id, page, limit, type_filter) -> (list[Agent], total)
- update_agent(db, owner_id, agent_id, data) -> Agent
- delete_agent(db, owner_id, agent_id) -> None
- validate_contract(inputs, outputs, actions) -> ValidationResult
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import yaml
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.storage import AgentStorage, get_agent_storage
from app.agents.validator import (
    ValidationResult,
    errors_to_details,
    validate_agent_contract,
)
from app.core.errors import AppError
from app.db.models import Agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization: Agent model <-> YAML artifact
# ---------------------------------------------------------------------------


def agent_to_yaml(agent: Agent, mcp_servers: list[dict[str, Any]] | None = None) -> str:
    """Serializa o agente para o formato .yml do artefato."""
    data = {
        "id": str(agent.id),
        "ownerId": str(agent.owner_id),
        "name": agent.name,
        "type": agent.type,
        "description": agent.description,
        "prompt": agent.prompt,
        "strategy": agent.strategy,
        "skills": agent.skills,
        "tools": agent.tools,
        "mcpServers": agent.mcp_servers if mcp_servers is None else mcp_servers,
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
    }
    return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)


def yaml_to_agent_data(yaml_content: str) -> dict[str, Any]:
    """Deserializa o artefato .yml para dict."""
    return yaml.safe_load(yaml_content)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AgentService:
    """Service de agentes com persistência dupla (Postgres + Garage)."""

    def __init__(self, storage: AgentStorage | None = None) -> None:
        self._storage = storage or get_agent_storage()

    async def _artifact_yaml(self, db: AsyncSession, agent: Agent) -> str:
        from app.mcp.registry import resolve_mcp_refs

        servers, warnings = await resolve_mcp_refs(db, agent.owner_id, agent.mcp_servers)
        for warning in warnings:
            logger.warning("Agente %s: %s", agent.id, warning)
        return agent_to_yaml(agent, servers)

    async def create_agent(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        data: dict[str, Any],
    ) -> Agent:
        """Cria um agente: valida contrato, PUT no Garage, INSERT no Postgres.

        Estratégia: Garage primeiro. Se Garage falhar, não há INSERT.
        Se INSERT falhar após PUT, DELETE compensatório no Garage.
        """
        # Validate contract.
        inputs = data.get("inputs", [])
        outputs = data.get("outputs", [])
        actions = data.get("actions", [])
        result = validate_agent_contract(inputs, outputs, actions)
        if not result.valid:
            raise AppError(400, "validation error", "invalid_graph", errors_to_details(result))

        # Check name uniqueness per owner.
        existing = await db.execute(
            select(Agent).where(Agent.owner_id == owner_id, Agent.name == data["name"])
        )
        if existing.scalar_one_or_none() is not None:
            raise AppError(409, "conflict", "agent_name_exists")

        # Build the agent.
        agent = Agent(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=data["name"],
            type=data.get("type", "custom"),
            description=data.get("description", ""),
            prompt=data.get("prompt", ""),
            strategy=data.get("strategy", ""),
            skills=data.get("skills", []),
            tools=data.get("tools", []),
            mcp_servers=data.get("mcpServers", []),
            knowledge=data.get("knowledge", []),
            integrations=data.get("integrations", []),
            inputs=inputs,
            outputs=outputs,
            actions=actions,
            model=data.get("model", "gpt-4o"),
            llm=data.get("llm"),
            max_iterations=data.get("maxIterations", 10),
            timeout=data.get("timeout", 300),
            shell_access=data.get("shellAccess", False),
        )

        # PUT in Garage first.
        agent_yaml = await self._artifact_yaml(db, agent)
        try:
            await self._storage.save_agent(str(agent.id), agent_yaml)
        except Exception as e:
            logger.error("Garage PUT failed for agent %s: %s", agent.id, e)
            raise AppError(500, "internal error", "storage_error") from e

        # INSERT in Postgres.
        try:
            db.add(agent)
            await db.commit()
            await db.refresh(agent)
        except Exception:
            # Compensating DELETE in Garage.
            try:
                await self._storage.delete_agent(str(agent.id))
            except Exception:
                logger.warning("Compensating DELETE failed for agent %s", agent.id)
            raise

        return agent

    async def get_agent(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> Agent:
        """Busca um agente por id, filtrado por owner."""
        result = await db.execute(
            select(Agent).where(Agent.id == agent_id, Agent.owner_id == owner_id)
        )
        agent = result.scalar_one_or_none()
        if agent is None:
            raise AppError(404, "not_found", "agent_not_found")
        return agent

    async def list_agents(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        page: int = 1,
        limit: int = 20,
        type_filter: str | None = None,
    ) -> tuple[list[Agent], int]:
        """Lista agentes do owner com paginação e filtro opcional por type."""
        query = select(Agent).where(Agent.owner_id == owner_id)
        count_query = select(func.count()).select_from(Agent).where(Agent.owner_id == owner_id)

        if type_filter:
            query = query.where(Agent.type == type_filter)
            count_query = count_query.where(Agent.type == type_filter)

        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        query = query.order_by(Agent.created_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await db.execute(query)
        agents = list(result.scalars().all())

        return agents, total

    async def update_agent(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        agent_id: uuid.UUID,
        data: dict[str, Any],
    ) -> Agent:
        """Atualiza um agente: valida, PUT no Garage, UPDATE no Postgres."""
        agent = await self.get_agent(db, owner_id, agent_id)

        # Validate contract if inputs/outputs/actions are being updated.
        inputs = data.get("inputs", agent.inputs)
        outputs = data.get("outputs", agent.outputs)
        actions = data.get("actions", agent.actions)
        result = validate_agent_contract(inputs, outputs, actions)
        if not result.valid:
            raise AppError(400, "validation error", "invalid_graph", errors_to_details(result))

        # Check name uniqueness if name is changing.
        new_name = data.get("name", agent.name)
        if new_name != agent.name:
            existing = await db.execute(
                select(Agent).where(
                    Agent.owner_id == owner_id,
                    Agent.name == new_name,
                    Agent.id != agent_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise AppError(409, "conflict", "agent_name_exists")

        # Apply updates.
        if "name" in data:
            agent.name = data["name"]
        if "type" in data:
            agent.type = data["type"]
        if "description" in data:
            agent.description = data["description"]
        if "prompt" in data:
            agent.prompt = data["prompt"]
        if "strategy" in data:
            agent.strategy = data["strategy"]
        if "skills" in data:
            agent.skills = data["skills"]
        if "tools" in data:
            agent.tools = data["tools"]
        if "mcpServers" in data:
            agent.mcp_servers = data["mcpServers"]
        if "knowledge" in data:
            agent.knowledge = data["knowledge"]
        if "integrations" in data:
            agent.integrations = data["integrations"]
        if "inputs" in data:
            agent.inputs = data["inputs"]
        if "outputs" in data:
            agent.outputs = data["outputs"]
        if "actions" in data:
            agent.actions = data["actions"]
        if "model" in data:
            agent.model = data["model"]
        if "llm" in data:
            agent.llm = data["llm"]
        if "maxIterations" in data:
            agent.max_iterations = data["maxIterations"]
        if "timeout" in data:
            agent.timeout = data["timeout"]
        if "shellAccess" in data:
            agent.shell_access = data["shellAccess"]

        # PUT in Garage first.
        agent_yaml = await self._artifact_yaml(db, agent)
        try:
            await self._storage.save_agent(str(agent.id), agent_yaml)
        except Exception as e:
            logger.error("Garage PUT failed for agent update %s: %s", agent.id, e)
            raise AppError(500, "internal error", "storage_error") from e

        # UPDATE in Postgres.
        try:
            await db.commit()
            await db.refresh(agent)
        except Exception:
            # The old artifact in Garage is still valid (same id).
            # The Postgres state is unchanged (rollback).
            raise

        return agent

    async def delete_agent(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> None:
        """Remove um agente: DELETE no Garage, DELETE no Postgres."""
        agent = await self.get_agent(db, owner_id, agent_id)

        # DELETE in Garage first.
        try:
            await self._storage.delete_agent(str(agent.id))
        except Exception as e:
            logger.error("Garage DELETE failed for agent %s: %s", agent.id, e)
            raise AppError(500, "internal error", "storage_error") from e

        # DELETE in Postgres.
        await db.delete(agent)
        await db.commit()


# Module-level convenience function for the router.
def validate_contract(
    inputs: list[dict],
    outputs: list[dict],
    actions: list[str],
) -> ValidationResult:
    """Valida o contrato de um agente (exposto para o chat de construção)."""
    return validate_agent_contract(inputs, outputs, actions)
