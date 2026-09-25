"""Retomada de pipeline após decisão humana (D7 §7.4, ADR-004, ADR-006).

Dono: hitl-resume (FASE 7). Fontes de verdade:
- CONTRATO-TECNICO.md ADR-004 (resume sempre recompila o grafo), ADR-006
  (Command(goto=<id real>)), ADR-009 (idempotência por chave).
- D7-human-in-the-loop.md §7.4 (retomada).
- Spec 5.3 (fan-out com múltiplos nós de aprovação, três respostas humanas).
- spike/main.py (padrão aprovado de compile_and_resume).

Responsabilidades:
- compile_and_resume: carrega a pipeline do banco, recompila o StateGraph
  (ADR-004), retoma com Command(resume=...) usando o thread_id do run e
  continua o streaming pelo executor existente.
- Fan-out com múltiplas aprovações pendentes no mesmo run: resume com o mapa
  {interrupt_id: resposta} (spec 5.3).
- As três respostas humanas: aprovar (segue para o target), rejeitar (reject
  target da aresta: loop back ou END) e argumentar (o texto do humano volta
  como input para o nó de origem).
- Idempotência: responder duas vezes à mesma aprovação não retoma duas vezes
  (409 ou no-op documentado); resposta a aprovação de run cancelado retorna
  erro claro.

Integração com o endpoint POST /approvals/:id/respond (nó HITL Approval):
o endpoint chama compile_and_resume com a assinatura:
    await compile_and_resume(
        pipeline_id=str,
        run_id=str,
        checkpointer=checkpointer,
        thread_id=str,
        resume_value=dict,
    )
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.compiler.graph_builder import Pipeline, WorkerClient, compile_pipeline, pipeline_from_dict
from app.compiler.state import initial_state
from app.db.models import (
    ApprovalRequest,
    Pipeline as PipelineModel,
    PipelineEdge as PipelineEdgeModel,
    PipelineNode as PipelineNodeModel,
    PipelineRun,
)
from app.runtime.checkpoint import make_thread_id
from app.runtime.websocket import publish as ws_publish

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions (mapeadas para HTTP no endpoint)
# ---------------------------------------------------------------------------


class AlreadyRespondedError(Exception):
    """409: a aprovação já foi respondida (idempotência)."""

    def __init__(self, approval_id: str) -> None:
        super().__init__(f"Approval already responded: {approval_id}")
        self.approval_id = approval_id


class RunCancelledError(Exception):
    """409: o run foi cancelado; não é possível retomar."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run cancelled, cannot resume: {run_id}")
        self.run_id = run_id


class NoPendingInterruptError(Exception):
    """409: não há interrupt pendente no thread (já foi retomado ou não existe)."""

    def __init__(self, thread_id: str) -> None:
        super().__init__(f"No pending interrupt for thread: {thread_id}")
        self.thread_id = thread_id


class PipelineNotFoundError(Exception):
    """404: pipeline não encontrada."""

    def __init__(self, pipeline_id: str) -> None:
        super().__init__(f"Pipeline not found: {pipeline_id}")
        self.pipeline_id = pipeline_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _pipeline_to_dict(
    db_pipeline: PipelineModel,
    nodes: list[PipelineNodeModel],
    edges: list[PipelineEdgeModel],
) -> dict[str, Any]:
    """Converte os modelos DB em dict no formato da spec 4.2 (para pipeline_from_dict)."""
    return {
        "id": str(db_pipeline.id),
        "name": db_pipeline.name,
        "entryNodeId": str(db_pipeline.entry_node_id),
        "description": db_pipeline.description,
        "status": db_pipeline.status.value if hasattr(db_pipeline.status, "value") else db_pipeline.status,
        "nodes": [
            {
                "id": str(n.id),
                "agentId": str(n.agent_id),
                "agentSnapshot": n.agent_snapshot,
                "position": n.position,
                "label": n.label,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": str(e.id),
                "type": e.type.value if hasattr(e.type, "value") else e.type,
                "source": str(e.source),
                "target": str(e.target),
                "condition": e.condition,
                "label": e.label,
                "requiresApproval": e.requires_approval,
                "approvalChannel": (
                    e.approval_channel.value
                    if e.approval_channel and hasattr(e.approval_channel, "value")
                    else e.approval_channel
                ),
                "approvalMessage": e.approval_message,
                "dataMapping": e.data_mapping,
                "rejectTarget": e.reject_target,
            }
            for e in edges
        ],
    }


async def _load_pipeline_from_db(
    session: AsyncSession, pipeline_id: uuid.UUID
) -> Pipeline:
    """Carrega a pipeline (nodes + edges) do banco e converte para Pipeline dataclass."""
    result = await session.execute(
        select(PipelineModel).where(PipelineModel.id == pipeline_id)
    )
    db_pipeline = result.scalar_one_or_none()
    if db_pipeline is None:
        raise PipelineNotFoundError(str(pipeline_id))

    nodes_result = await session.execute(
        select(PipelineNodeModel).where(PipelineNodeModel.pipeline_id == pipeline_id)
    )
    nodes = list(nodes_result.scalars().all())

    edges_result = await session.execute(
        select(PipelineEdgeModel).where(PipelineEdgeModel.pipeline_id == pipeline_id)
    )
    edges = list(edges_result.scalars().all())

    pipeline_dict = _pipeline_to_dict(db_pipeline, nodes, edges)
    return pipeline_from_dict(pipeline_dict)


