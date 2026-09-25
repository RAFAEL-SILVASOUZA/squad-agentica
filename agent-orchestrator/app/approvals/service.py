"""ApprovalRequest: upsert idempotente + hook do executor (D7 §7.2).

Dono: hitl-approval (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md ADR-009 (criação da ApprovalRequest pelo executor, upsert
  pós-interrupção, chave (runId, nodeId, interruptId)) e §7 (WebSocket).
- D7-human-in-the-loop.md §7.2.
- Spec 4.5 (ApprovalRequest), 5.3 (idempotência).

ADR-009 (decisão vigente): o nó de aprovação NÃO tem efeitos colaterais antes do
``interrupt()``. Quem cria a ApprovalRequest é o EXECUTOR, ao detectar a pausa no
stream: ele faz o **upsert** com a chave ``(runId, nodeId, interruptId)`` e dispara
a notificação. Reexecuções do nó (o LangGraph re-executa o nó inteiro ao retomar)
não duplicam, porque o upsert é idempotente por chave.

Chave de idempotência:
- ``runId``: UUID do PipelineRun.
- ``nodeId``: ID do nó de aprovação (``approval_node_{edgeId}``).
- ``interruptId``: task id real do LangGraph (``PregelTask.id`` ==
  ``CONFIG_KEY_TASK_ID``), estável entre execuções/resumes da mesma pausa.

O executor (rt-executor) expõe ``register_approval_hook(callback)``; este módulo
fornece ``build_approval_hook`` que devolve o callback com a assinatura do
contrato: ``(run_id, pipeline_id, node_id, interrupt_payload, thread_id)``.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApprovalRequest
from app.runtime.websocket import publish as ws_publish

logger = logging.getLogger(__name__)

# Canal padrão de notificação (V1: in-app via WebSocket; email opcional).
# NotificationChannel é um Enum do SQLAlchemy (string values), não um enum
# Python; usamos a string "in-app" diretamente.
DEFAULT_CHANNEL = "in-app"


def _now_iso() -> str:
    """Timestamp ISO 8601 UTC com Z explícito (contrato §8)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _channel_from_payload(payload: Any) -> str:
    """Extrai o canal de notificação do payload do interrupt.

    O payload é montado pelo nó de aprovação (node_function.py) e carrega
    ``approvalChannel`` (do PipelineEdge). Default: in-app.
    """
    if isinstance(payload, dict):
        raw = payload.get("approvalChannel")
        if raw:
            return str(raw)
    return DEFAULT_CHANNEL


def _message_from_payload(payload: Any) -> str:
    """Extrai a mensagem do payload do interrupt (default vazio)."""
    if isinstance(payload, dict):
        return str(payload.get("message", "") or "")
    return ""


def _context_from_payload(payload: Any) -> dict[str, Any]:
    """Extrai o contexto (o que o agente produziu) do payload do interrupt."""
    if isinstance(payload, dict):
        ctx = payload.get("context")
        if isinstance(ctx, dict):
            return ctx
    return {}


def _artifacts_from_payload(payload: Any) -> list[str] | None:
    """Extrai os artefatos (links) do payload do interrupt (opcional)."""
    if isinstance(payload, dict):
        arts = payload.get("artifacts")
        if isinstance(arts, list):
            return [str(a) for a in arts]
    return None


async def upsert_approval_request(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    pipeline_id: uuid.UUID,
    run_id: uuid.UUID | None,
    node_id: str,
    interrupt_id: str,
    payload: Any,
) -> tuple[ApprovalRequest, bool]:
    """Upsert idempotente da ApprovalRequest (ADR-009).

    Chave de idempotência: ``(runId, nodeId, interruptId)``. Como o modelo
    ``ApprovalRequest`` não tem coluna ``run_id`` única composta, a busca é por
    ``(pipeline_id, node_id, checkpoint_id)`` (``checkpoint_id`` guarda o
    ``interruptId``) e, quando disponível, ``run_id``. Se já existe com status
    ``pending``, NÃO recria (idempotente).

    Args:
        session: Sessão SQLAlchemy async.
        owner_id: Owner da pipeline (filtro de isolamento).
        pipeline_id: UUID da pipeline.
        run_id: UUID do run (pode ser None).
        node_id: ID do nó de aprovação.
        interrupt_id: task id real do LangGraph (chave de idempotência).
        payload: payload do interrupt (montado pelo nó de aprovação).

    Returns:
        Tupla ``(approval_request, created)``: a linha (existente ou nova) e um
        bool indicando se foi criada agora (``created=True``) ou já existia
        (``created=False``). O caller usa ``created`` para decidir se notifica.
    """
    # Busca por chave de idempotência.
    query = select(ApprovalRequest).where(
        ApprovalRequest.pipeline_id == pipeline_id,
        ApprovalRequest.node_id == node_id,
        ApprovalRequest.checkpoint_id == interrupt_id,
    )
    if run_id is not None:
        query = query.where(ApprovalRequest.run_id == run_id)

    result = await session.execute(query)
    existing = result.scalars().first()

    if existing is not None:
        # Já existe: idempotente, não recria.
        return existing, False

    # Cria nova.
    approval = ApprovalRequest(
        id=uuid.uuid4(),
        owner_id=owner_id,
        pipeline_id=pipeline_id,
        run_id=run_id,
        node_id=node_id,
        # agent_id: o nó de aprovação não carrega o agentId diretamente; o
        # contexto tem o output do source. Deixamos None (coluna nullable).
        checkpoint_id=interrupt_id,
        message=_message_from_payload(payload),
        context=_context_from_payload(payload),
        artifacts=_artifacts_from_payload(payload),
        status="pending",
        channel=_channel_from_payload(payload),
        sent_at=datetime.now(UTC),
        retry_count=0,
        max_retries=3,
        attempted_channels=[],
        fallback_channel=None,
        timeout_seconds=3600,
    )
    session.add(approval)
    await session.commit()
    await session.refresh(approval)
    return approval, True


