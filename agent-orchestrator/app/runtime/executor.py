"""Pipeline executor: lifecycle management (execute, pause, resume, stop).

Dono: rt-executor (FASE 6). Fontes de verdade:
- CONTRATO-TECNICO.md (ADR-001/004/005/007/009, §7, §8)
- D6-runtime.md §6.1-6.5
- Spec 5.1 (ciclo de vida), 9.1 (endpoints), 14.1 (rate limiting)

Responsabilidades:
- execute: compila, faz streaming por nó em background task (astream), emite
  eventos WS por nó (pipeline:status, agent:output, pipeline:log), grava
  checkpoints (run_checkpoints) e artefatos (artifacts) por nó, detecta
  interrupção (interrupt) e chama o hook de aprovação.
- pause: para o stream sem perder checkpoint (cancela a task de background).
- resume: recompila o grafo (ADR-004) e continua pelo thread_id.
- stop: cancela o run e as aprovações pendentes.
- maxIterations e timeout global: enforcement via node function (ADR-005/007)
  e asyncio.timeout no stream.
- O runId ÚNICO da execução é o do PipelineRun criado pela API (F7): o
  executor NUNCA gera outro id; eventos WS, checkpoints e artefatos usam esse id.

Hook de aprovação (ponto de extensão):
- O executor expõe `register_approval_hook(callback)` para que o nó de HITL
  (hitl-approval) registre o callback que faz upsert da ApprovalRequest e
  dispara a notificação. O callback recebe:
    (run_id, pipeline_id, node_id, interrupt_payload, thread_id)
- Se nenhum hook está registrado, o executor loga um warning e continua.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy import select, text

from app.compiler.graph_builder import (
    Pipeline,
    WorkerClient,
    WorkerUnavailableError,
    compile_pipeline,
)
from app.compiler.state import initial_state
from app.db.models import Artifact, Checkpoint
from app.db.session import async_session_factory
from app.runtime.checkpoint import make_thread_id
from app.runtime.websocket import publish as ws_publish

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting (spec 14.1: execute 5/min por pipeline, in-memory V1)
# ---------------------------------------------------------------------------

EXECUTE_RATE_LIMIT = 5  # requests per minute per pipeline
RATE_WINDOW_SECONDS = 60.0


class _RateLimiter:
    """In-memory rate limiter (V1 single-user, spec 14.1)."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> int | None:
        """Returns None if allowed, or retry_after seconds if rate-limited."""
        now = time.monotonic()
        calls = self._calls[key]
        # Remove old calls outside window.
        self._calls[key] = [t for t in calls if now - t < self._window]
        if len(self._calls[key]) >= self._max:
            oldest = min(self._calls[key])
            retry_after = int(self._window - (now - oldest)) + 1
            return max(retry_after, 1)
        self._calls[key].append(now)
        return None


_rate_limiter = _RateLimiter(EXECUTE_RATE_LIMIT, RATE_WINDOW_SECONDS)

# ---------------------------------------------------------------------------
# Approval hook (ponto de extensão para hitl-approval)
# ---------------------------------------------------------------------------

# Signature: async def hook(run_id, pipeline_id, node_id, interrupt_payload, thread_id)
# Retorna o id da ApprovalRequest persistida (ou None se não persistiu). O
# executor usa esse id no evento ``approval:new`` (approvalId == id da API,
# exigido pela suíte de integração).
ApprovalHook = Callable[
    [str, str, str, Any, str],
    Coroutine[Any, Any, str | None],
]

_approval_hook: ApprovalHook | None = None


def register_approval_hook(hook: ApprovalHook | None) -> None:
    """Register the approval hook (called by hitl-approval at startup).

    The hook is invoked when the executor detects an interrupt in the stream.
    It receives:
        run_id: UUID of the PipelineRun
        pipeline_id: UUID of the Pipeline
        node_id: the approval node ID (e.g. "approval_node_e1")
        interrupt_payload: the value passed to interrupt()
        thread_id: the LangGraph thread_id

    The hook returns the id of the persisted ApprovalRequest (or None).

    ``None`` desregistra (usado em testes).
    """
    global _approval_hook
    _approval_hook = hook
    if hook is not None:
        logger.info("Approval hook registered")
    else:
        logger.info("Approval hook cleared")


