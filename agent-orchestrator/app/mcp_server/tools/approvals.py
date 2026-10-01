"""Ferramentas MCP de Aprovações (listar, detalhar, aprovar, rejeitar).

Registra as ferramentas de gerenciamento de aprovações (HITL) no servidor
MCP. Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
opera diretamente no ``ApprovalRequest`` (mesmo caminho usado pelo router
REST em ``app/api/approvals.py``).

Ao aprovar/rejeitar, atualiza o status, emite ``approval:resolved`` (via
``ws_publish``) e retoma a execução (via ``_trigger_resume``). Erros
(``AppError``) e de parsing de UUID são convertidos em ``ToolError`` com
mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.errors import AppError
from app.db.models import ApprovalRequest, PipelineRun
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError
from app.runtime.websocket import publish as ws_publish
from app.api.approvals import _trigger_resume


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Filtro de status: "resolved" agrupa approved + rejected + revised.
_STATUS_FILTER_MAP: dict[str, list[str]] = {
    "pending": ["pending"],
    "resolved": ["approved", "rejected", "revised"],
    "cancelled": ["cancelled"],
}


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _approval_to_dict(a: ApprovalRequest) -> dict[str, Any]:
    """Converte ApprovalRequest para camelCase (spec 4.5)."""
    return {
        "id": str(a.id),
        "pipelineId": str(a.pipeline_id),
        "runId": str(a.run_id) if a.run_id else None,
        "nodeId": a.node_id,
        "agentId": str(a.agent_id) if a.agent_id else None,
        "checkpointId": a.checkpoint_id,
        "message": a.message,
        "context": a.context,
        "artifacts": a.artifacts,
        "status": a.status.value if hasattr(a.status, "value") else a.status,
        "response": a.response,
        "respondedBy": a.responded_by,
        "respondedAt": a.responded_at.isoformat().replace("+00:00", "Z")
        if a.responded_at
        else None,
        "channel": a.channel.value if hasattr(a.channel, "value") else a.channel,
        "sentAt": a.sent_at.isoformat().replace("+00:00", "Z") if a.sent_at else None,
        "retryCount": a.retry_count,
        "maxRetries": a.max_retries,
        "attemptedChannels": a.attempted_channels,
        "fallbackChannel": (
            a.fallback_channel.value if a.fallback_channel else None
        ),
        "timeoutSeconds": a.timeout_seconds,
        "createdAt": a.created_at.isoformat().replace("+00:00", "Z")
        if a.created_at
        else None,
    }


async def _get_owned_approval(db, owner_id: uuid.UUID, approval_id: uuid.UUID) -> ApprovalRequest:
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.owner_id == owner_id,
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise AppError(404, "not_found", "approval_not_found")
    return approval


async def _respond(
    db, user, approval: ApprovalRequest, decision: str, response: str | None
) -> dict[str, Any]:
    """Lógica comum de aprovar/rejeitar (valida, atualiza, emite, retoma)."""
    # 409: já respondida.
    if approval.status != "pending":
        raise AppError(409, "conflict", "already_responded")

    # 409: run cancelado.
    if approval.run_id is not None:
        run_result = await db.execute(
            select(PipelineRun).where(PipelineRun.id == approval.run_id)
        )
        run = run_result.scalar_one_or_none()
        if run is not None and run.status == "cancelled":
            raise AppError(409, "conflict", "already_responded")

    approval.status = decision
    approval.response = response
    approval.responded_by = str(user.owner_id)
    approval.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(approval)

    await ws_publish(
        str(user.owner_id),
        "approval:resolved",
        {
            "approvalId": str(approval.id),
            "pipelineId": str(approval.pipeline_id),
            "runId": str(approval.run_id) if approval.run_id else None,
            "nodeId": approval.node_id,
            "decision": decision,
            "at": _now_iso(),
        },
    )

    resume_value: dict[str, Any] = {"decision": decision}
    if response is not None:
        resume_value["response"] = response
    await _trigger_resume(approval, resume_value, db)

    return {
        "approvalId": str(approval.id),
        "status": decision,
        "respondedAt": approval.responded_at.isoformat().replace("+00:00", "Z"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_approvals(
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    pipeline_id: str | None = None,
) -> dict[str, Any]:
    """Lista as aprovações do usuário autenticado, com filtros e paginação.

    ``status`` pode ser 'pending', 'resolved' (agrupa approved/rejected/
    revised) ou 'cancelled'. ``pipeline_id`` filtra por pipeline.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        query = select(ApprovalRequest).where(ApprovalRequest.owner_id == user.owner_id)

        if status:
            allowed = _STATUS_FILTER_MAP.get(status)
            if allowed is None:
                raise ToolError(f"Status inválido: {status}. Use pending, resolved ou cancelled.")
            query = query.where(ApprovalRequest.status.in_(allowed))

        if pipeline_id:
            try:
                pid = uuid.UUID(pipeline_id)
            except (ValueError, TypeError, AttributeError):
                raise ToolError("pipeline_id inválido.") from None
            query = query.where(ApprovalRequest.pipeline_id == pid)

        query = query.order_by(ApprovalRequest.created_at.desc())
        result = await db.execute(query)
        all_items = list(result.scalars().all())
        total = len(all_items)

        offset = (page - 1) * limit
        items = all_items[offset : offset + limit]

        return {
            "items": [_approval_to_dict(a) for a in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_approval(approval_id: str) -> dict[str, Any]:
    """Obtém uma aprovação por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(approval_id)

    async with async_session_factory() as db:
        try:
            approval = await _get_owned_approval(db, user.owner_id, parsed_id)
        except AppError as e:
            raise ToolError(f"Aprovação não encontrada: {e.error}") from e
        return _approval_to_dict(approval)


@mcp.tool()
async def approve(approval_id: str) -> dict[str, Any]:
    """Aprova uma aprovação pendente.

    Atualiza o status para 'approved', emite ``approval:resolved`` e retoma a
    execução da pipeline. 409 se já foi respondida ou o run foi cancelado.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(approval_id)

    async with async_session_factory() as db:
        try:
            approval = await _get_owned_approval(db, user.owner_id, parsed_id)
            return await _respond(db, user, approval, "approved", None)
        except AppError as e:
            raise ToolError(f"Erro ao aprovar: {e.error}") from e


@mcp.tool()
async def reject(approval_id: str, response: str | None = None) -> dict[str, Any]:
    """Rejeita uma aprovação pendente.

    ``response`` é opcional: o argumento/motivo do humano. Atualiza o status
    para 'rejected', emite ``approval:resolved`` e retoma a execução. 409 se
    já foi respondida ou o run foi cancelado.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(approval_id)

    async with async_session_factory() as db:
        try:
            approval = await _get_owned_approval(db, user.owner_id, parsed_id)
            return await _respond(db, user, approval, "rejected", response)
        except AppError as e:
            raise ToolError(f"Erro ao rejeitar: {e.error}") from e