# ---------------------------------------------------------------------------
# compile_and_resume: a função principal
# ---------------------------------------------------------------------------


async def compile_and_resume(
    pipeline_id: str,
    run_id: str,
    checkpointer: BaseCheckpointSaver,
    thread_id: str,
    resume_value: dict[str, Any] | str,
    *,
    worker_client: WorkerClient | None = None,
    owner_id: str | None = None,
    session: AsyncSession | None = None,
) -> dict[str, Any]:
    """Recompila o grafo da pipeline e retoma com Command(resume=...) (ADR-004).

    Fluxo:
    1. Carrega a pipeline do banco (nodes + edges + agentSnapshots).
    2. Recompila o StateGraph via compile_pipeline (ADR-004: sempre recompila).
    3. Obtém o snapshot atual do thread (para o checkpoint_id da pausa).
    4. Chama graph.ainvoke(Command(resume=resume_value), config).
    5. Detecta se a execução pausou novamente (novo interrupt) ou completou.
    6. Emite eventos WebSocket (pipeline:status).

    Para fan-out com múltiplos interrupts no mesmo superstep (spec 5.3),
    resume_value pode ser um mapa {interrupt_id: response}. O LangGraph
    distribui cada resposta ao interrupt correspondente.

    Args:
        pipeline_id: UUID da pipeline (string).
        run_id: UUID do run (string).
        checkpointer: O checkpointer (AsyncPostgresSaver ou MemorySaver em testes).
        thread_id: O thread_id do run (f"{pipeline_id}:{run_id}").
        resume_value: A resposta humana. Pode ser:
            - str: "approved" | "rejected" | "revised" (single interrupt).
            - dict: {"decision": "...", "response": "..."} (single interrupt).
            - dict: {interrupt_id: response} (fan-out, múltiplos interrupts).
        worker_client: Implementação do WorkerClient (injetado). Se None,
            usa HttpWorkerClient (produção).
        owner_id: Owner da pipeline (para eventos WebSocket). Opcional.
        session: Sessão SQLAlchemy async (para carregar a pipeline do DB).
            Se None, a função não carrega do DB (usado em testes com pipeline
            pré-construída).

    Returns:
        Dict com o resultado:
            - "status": "completed" | "paused" | "interrupted" | "failed"
            - "state": o estado final do grafo (se disponível)
            - "interrupted": bool (se pausou em novo interrupt)

    Raises:
        PipelineNotFoundError: 404 se a pipeline não existe.
        AlreadyRespondedError: 409 se não há interrupt pendente (já respondida).
        RunCancelledError: 409 se o run foi cancelado.
    """
    # Se worker_client não foi injetado, cria o HTTP client (produção).
    if worker_client is None:
        from app.runtime.worker_client import HttpWorkerClient  # noqa: PLC0415

        worker_client = HttpWorkerClient()

    # Carrega a pipeline do banco.
    if session is not None:
        pipeline_uuid = uuid.UUID(pipeline_id)
        pipeline = await _load_pipeline_from_db(session, pipeline_uuid)
    else:
        # Sem sessão: não é possível carregar do DB. Levanta erro claro.
        raise PipelineNotFoundError(pipeline_id)

    # Verifica se o run foi cancelado.
    run_uuid = uuid.UUID(run_id)
    run_result = await session.execute(
        select(PipelineRun).where(PipelineRun.id == run_uuid)
    )
    run = run_result.scalar_one_or_none()
    if run is not None and run.status == "cancelled":
        raise RunCancelledError(run_id)

    # Recompila o grafo (ADR-004: sempre recompila do JSON).
    graph = compile_pipeline(
        pipeline,
        worker_client=worker_client,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": thread_id}}

    # Verifica se há interrupt pendente (idempotência).
    snap = graph.get_state(config)
    if snap is None:
        raise NoPendingInterruptError(thread_id)

    # Verifica se há tasks com interrupts (pausa ativa).
    has_pending_interrupt = False
    for task in snap.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            has_pending_interrupt = True
            break

    if not has_pending_interrupt:
        # Sem interrupt pendente: já foi respondida ou o run não está pausado.
        # Idempotência: no-op documentado (não retoma duas vezes).
        logger.info(
            "compile_and_resume: no pending interrupt (idempotent no-op)",
            extra={"thread_id": thread_id, "run_id": run_id},
        )
        return {
            "status": "no_pending_interrupt",
            "state": dict(snap.values) if snap.values else {},
            "interrupted": False,
        }

    # Para retomar do ponto de interrupção, usa a config do snapshot atual
    # (carrega o checkpoint_id da pausa).
    resume_config = snap.config if snap.config else config

    # Executa o resume.
    try:
        await graph.ainvoke(Command(resume=resume_value), config=resume_config)
    except Exception as exc:
        logger.exception(
            "compile_and_resume: ainvoke failed",
            extra={"thread_id": thread_id, "run_id": run_id},
        )
        # Emite status failed.
        if owner_id:
            await ws_publish(
                owner_id,
                "pipeline:status",
                {
                    "pipelineId": pipeline_id,
                    "runId": run_id,
                    "nodeId": "",
                    "status": "failed",
                    "at": _now_iso(),
                },
            )
        raise

    # Verifica o estado pós-resume.
    final_snap = graph.get_state(config)
    final_state = dict(final_snap.values) if final_snap is not None else {}

    # Detecta se pausou novamente (novo interrupt em outro nó de aprovação).
    interrupted = False
    if final_snap is not None:
        for task in final_snap.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupted = True
                break

    # Determina o status final.
    if interrupted:
        status = "interrupted"
    elif final_state.get("pipeline_status") == "failed":
        status = "failed"
    elif final_snap is not None and final_snap.next:
        # Tem próximos nós mas não está em interrupt: pode ser paused.
        status = "paused"
    else:
        status = "completed"

    # Emite evento WebSocket.
    if owner_id:
        await ws_publish(
            owner_id,
            "pipeline:status",
            {
                "pipelineId": pipeline_id,
                "runId": run_id,
                "nodeId": "",
                "status": status,
                "at": _now_iso(),
            },
        )

    logger.info(
        "compile_and_resume completed",
        extra={
            "thread_id": thread_id,
            "run_id": run_id,
            "status": status,
            "interrupted": interrupted,
        },
    )

    return {
        "status": status,
        "state": final_state,
        "interrupted": interrupted,
    }


# ---------------------------------------------------------------------------
# compile_and_resume_with_pipeline: variante que recebe a Pipeline já carregada
# (para testes e para o executor que já tem a pipeline em memória).
# ---------------------------------------------------------------------------


async def compile_and_resume_with_pipeline(
    pipeline: Pipeline,
    checkpointer: BaseCheckpointSaver,
    thread_id: str,
    resume_value: dict[str, Any] | str,
    *,
    worker_client: WorkerClient,
    owner_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Variante de compile_and_resume que recebe a Pipeline já carregada.

    Útil para testes (sem DB) e para o executor que já tem a pipeline em memória.
    A lógica de resume é idêntica a compile_and_resume.

    Args:
        pipeline: Pipeline já carregada (dataclass).
        checkpointer: O checkpointer.
        thread_id: O thread_id do run.
        resume_value: A resposta humana (str ou dict).
        worker_client: Implementação do WorkerClient.
        owner_id: Owner (para WebSocket). Opcional.
        run_id: Run ID (para logs). Opcional.

    Returns:
        Dict com status, state, interrupted (mesmo formato de compile_and_resume).
    """
    # Recompila o grafo (ADR-004).
    graph = compile_pipeline(
        pipeline,
        worker_client=worker_client,
        checkpointer=checkpointer,
    )

    config = {"configurable": {"thread_id": thread_id}}

    # Verifica se há interrupt pendente.
    snap = graph.get_state(config)
    if snap is None:
        raise NoPendingInterruptError(thread_id)

    has_pending_interrupt = False
    for task in snap.tasks:
        if hasattr(task, "interrupts") and task.interrupts:
            has_pending_interrupt = True
            break

    if not has_pending_interrupt:
        logger.info(
            "compile_and_resume_with_pipeline: no pending interrupt (idempotent no-op)",
            extra={"thread_id": thread_id},
        )
        return {
            "status": "no_pending_interrupt",
            "state": dict(snap.values) if snap.values else {},
            "interrupted": False,
        }

    resume_config = snap.config if snap.config else config

    try:
        await graph.ainvoke(Command(resume=resume_value), config=resume_config)
    except Exception as exc:
        logger.exception(
            "compile_and_resume_with_pipeline: ainvoke failed",
            extra={"thread_id": thread_id},
        )
        if owner_id:
            await ws_publish(
                owner_id,
                "pipeline:status",
                {
                    "pipelineId": pipeline.id,
                    "runId": run_id or "",
                    "nodeId": "",
                    "status": "failed",
                    "at": _now_iso(),
                },
            )
        raise

    final_snap = graph.get_state(config)
    final_state = dict(final_snap.values) if final_snap is not None else {}

    interrupted = False
    if final_snap is not None:
        for task in final_snap.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                interrupted = True
                break

    if interrupted:
        status = "interrupted"
    elif final_state.get("pipeline_status") == "failed":
        status = "failed"
    elif final_snap is not None and final_snap.next:
        status = "paused"
    else:
        status = "completed"

    if owner_id:
        await ws_publish(
            owner_id,
            "pipeline:status",
            {
                "pipelineId": pipeline.id,
                "runId": run_id or "",
                "nodeId": "",
                "status": status,
                "at": _now_iso(),
            },
        )

    return {
        "status": status,
        "state": final_state,
        "interrupted": interrupted,
    }
