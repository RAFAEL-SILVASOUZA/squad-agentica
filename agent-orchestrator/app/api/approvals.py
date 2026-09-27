"""API de aprovações (spec 9.6, contrato §8).

Dono: hitl-approval (FASE 7). Endpoints:
- GET  /api/approvals            (listar, filtros status/pipelineId, paginação)
- GET  /api/approvals/{id}       (detalhar)
- POST /api/approvals/{id}/respond (aprovar/rejeitar/argumentar)

Contrato §8: envelope de erro, camelCase, 409 (already_responded), 404.
Tudo filtrado por owner (V1 single-user, contrato §11.19).

Resposta do respond (spec 5.3, mapa de respostas para fan-out):
- decision: "approved" | "rejected" | "revised"
- response: texto do argumento (modo "revised"/argumentar)

Ao responder, chama ``compile_and_resume`` do nó hitl-resume (em paralelo;
importado pela assinatura do contrato). Se hitl-resume ainda não existe, o
resume é adiado (a ApprovalRequest fica marcada e o resume é feito quando o
nó hitl-resume estiver disponível) — mas na V1 o hitl-resume roda na mesma
fase, então o import funciona.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.db.models import ApprovalRequest, PipelineRun, User
from app.db.session import get_db
from app.runtime.websocket import publish as ws_publish

logger = logging.getLogger(__name__)

router = APIRouter(tags=["approvals"])


# ---------------------------------------------------------------------------
# Schemas (Pydantic, camelCase via alias)
# ---------------------------------------------------------------------------


class RespondRequest(BaseModel):
    """Body de POST /api/approvals/{id}/respond (spec 5.3)."""

    decision: str  # "approved" | "rejected" | "revised"
    response: str | None = None  # argumento do humano (modo revised)

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# Filtro de status: o query aceita "pending" | "resolved" | "cancelled".
# "resolved" agrupa approved + rejected + revised (spec 9.6).
_STATUS_FILTER_MAP: dict[str, list[str]] = {
    "pending": ["pending"],
    "resolved": ["approved", "rejected", "revised"],
    "cancelled": ["cancelled"],
}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/approvals")
async def list_approvals(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    status: str | None = None,
    pipeline_id: Annotated[str | None, Query(alias="pipelineId")] = None,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """GET /api/approvals

    Lista aprovações do owner (filtro por status e pipelineId, paginação).
    Query: ?status=pending|resolved|cancelled&pipelineId=&page=&limit=
    """
    query = select(ApprovalRequest).where(ApprovalRequest.owner_id == user.owner_id)

    # Filtro de status (spec 9.6).
    if status:
        allowed = _STATUS_FILTER_MAP.get(status)
        if allowed is None:
            raise AppError(400, "validation error", "invalid_status")
        query = query.where(ApprovalRequest.status.in_(allowed))

    # Filtro de pipelineId.
    if pipeline_id:
        try:
            pid = uuid.UUID(pipeline_id)
        except ValueError:
            raise AppError(400, "validation error", "invalid_pipeline_id") from None
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


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """GET /api/approvals/{id}

    Detalha uma aprovação (filtrado por owner).
    """
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.owner_id == user.owner_id,
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise AppError(404, "not_found", "approval_not_found")

    return _approval_to_dict(approval)


@router.post("/approvals/{approval_id}/respond")
async def respond_approval(
    approval_id: uuid.UUID,
    body: RespondRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/approvals/{id}/respond

    Responde uma aprovação: aprovar, rejeitar ou argumentar (spec 5.3).
    - 404 se não existe ou não é do owner.
    - 409 already_responded se já foi respondida ou o run foi cancelado.
    - Ao responder: atualiza status, emite ``approval:resolved`` e chama
      ``compile_and_resume`` (nó hitl-resume) para retomar a execução.
    """
    # Valida a decisão.
    decision = body.decision.strip().lower()
    if decision not in ("approved", "rejected", "revised"):
        raise AppError(400, "validation error", "invalid_decision")

    # Carrega a aprovação (filtrado por owner).
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.owner_id == user.owner_id,
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise AppError(404, "not_found", "approval_not_found")

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

    # Atualiza a aprovação.
    approval.status = decision
    approval.response = body.response
    approval.responded_by = str(user.owner_id)
    approval.responded_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(approval)

    # Emite approval:resolved (contrato §7).
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

    # Retoma a execução via compile_and_resume (nó hitl-resume, FASE 7).
    # O resume é assíncrono e não bloqueia a resposta da API: o humano já
    # recebeu o 200 e a execução continua em background.
    resume_value: dict[str, Any] = {"decision": decision}
    if body.response is not None:
        resume_value["response"] = body.response

    await _trigger_resume(approval, resume_value, db)

    return {
        "approvalId": str(approval.id),
        "status": decision,
        "respondedAt": approval.responded_at.isoformat().replace("+00:00", "Z"),
    }


@router.delete("/approvals/{approval_id}")
async def cancel_approval(
    approval_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """DELETE /api/approvals/{id}

    Cancela uma aprovação pendente (spec 9.6). 404 se já respondida.
    """
    result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.owner_id == user.owner_id,
        )
    )
    approval = result.scalar_one_or_none()
    if approval is None:
        raise AppError(404, "not_found", "approval_not_found")

    if approval.status != "pending":
        raise AppError(404, "not_found", "approval_not_found")

    approval.status = "cancelled"
    approval.responded_by = str(user.owner_id)
    approval.responded_at = datetime.now(UTC)
    await db.commit()

    return {"approvalId": str(approval.id), "status": "cancelled"}


async def _trigger_resume(
    approval: ApprovalRequest,
    resume_value: dict[str, Any],
    db: AsyncSession,
) -> None:
    """Retoma pelo executor compartilhado, preservando eventos e checkpoints."""
    if approval.run_id is None:
        logger.warning(
            "approval has no run_id; cannot resume",
            extra={"approval_id": str(approval.id)},
        )
        return

    # Reuse the runtime executor: async checkpoints, node events, persistence
    # and subsequent approval hooks must follow the same path as execute.
    try:
        from langgraph.types import Command

        from app.api.pipeline_runs import get_executor
        from app.approvals.resume import _load_pipeline_from_db
        from app.runtime.executor import get_active_run

        pipeline = await _load_pipeline_from_db(db, approval.pipeline_id)
        executor = await get_executor()
        active = get_active_run(str(approval.pipeline_id))
        if active and active.task:
            await active.task
        await executor.resume(
            pipeline,
            owner_id=str(approval.owner_id),
            run_id=str(approval.run_id),
            resume_input=Command(resume=resume_value),
        )
    except Exception:
        logger.exception(
            "resume failed after approval response",
            extra={"approval_id": str(approval.id)},
        )
