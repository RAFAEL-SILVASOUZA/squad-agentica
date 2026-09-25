"""Agent construction chat API: SSE streaming for agent build and edit.

Dono: be-agent-chat (FASE 4). Spec 9.2 + 10 + 14.1.

Rotas (prefixo /api):
- POST /api/agents/chat — chat de construção de novo agente (sessão efêmera)
- POST /api/agents/{id}/chat — chat de edição de agente existente

SSE events:
- { type: "text", data: string }
- { type: "config_update", data: Partial<Agent> }
- { type: "done", data: { draftId } }

Rate limit: 30 requests/min por usuário (spec 14.1).
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat.conversation import draft_store
from app.agents.chat.preview import build_preview
from app.agents.chat.proposal import (
    build_system_prompt,
    draft_to_agent_data,
    merge_config,
    parse_llm_response,
    validate_config,
)
from app.agents.service import AgentService
from app.auth.dependencies import get_current_user
from app.auth.rate_limiter import RateLimiter
from app.core.errors import AppError
from app.core.llm import LLMClient, get_llm_client
from app.db.models import User
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents-chat"])

# Rate limiter: 30 requests/min per user (spec 14.1).
chat_rate_limiter = RateLimiter(max_requests=30, window_seconds=60)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Body para POST /api/agents/chat e POST /api/agents/{id}/chat."""

    message: str = Field(..., min_length=1, max_length=10000)
    draftId: str | None = Field(default=None, description="Draft ID para continuar a sessão")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sse_event(event_type: str, data: Any) -> str:
    """Formats an SSE event line."""
    payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _check_rate_limit(user_id: str) -> None:
    """Checks the chat rate limit. Raises AppError(429) if exceeded."""
    allowed, retry_after = chat_rate_limiter.is_allowed(user_id)
    if not allowed:
        raise AppError(429, "rate_limited", "rate_limited", {"retryAfter": retry_after})


def _agent_to_config_dict(agent) -> dict[str, Any]:
    """Converts an Agent model to a config dict (for edit mode system prompt)."""
    return {
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
        "maxIterations": agent.max_iterations,
        "timeout": agent.timeout,
        "shellAccess": agent.shell_access,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/chat")
async def agent_chat_create(
    body: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Chat de construção de novo agente (sessão efêmera, sem id).

    SSE stream com eventos: text, config_update, done.
    """
    _check_rate_limit(str(user.id))

    # Resolve or creates the draft.
    if body.draftId:
        draft = draft_store.get(body.draftId, str(user.id))
        if draft is None:
            raise AppError(404, "not_found", "draft_not_found")
    else:
        draft = draft_store.create(str(user.id))

    # Build messages for the LLM.
    system_prompt = build_system_prompt("create")
    draft.add_message("user", body.message)
    llm_messages = [{"role": "system", "content": system_prompt}] + draft.to_llm_messages()

    # Call the LLM.
    llm: LLMClient = get_llm_client()
    raw_response = await llm.chat(llm_messages)

    # Parse the response.
    text, config_update = parse_llm_response(raw_response)

    # Merge config into the draft.
    if config_update:
        draft.config = merge_config(draft.config, config_update)

    # Validate the contract if inputs/outputs/actions are present.
    validation_errors = validate_config(draft.config)

    # Store the assistant message.
    draft.add_message("assistant", text)

    # Build the SSE stream.
    async def event_stream():
        # Text event.
        yield _sse_event("text", text)

        # Config update event (if there's a config change).
        if config_update:
            preview = build_preview(draft)
            yield _sse_event("config_update", preview)

        # Validation errors (if any).
        if validation_errors:
            yield _sse_event("validation_error", validation_errors)

        # Done event.
        yield _sse_event("done", {"draftId": draft.draft_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{agent_id}/chat")
async def agent_chat_edit(
    agent_id: uuid.UUID,
    body: ChatRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Chat de edição de agente existente. SSE streaming.

    O agente é carregado do banco (com isolamento por owner).
    O draft acumula as mudanças; ao salvar, o AgentService.update_agent é chamado.
    """
    _check_rate_limit(str(user.id))

    # Load the agent (owner isolation enforced by service).
    service = AgentService()
    agent = await service.get_agent(db, user.id, agent_id)

    # Resolve or create the draft.
    if body.draftId:
        draft = draft_store.get(body.draftId, str(user.id))
        if draft is None:
            raise AppError(404, "not_found", "draft_not_found")
    else:
        # Create a new draft seeded with the current agent config.
        draft = draft_store.create(str(user.id))
        draft.config = _agent_to_config_dict(agent)

    # Build messages for the LLM.
    current_config = _agent_to_config_dict(agent)
    system_prompt = build_system_prompt("edit", current_config)
    draft.add_message("user", body.message)
    llm_messages = [{"role": "system", "content": system_prompt}] + draft.to_llm_messages()

    # Call the LLM.
    llm: LLMClient = get_llm_client()
    raw_response = await llm.chat(llm_messages)

    # Parse the response.
    text, config_update = parse_llm_response(raw_response)

    # For edit mode, the LLM returns the FULL config.
    if config_update:
        draft.config = config_update

    # Validate the contract.
    validation_errors = validate_config(draft.config)

    # Store the assistant message.
    draft.add_message("assistant", text)

    # Build the SSE stream.
    async def event_stream():
        # Text event.
        yield _sse_event("text", text)

        # Config update event.
        if config_update:
            preview = build_preview(draft)
            yield _sse_event("config_update", preview)

        # Validation errors.
        if validation_errors:
            yield _sse_event("validation_error", validation_errors)

        # Done event.
        yield _sse_event("done", {"draftId": draft.draft_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/confirm")
async def agent_chat_confirm(
    body: dict[str, Any],
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
):
    """Confirma o draft e salva o agente via AgentService.

    Body: { draftId: string }
    Response: 201 AgentResponse | 400 invalid_graph | 404 draft_not_found | 409 agent_name_exists
    """
    draft_id = body.get("draftId")
    if not draft_id:
        raise AppError(400, "validation error", "missing_draft_id")

    draft = draft_store.get(draft_id, str(user.id))
    if draft is None:
        raise AppError(404, "not_found", "draft_not_found")

    # Convert draft to agent data and save via service.
    data = draft_to_agent_data(draft)
    service = AgentService()
    agent = await service.create_agent(db, user.id, data)

    # Delete the draft after successful save.
    draft_store.delete(draft.draft_id)

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
        "maxIterations": agent.max_iterations,
        "timeout": agent.timeout,
        "shellAccess": agent.shell_access,
        "createdAt": agent.created_at.isoformat() if agent.created_at else "",
        "updatedAt": agent.updated_at.isoformat() if agent.updated_at else "",
    }