def get_approval_hook() -> ApprovalHook | None:
    """Get the currently registered approval hook (for testing)."""
    return _approval_hook


# ---------------------------------------------------------------------------
# Active run tracking (in-memory, V1 single-process)
# ---------------------------------------------------------------------------


@dataclass
class _ActiveRun:
    """Tracks an in-flight pipeline execution."""

    run_id: str
    pipeline_id: str
    owner_id: str
    thread_id: str
    task: asyncio.Task | None = None
    cancelled: bool = False
    stopped: bool = False
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Última falha de nó/execução; gravada em pipeline_runs.error.
    error: str | None = None


# pipeline_id -> _ActiveRun (at most one running run per pipeline)
_active_runs: dict[str, _ActiveRun] = {}


def _now_iso() -> str:
    """Timestamp ISO 8601 UTC com Z explícito (contrato §8)."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Saúde do banco (fail-fast)
# ---------------------------------------------------------------------------
#
# O executor grava checkpoints/artefatos/status no banco. Em testes de
# unidade (MemorySaver, sem postgres) a conexão asyncpg demora a falhar
# (timeout de ~60s) e travaria os testes: checa a saúde UMA vez, com timeout
# curto, e memoiza o resultado. Com o banco fora, a persistência é pulada
# (com log); a execução segue (WS/events não dependem do banco).
_db_health: bool | None = None
DB_HEALTH_TIMEOUT_SECONDS = 3.0


def reset_db_health() -> None:
    """Reseta a cache de saúde do banco (uso em testes)."""
    global _db_health
    _db_health = None


async def _db_available() -> bool:
    """True se o banco responde (checagem memoizada, fail-fast)."""
    global _db_health
    if _db_health is not None:
        return _db_health
    try:
        async with asyncio.timeout(DB_HEALTH_TIMEOUT_SECONDS):
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        _db_health = True
    except Exception:
        _db_health = False
        logger.warning(
            "banco indisponível; persistência de checkpoints/artefatos desativada"
        )
    return _db_health


# ---------------------------------------------------------------------------
# Mapeamento de tipos de porta -> ArtifactType (spec 4.5)
# ---------------------------------------------------------------------------

# ArtifactType é um Enum do SQLAlchemy (valores string), não um enum Python:
# usamos as strings "code"/"document"/"image"/"other" (spec 4.5).
_ARTIFACT_TYPE_MAP: dict[str, str] = {
    "code": "code",
    "document": "document",
    "image": "image",
}


def _artifact_type_for(port_name: str, value: Any) -> str:
    """Infere o ArtifactType do nome/conteúdo da porta (spec 4.5)."""
    lower = port_name.lower()
    if lower in _ARTIFACT_TYPE_MAP:
        return _ARTIFACT_TYPE_MAP[lower]
    if isinstance(value, str) and lower.startswith(("img", "image", "screenshot", "print")):
        return "image"
    return "other"


def _artifact_content(value: Any) -> str:
    """Serializa o valor da porta para o content do Artifact (texto, V1)."""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, default=str)


def get_active_run(pipeline_id: str) -> _ActiveRun | None:
    """Get the active run for a pipeline (for testing/inspection)."""
    return _active_runs.get(pipeline_id)


def clear_active_runs() -> None:
    """Clear all active runs (for testing)."""
    _active_runs.clear()


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


class PipelineExecutor:
    """Manages pipeline execution lifecycle.

    Usage (from API endpoints):
        executor = PipelineExecutor(
            worker_client=HttpWorkerClient(),
            checkpointer=await create_checkpointer(settings.database_url),
        )
        run_id = await executor.execute(pipeline, owner_id)
    """

    def __init__(
        self,
        worker_client: WorkerClient,
        checkpointer: BaseCheckpointSaver,
        global_timeout: int = 3600,
    ) -> None:
        self._worker_client = worker_client
        self._checkpointer = checkpointer
        self._global_timeout = global_timeout

    async def execute(
        self,
        pipeline: Pipeline,
        owner_id: str,
        run_id: str | None = None,
        initial_inputs: dict[str, Any] | None = None,
    ) -> str:
        """Start a new pipeline execution.

        O ``run_id`` é o do PipelineRun criado pela API (F7: runId único):
        a API sempre passa o id persistido; sem ele (testes) um novo UUID é
        gerado. Compila o grafo e inicia o streaming por nó em background task.

        Args:
            pipeline: The Pipeline to execute (with frozen agent snapshots).
            owner_id: The owner (for WebSocket events and DB writes).
            run_id: UUID of the PipelineRun (fonte única de verdade).
            initial_inputs: Optional initial inputs for the entry node.

        Returns:
            The run_id usado na execução (o recebido, ou o gerado).

        Raises:
            PipelineAlreadyRunningError: if a run is already active.
            RateLimitError: if rate limit exceeded.
        """
        if run_id is None:
            run_id = str(uuid.uuid4())
        # Rate limit check (spec 14.1: 5/min per pipeline).
        retry_after = _rate_limiter.check(pipeline.id)
        if retry_after is not None:
            raise RateLimitError(retry_after)

        # Concurrency check: 409 if already running.
        if pipeline.id in _active_runs:
            existing = _active_runs[pipeline.id]
            raise PipelineAlreadyRunningError(existing.run_id)

        thread_id = make_thread_id(pipeline.id, run_id)

        # Compile the graph (ADR-004: always recompile from JSON).
        graph = compile_pipeline(
            pipeline,
            worker_client=self._worker_client,
            checkpointer=self._checkpointer,
        )

        # Build initial state.
        state = initial_state()
        if initial_inputs:
            state["data"] = {pipeline.entry_node_id: initial_inputs}

        config = {"configurable": {"thread_id": thread_id}}

        # Track the active run.
        active = _ActiveRun(
            run_id=run_id,
            pipeline_id=pipeline.id,
            owner_id=owner_id,
            thread_id=thread_id,
        )
        _active_runs[pipeline.id] = active

        # Start background task.
        active.task = asyncio.create_task(
            self._run_stream(graph, config, state, active, pipeline, resume=False),
            name=f"pipeline-run-{run_id}",
        )

        logger.info(
            "Pipeline execution started",
            extra={"pipeline_id": pipeline.id, "run_id": run_id},
        )
        return run_id

    async def pause(self, pipeline_id: str) -> str:
        """Pause an active pipeline execution.

        Cancels the background task. The checkpoint is already saved by
        LangGraph at the last completed node, so no state is lost.

        Args:
            pipeline_id: The pipeline to pause.

        Returns:
            The run_id that was paused.

        Raises:
            NoActiveRunError: if no run is active for this pipeline.
        """
        active = _active_runs.get(pipeline_id)
        if active is None:
            raise NoActiveRunError(pipeline_id)

        active.cancelled = True
        if active.task is not None and not active.task.done():
            active.task.cancel()
            try:
                await active.task
            except asyncio.CancelledError:
                pass

        # Remove from active (the run is now "paused" in DB).
        _active_runs.pop(pipeline_id, None)

        # Emit status event.
        await ws_publish(
            active.owner_id,
            "pipeline:status",
            {
                "pipelineId": pipeline_id,
                "runId": active.run_id,
                "nodeId": "",
                "status": "paused",
                "at": _now_iso(),
            },
        )

        logger.info(
            "Pipeline paused",
            extra={"pipeline_id": pipeline_id, "run_id": active.run_id},
        )
        return active.run_id

    async def resume(
        self,
        pipeline: Pipeline,
        owner_id: str,
        run_id: str,
        resume_input: Any = None,
    ) -> str:
        """Resume a paused pipeline execution.

        Recompiles the graph (ADR-004) and continues from the last checkpoint
        using the same thread_id.

        ``resume_input`` é o payload de retomada: ``None`` continua de onde
        parou; um ``Command(resume=...)`` responde um interrupt de aprovação
        (HITL, spec 5.3).

        Args:
            pipeline: The Pipeline (recompiled from JSON).
            owner_id: The owner (for WebSocket events).
            run_id: The run_id to resume.
            resume_input: Optional resume payload (None ou Command).

        Returns:
            The run_id (same as input).

        Raises:
            PipelineAlreadyRunningError: if a run is already active.
        """
        if pipeline.id in _active_runs:
            existing = _active_runs[pipeline.id]
            if existing.task is not None and not existing.task.done():
                raise PipelineAlreadyRunningError(existing.run_id)
            _active_runs.pop(pipeline.id, None)

        thread_id = make_thread_id(pipeline.id, run_id)

        # Recompile (ADR-004: always recompile from JSON).
        graph = compile_pipeline(
            pipeline,
            worker_client=self._worker_client,
            checkpointer=self._checkpointer,
        )

        config = {"configurable": {"thread_id": thread_id}}

        # Track the active run.
        active = _ActiveRun(
            run_id=run_id,
            pipeline_id=pipeline.id,
            owner_id=owner_id,
            thread_id=thread_id,
        )
        _active_runs[pipeline.id] = active

        # Resume: invoke com o payload de retomada (continua do checkpoint).
        active.task = asyncio.create_task(
            self._run_stream(
                graph,
                config,
                resume_input,
                active,
                pipeline,
                resume=True,
            ),
            name=f"pipeline-resume-{run_id}",
        )

        logger.info(
            "Pipeline resumed",
            extra={"pipeline_id": pipeline.id, "run_id": run_id},
        )
        return run_id

    async def stop(self, pipeline_id: str) -> str:
        """Stop (cancel) an active pipeline execution.

        Cancels the background task and marks the run as cancelled.
        Pending approvals should be cancelled by the caller (API layer).

        Args:
            pipeline_id: The pipeline to stop.

        Returns:
            The run_id that was stopped.

        Raises:
            NoActiveRunError: if no run is active for this pipeline.
        """
        active = _active_runs.get(pipeline_id)
        if active is None:
            raise NoActiveRunError(pipeline_id)

        active.cancelled = True
        active.stopped = True
        if active.task is not None and not active.task.done():
            active.task.cancel()
            try:
                await active.task
            except asyncio.CancelledError:
                pass

        _active_runs.pop(pipeline_id, None)

        # Emit status event.
        await ws_publish(
            active.owner_id,
            "pipeline:status",
            {
                "pipelineId": pipeline_id,
                "runId": active.run_id,
                "nodeId": "",
                "status": "cancelled",
                "at": _now_iso(),
            },
        )

        logger.info(
            "Pipeline stopped",
            extra={"pipeline_id": pipeline_id, "run_id": active.run_id},
        )
        return active.run_id

    async def _run_stream(
        self,
        graph: Any,
        config: dict[str, Any],
        state: dict[str, Any] | None,
        active: _ActiveRun,
        pipeline: Pipeline,
        *,
        resume: bool,
    ) -> None:
        """Background task: stream the graph execution por nó.

        Usa ``astream`` para emitir eventos por nó (contrato §7):
        - ``pipeline:status`` por nó (completed/failed) + agregado final;
        - ``agent:output`` com o output de cada nó;
        - grava Checkpoint (run_checkpoints) e Artifact (artifacts) por nó.

        Handles:
        - Normal completion
        - Interrupt detection (approval hook) via aget_state (async)
        - Worker failure (node failed, run resumable)
        - Timeout (global)
        - Cancellation (pause/stop)
        """
        final_status: str = "failed"
        try:
            # Use asyncio.timeout for global timeout (Python 3.11+).
            async with asyncio.timeout(self._global_timeout):
                async for update in graph.astream(
                    state, config=config, stream_mode="updates"
                ):
                    await self._process_stream_update(update, active, pipeline)

            # Stream terminou: lê o estado final (F1: aget_state, assíncrono
            # sobre o AsyncPostgresSaver).
            snap = await graph.aget_state(config)
            if snap is not None:
                for task in snap.tasks:
                    if getattr(task, "interrupts", None):
                        await self._handle_interrupt_from_tasks(task, active, pipeline)
                        return

            # Decide pelo pipeline_status do state final (ADR-002).
            values = (snap.values if snap is not None else {}) or {}
            pipeline_status = values.get("pipeline_status", "completed")
            final_status = "failed" if pipeline_status == "failed" else "completed"

        except asyncio.CancelledError:
            # Paused or stopped by user (o API persiste o status final).
            if active.cancelled:
                logger.info(
                    "Run cancelled",
                    extra={"run_id": active.run_id},
                )
            raise  # Re-raise so the task is properly marked as cancelled.

        except WorkerUnavailableError as exc:
            # F14/ADR-001: worker fora do ar -> run PAUSADO (retomável),
            # não failed. O checkpoint do superstep anterior sobrevive; a
            # retomada reexecuta o nó pendente. A persistência de status
            # acontece no bloco final (final_status = "paused").
            logger.warning(
                "Worker unavailable; run paused",
                extra={
                    "pipeline_id": active.pipeline_id,
                    "run_id": active.run_id,
                    "node_id": exc.node_id,
                },
            )
            final_status = "paused"

        except TimeoutError:
            # Global timeout exceeded.
            logger.error(
                "Pipeline global timeout exceeded",
                extra={"pipeline_id": active.pipeline_id, "run_id": active.run_id},
            )
            final_status = "failed"
            active.error = active.error or "tempo limite global da pipeline excedido"

        except Exception as exc:
            # Unexpected error: mark as failed.
            logger.exception(
                "Pipeline execution error",
                extra={"pipeline_id": active.pipeline_id, "run_id": active.run_id},
            )
            final_status = "failed"
            active.error = active.error or f"erro interno: {type(exc).__name__}"

        # Persiste o status final no banco (F7: pipeline_runs.status não fica
        # preso em "running") e emite o status agregado no WS.
        # (Sem DB em testes de unidade: falha só loga; o status WS sai.)
        try:
            await self._persist_run_status(active, final_status)
        except Exception:
            logger.exception(
                "Failed to persist run status",
                extra={"run_id": active.run_id},
            )
        await self._emit_status(active, final_status)

        # Clean up active run tracking (only if still present).
        _active_runs.pop(active.pipeline_id, None)

    # -- eventos por nó + persistência (F10/F11) ----------------------------

    async def _process_stream_update(
        self,
        update: dict[str, Any],
        active: _ActiveRun,
        pipeline: Pipeline,
    ) -> None:
        """Processa um chunk de ``astream(stream_mode='updates')``.

        ``update`` é ``{node_id: state_update}`` (um ou mais nós por chunk).
        Emite ``pipeline:status``/``agent:output`` por nó e grava o
        checkpoint + artefatos do nó (F10).
        """
        for node_id, node_update in (update or {}).items():
            if node_id in ("__start__", "__pregel_validate", "__interrupt__"):
                continue
            state_update = node_update if isinstance(node_update, dict) else {}
            node_status_map = state_update.get("status", {}) or {}
            status = node_status_map.get(node_id)
            if status is None:
                continue

            # pipeline:status por nó (contrato §7).
            await self._emit_status(
                active,
                "completed" if status == "completed" else "failed",
                node_id=str(node_id),
            )

            # pipeline:log (contrato §7): logs do worker e o erro do nó.
            for line in (state_update.get("node_logs", {}) or {}).get(node_id, []) or []:
                await self._emit_log(active, str(node_id), "info", str(line))
            node_error = (state_update.get("node_errors", {}) or {}).get(node_id)
            if node_error:
                active.error = str(node_error)[:2000]
                await self._emit_log(active, str(node_id), "error", active.error)

            # agent:output (contrato §7): outputs namespaced por nodeId.
            outputs = state_update.get("data", {}).get(node_id)
            if outputs is not None:
                await ws_publish(
                    active.owner_id,
                    "agent:output",
                    {
                        "pipelineId": active.pipeline_id,
                        "runId": active.run_id,
                        "nodeId": str(node_id),
                        "output": outputs,
                        "at": _now_iso(),
                    },
                )

            # Checkpoint por nó (spec 4.3): snapshot do estado do grafo.
            # (Sem DB em testes de unidade: falhas aqui só logam, nunca
            # derrubam a execução.)
            try:
                snapshot = await self._current_snapshot(active)
                await self._persist_checkpoint(active, str(node_id), status, snapshot)
            except Exception:
                logger.exception(
                    "Failed to persist checkpoint",
                    extra={"run_id": active.run_id, "node_id": node_id},
                )

            # Artefatos por porta de output (spec 4.5).
            if status == "completed" and isinstance(outputs, dict):
                try:
                    await self._persist_artifacts(active, str(node_id), outputs, pipeline)
                except Exception:
                    logger.exception(
                        "Failed to persist artifacts",
                        extra={"run_id": active.run_id, "node_id": node_id},
                    )

    async def _current_snapshot(self, active: _ActiveRun) -> dict[str, Any]:
        """Retorna o snapshot do estado do grafo (checkpointer da thread)."""
        config = {"configurable": {"thread_id": active.thread_id}}
        tup = await self._checkpointer.aget_tuple(config)
        if tup is None:
            return {}
        checkpoint = getattr(tup, "checkpoint", None) or {}
        values = checkpoint.get("channel_values") or {}
        return {
            "data": values.get("data", {}),
            "actions": values.get("actions", {}),
            "status": values.get("status", {}),
            "iterations": values.get("iterations", {}),
            "max_iter_exceeded": bool(values.get("max_iter_exceeded", False)),
            "pipeline_status": values.get("pipeline_status", "running"),
        }

    async def _persist_checkpoint(
        self,
        active: _ActiveRun,
        node_id: str,
        status: str,
        state_snapshot: dict[str, Any],
    ) -> None:
        """Grava um Checkpoint (run_checkpoints) por nó (spec 4.3)."""
        if not await _db_available():
            return
        from app.db.models import PipelineRun

        async with async_session_factory() as session:
            run_result = await session.execute(
                select(PipelineRun).where(PipelineRun.id == uuid.UUID(active.run_id))
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                return
            cp = Checkpoint(
                id=uuid.uuid4(),
                owner_id=run.owner_id,
                pipeline_id=run.pipeline_id,
                run_id=run.id,
                node_id=node_id,
                state=state_snapshot,
                status="completed" if status == "completed" else "failed",
                timestamp=datetime.now(UTC),
                meta={"status": status, "pipelineStatus": state_snapshot.get("pipeline_status")},
            )
            session.add(cp)
            run.current_checkpoint_id = str(cp.id)
            await session.commit()

    async def _persist_artifacts(
        self,
        active: _ActiveRun,
        node_id: str,
        outputs: dict[str, Any],
        pipeline: Pipeline,
    ) -> None:
        """Grava um Artifact por porta de output do nó (spec 4.5)."""
        if not await _db_available():
            return
        from app.db.models import PipelineRun

        # Tipos de porta declarados no snapshot do agente (se houver).
        port_types: dict[str, str] = {}
        for node in pipeline.nodes:
            if str(node.id) == node_id:
                for port in node.agent_snapshot.outputs:
                    port_types[port.name] = port.type
                break

        async with async_session_factory() as session:
            run_result = await session.execute(
                select(PipelineRun).where(PipelineRun.id == uuid.UUID(active.run_id))
            )
            run = run_result.scalar_one_or_none()
            if run is None:
                return
            for port_name, value in outputs.items():
                content = _artifact_content(value)
                if len(content.encode("utf-8")) > 10 * 1024 * 1024:
                    continue  # limite de 10MB do V1 (spec 4.5)
                # O tipo declarado na porta (spec 4.1: document/code/artifact/
                # signal) vira o ArtifactType quando é um dos três mapeáveis;
                # caso contrário inferimos pelo nome da porta/conteúdo.
                declared = (port_types.get(port_name) or "").lower()
                if declared in _ARTIFACT_TYPE_MAP:
                    art_type = _ARTIFACT_TYPE_MAP[declared]
                else:
                    art_type = _artifact_type_for(port_name, value)
                session.add(
                    Artifact(
                        id=uuid.uuid4(),
                        owner_id=run.owner_id,
                        run_id=run.id,
                        node_id=node_id,
                        name=f"{node_id}.{port_name}",
                        type=art_type,
                        content=content,
                        size=len(content.encode("utf-8")),
                    )
                )
            await session.commit()

    async def _persist_run_status(self, active: _ActiveRun, status: str) -> None:
        """Atualiza pipeline_runs.status e pipeline.status (F7)."""
        if not await _db_available():
            return
        from app.db.models import Pipeline, PipelineRun

        async with async_session_factory() as session:
            run_result = await session.execute(
                select(PipelineRun).where(PipelineRun.id == uuid.UUID(active.run_id))
            )
            run = run_result.scalar_one_or_none()
            if run is not None:
                run.status = status
                if status in ("completed", "failed", "cancelled"):
                    run.completed_at = datetime.now(UTC)
                if status == "failed" and active.error:
                    run.error = active.error
                await session.commit()

            pipe_result = await session.execute(
                select(Pipeline).where(Pipeline.id == uuid.UUID(active.pipeline_id))
            )
            pipe = pipe_result.scalar_one_or_none()
            if pipe is not None:
                pipe.status = status
                if status in ("completed", "failed", "cancelled"):
                    pipe.completed_at = datetime.now(UTC)
                await session.commit()

    async def _handle_interrupt_from_tasks(
        self,
        task: Any,
        active: _ActiveRun,
        pipeline: Pipeline,
    ) -> None:
        """Handle an interrupt detected via state.tasks (LangGraph 0.2.x).

        The task has .name (node ID) and .interrupts (tuple of Interrupt objects).
        Each Interrupt has .value (the payload passed to interrupt()).
        """
        node_id = task.name  # e.g. "approval_node_e1"

        for interrupt_item in task.interrupts:
            payload = interrupt_item.value if hasattr(interrupt_item, "value") else interrupt_item
            # ADR-009: o task id real do LangGraph (PregelTask.id ==
            # CONFIG_KEY_TASK_ID) é a chave de idempotência da ApprovalRequest.
            # Ele é estável entre execuções/resumes da mesma pausa, então o
            # upsert (feito pelo hook do hitl-approval) não duplica. Injetamos
            # no payload sob ``__interruptId__`` para o hook consumir.
            interrupt_id = str(getattr(task, "id", "") or uuid.uuid4())
            if isinstance(payload, dict):
                payload = {**payload, "__interruptId__": interrupt_id}

            # Emit pipeline:status event (waiting_approval).
            await ws_publish(
                active.owner_id,
                "pipeline:status",
                {
                    "pipelineId": active.pipeline_id,
                    "runId": active.run_id,
                    "nodeId": node_id,
                    "status": "waiting_approval",
                    "at": _now_iso(),
                },
            )

            # Call the approval hook (ADR-009: upsert + notification).
            # O hook devolve o id da ApprovalRequest persistida; ele vira o
            # approvalId do evento (F6: approvalId == id da API).
            approval_id: str | None = None
            if _approval_hook is not None:
                try:
                    approval_id = await _approval_hook(
                        run_id=active.run_id,
                        pipeline_id=active.pipeline_id,
                        node_id=node_id,
                        interrupt_payload=payload,
                        thread_id=active.thread_id,
                    )
                except Exception:
                    logger.exception(
                        "Approval hook failed",
                        extra={"run_id": active.run_id, "node_id": node_id},
                    )
            else:
                logger.warning(
                    "Interrupt detected but no approval hook registered",
                    extra={"run_id": active.run_id, "node_id": node_id},
                )

            # Nota (F6/ADR-009): o evento ``approval:new`` é emitido pelo hook
            # (hitl-approval, ``_notify_new_approval``) APÓS o upsert, com o
            # approvalId real da API. O executor não emite aqui para não
            # duplicar o evento (a suíte de integração exige approvalId ==
            # id persistida). ``approval_id`` é usado apenas para logs/debug.
            if approval_id is None:
                logger.warning(
                    "approval:new sem ApprovalRequest persistida (hook ausente/falhou)",
                    extra={"run_id": active.run_id, "node_id": node_id},
                )

    async def _emit_status(
        self, active: _ActiveRun, status: str, node_id: str = ""
    ) -> None:
        """Emit a pipeline:status WebSocket event (contrato §7)."""
        await ws_publish(
            active.owner_id,
            "pipeline:status",
            {
                "pipelineId": active.pipeline_id,
                "runId": active.run_id,
                "nodeId": node_id,
                "status": status,
                "at": _now_iso(),
            },
        )

    async def _emit_log(
        self, active: _ActiveRun, node_id: str, level: str, message: str
    ) -> None:
        """Emit a pipeline:log WebSocket event (contrato §7)."""
        await ws_publish(
            active.owner_id,
            "pipeline:log",
            {
                "pipelineId": active.pipeline_id,
                "runId": active.run_id,
                "nodeId": node_id,
                "level": level,
                "message": message,
                "at": _now_iso(),
            },
        )


# ---------------------------------------------------------------------------
# Exceptions (mapped to HTTP errors in the API layer)
# ---------------------------------------------------------------------------


class PipelineAlreadyRunningError(Exception):
    """409: pipeline already has a running execution."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Pipeline already running (runId={run_id})")
        self.run_id = run_id


class NoActiveRunError(Exception):
    """404: no active run for this pipeline."""

    def __init__(self, pipeline_id: str) -> None:
        super().__init__(f"No active run for pipeline {pipeline_id}")
        self.pipeline_id = pipeline_id


class RateLimitError(Exception):
    """429: rate limit exceeded."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Rate limited, retry after {retry_after}s")
        self.retry_after = retry_after