async def _notify_new_approval(
    owner_id: str,
    approval: ApprovalRequest,
) -> None:
    """Dispara a notificação in-app (WebSocket ``approval:new``).

    Chamado APÓS o upsert (ADR-009). O nó hitl-notification (em paralelo) pode
    estender com email/teams/slack; aqui garantimos o canal in-app da V1 via a
    interface ``publish`` do contrato §7.
    """
    await ws_publish(
        owner_id,
        "approval:new",
        {
            "approvalId": str(approval.id),
            "pipelineId": str(approval.pipeline_id),
            "runId": str(approval.run_id) if approval.run_id else None,
            "nodeId": approval.node_id,
            "message": approval.message,
            "at": _now_iso(),
        },
    )


def build_approval_hook(session_factory: Any) -> Any:
    """Constrói o callback do hook de aprovação do executor (ADR-009).

    O executor (rt-executor) chama ``register_approval_hook(callback)``. O
    callback tem a assinatura do contrato:
        ``async def hook(run_id, pipeline_id, node_id, interrupt_payload, thread_id)``

    Este factory recebe uma ``session_factory`` (async_sessionmaker) para abrir
    uma sessão por chamada (o hook roda fora do request, no background task do
    executor).

    Fluxo do hook (ADR-009):
    1. Extrai o ``interrupt_id`` (task id real) do payload. O executor passa o
       payload do interrupt; o task id é embutido no payload pelo nó de
       aprovação (campo ``interruptId``) OU derivado. Como o nó não pode ter
       efeito colateral antes do interrupt, o executor é quem conhece o task id
       (``PregelTask.id``). Para robustez, o hook aceita o task id via um campo
       opcional ``__interruptId__`` no payload, injetado pelo executor.
    2. Upsert da ApprovalRequest (idempotente por chave).
    3. Se criada agora (``created=True``), dispara a notificação in-app.

    Args:
        session_factory: async_sessionmaker (abre sessões para o hook).

    Returns:
        O callback async com a assinatura do hook do executor.
    """

    async def approval_hook(
        run_id: str,
        pipeline_id: str,
        node_id: str,
        interrupt_payload: Any,
        thread_id: str,
    ) -> None:
        # O executor injeta o task id real (PregelTask.id) no payload sob a key
        # ``__interruptId__`` (ver executor._handle_interrupt_from_tasks). Se não
        # estiver presente, derivamos uma chave estável a partir dos campos
        # disponíveis (fallback; mantém a idempotência por (run, node)).
        interrupt_id = ""
        if isinstance(interrupt_payload, dict):
            interrupt_id = str(interrupt_payload.get("__interruptId__", "") or "")
        if not interrupt_id:
            interrupt_id = f"{run_id}:{node_id}"

        # Converte para UUID (o hook recebe strings).
        try:
            pipeline_uuid = uuid.UUID(pipeline_id)
        except (ValueError, TypeError):
            logger.warning(
                "approval hook: invalid pipeline_id",
                extra={"pipeline_id": pipeline_id},
            )
            return
        run_uuid: uuid.UUID | None
        try:
            run_uuid = uuid.UUID(run_id)
        except (ValueError, TypeError):
            run_uuid = None

        # owner_id: o hook não recebe o owner diretamente. A ApprovalRequest
        # precisa do owner_id (FK). Recupera da pipeline via sessão.
        async with session_factory() as session:
            from app.db.models import Pipeline

            result = await session.execute(
                select(Pipeline).where(Pipeline.id == pipeline_uuid)
            )
            pipeline = result.scalar_one_or_none()
            if pipeline is None:
                logger.warning(
                    "approval hook: pipeline not found",
                    extra={"pipeline_id": pipeline_id},
                )
                return
            owner_id = pipeline.owner_id

            approval, created = await upsert_approval_request(
                session,
                owner_id=owner_id,
                pipeline_id=pipeline_uuid,
                run_id=run_uuid,
                node_id=node_id,
                interrupt_id=interrupt_id,
                payload=interrupt_payload,
            )

            if created:
                logger.info(
                    "approval request created",
                    extra={
                        "approval_id": str(approval.id),
                        "pipeline_id": pipeline_id,
                        "node_id": node_id,
                    },
                )
                # Notificação APÓS o upsert (ADR-009). Só se criada agora.
                await _notify_new_approval(str(owner_id), approval)
            else:
                logger.info(
                    "approval request already exists (idempotent, no re-notify)",
                    extra={
                        "approval_id": str(approval.id),
                        "pipeline_id": pipeline_id,
                        "node_id": node_id,
                    },
                )

    return approval_hook
