"""Pipeline executor: lifecycle management (execute, pause, resume, stop).

Dono: rt-executor (FASE 6). Fontes de verdade:
- CONTRATO-TECNICO.md (ADR-001/004/005/007/009, §7, §8)
- D6-runtime.md §6.1-6.5
- Spec 5.1 (ciclo de vida), 9.1 (endpoints), 14.1 (rate limiting)

Responsabilidades:
- execute: cria PipelineRun, congela snapshots, compila, faz streaming em
  background task, detecta interrupção (interrupt) e chama o hook de aprovação.
- pause: para o stream sem perder checkpoint (cancela a task de background).
- resume: recompila o grafo (ADR-004) e continua pelo thread_id.
- stop: cancela o run e as aprovações pendentes.
- maxIterations e timeout global: enforcement via node function (ADR-005/007)
  e asyncio.timeout no stream.

Hook de aprovação (ponto de extensão):
- O executor expõe `register_approval_hook(callback)` para que o nó de HITL
  (hitl-approval) registre o callback que faz upsert da ApprovalRequest e
  dispara a notificação. O callback recebe:
    (run_id, pipeline_id, node_id, interrupt_payload, thread_id)
- Se nenhum hook está registrado, o executor loga um warning e continua.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.compiler.graph_builder import Pipeline, WorkerClient, compile_pipeline
from app.compiler.state import initial_state
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
ApprovalHook = Callable[
    [str, str, str, Any, str],
    Coroutine[Any, Any, None],
]

_approval_hook: ApprovalHook | None = None


def register_approval_hook(hook: ApprovalHook) -> None:
    """Register the approval hook (called by hitl-approval at startup).

    The hook is invoked when the executor detects an interrupt in the stream.
    It receives:
        run_id: UUID of the PipelineRun
        pipeline_id: UUID of the Pipeline
        node_id: the approval node ID (e.g. "approval_node_e1")
        interrupt_payload: the value passed to interrupt()
        thread_id: the LangGraph thread_id
    """
    global _approval_hook
    _approval_hook = hook
    logger.info("Approval hook registered")


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
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))


# pipeline_id -> _ActiveRun (at most one running run per pipeline)
_active_runs: dict[str, _ActiveRun] = {}


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
        initial_inputs: dict[str, Any] | None = None,
    ) -> str:
        """Start a new pipeline execution.

        Creates a PipelineRun, compiles the graph, and starts streaming in
        a background task.

        Args:
            pipeline: The Pipeline to execute (with frozen agent snapshots).
            owner_id: The owner (for WebSocket events).
            initial_inputs: Optional initial inputs for the entry node.

        Returns:
            The run_id (UUID string) of the new PipelineRun.

        Raises:
            PipelineAlreadyRunningError: if a run is already active.
            RateLimitError: if rate limit exceeded.
        """
        # Rate limit check (spec 14.1: 5/min per pipeline).
        retry_after = _rate_limiter.check(pipeline.id)
        if retry_after is not None:
            raise RateLimitError(retry_after)

        # Concurrency check: 409 if already running.
        if pipeline.id in _active_runs:
            existing = _active_runs[pipeline.id]
            raise PipelineAlreadyRunningError(existing.run_id)

        # Create run.
        run_id = str(uuid.uuid4())
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
            self._run_stream(graph, config, state, active, pipeline),
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
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    ) -> str:
        """Resume a paused pipeline execution.

        Recompiles the graph (ADR-004) and continues from the last checkpoint
        using the same thread_id.

        Args:
            pipeline: The Pipeline (recompiled from JSON).
            owner_id: The owner (for WebSocket events).
            run_id: The run_id to resume.

        Returns:
            The run_id (same as input).

        Raises:
            PipelineAlreadyRunningError: if a run is already active.
        """
        if pipeline.id in _active_runs:
            existing = _active_runs[pipeline.id]
            raise PipelineAlreadyRunningError(existing.run_id)

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

        # Resume: invoke with None input (continues from checkpoint).
        active.task = asyncio.create_task(
            self._run_stream(graph, config, None, active, pipeline),
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
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
    ) -> None:
        """Background task: stream the graph execution.

        Handles:
        - Normal completion
        - Interrupt detection (approval hook) via state.tasks
        - Worker failure (node failed, run resumable)
        - Timeout (global)
        - Cancellation (pause/stop)
        """
        try:
            # Use asyncio.timeout for global timeout (Python 3.11+).
            async with asyncio.timeout(self._global_timeout):
                if state is not None:
                    # New execution: invoke with initial state.
                    result = await graph.ainvoke(state, config=config)
                else:
                    # Resume: invoke with None (continues from checkpoint).
                    result = await graph.ainvoke(None, config=config)

            # Check for interrupt via state.tasks (LangGraph 0.2.x API).
            snap = graph.get_state(config)
            if snap is not None:
                # Check if any task has interrupts.
                for task in snap.tasks:
                    if task.interrupts:
                        await self._handle_interrupt_from_tasks(
                            task, active, pipeline
                        )
                        return

                # Check if the graph is paused (has next nodes but didn't finish).
                if snap.next:
                    # Paused (worker failure or other reason).
                    await self._emit_status(active, "paused")
                    return

            # Check pipeline_status for failure.
            if result is not None:
                pipeline_status = result.get("pipeline_status", "completed")
                if pipeline_status == "failed":
                    await self._emit_status(active, "failed")
                else:
                    await self._emit_status(active, "completed")

        except asyncio.CancelledError:
            # Paused or stopped by user.
            if active.cancelled:
                logger.info(
                    "Run cancelled",
                    extra={"run_id": active.run_id},
                )
            raise  # Re-raise so the task is properly marked as cancelled.

        except TimeoutError:
            # Global timeout exceeded.
            logger.error(
                "Pipeline global timeout exceeded",
                extra={"pipeline_id": active.pipeline_id, "run_id": active.run_id},
            )
            await self._emit_status(active, "failed")

        except Exception:
            # Unexpected error: mark as failed.
            logger.exception(
                "Pipeline execution error",
                extra={"pipeline_id": active.pipeline_id, "run_id": active.run_id},
            )
            await self._emit_status(active, "failed")

        finally:
            # Clean up active run tracking (only if still present).
            _active_runs.pop(active.pipeline_id, None)

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
            interrupt_id = str(uuid.uuid4())

            # Emit pipeline:status event (waiting_approval).
            await ws_publish(
                active.owner_id,
                "pipeline:status",
                {
                    "pipelineId": active.pipeline_id,
                    "runId": active.run_id,
                    "nodeId": node_id,
                    "status": "waiting_approval",
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                },
            )

            # Call the approval hook (ADR-009: upsert + notification).
            if _approval_hook is not None:
                try:
                    await _approval_hook(
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

            # Emit approval:new event.
            message = ""
            if isinstance(payload, dict):
                message = payload.get("message", "")

            await ws_publish(
                active.owner_id,
                "approval:new",
                {
                    "approvalId": interrupt_id,
                    "pipelineId": active.pipeline_id,
                    "runId": active.run_id,
                    "nodeId": node_id,
                    "message": message,
                    "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                },
            )

    async def _emit_status(self, active: _ActiveRun, status: str) -> None:
        """Emit a pipeline:status WebSocket event."""
        await ws_publish(
            active.owner_id,
            "pipeline:status",
            {
                "pipelineId": active.pipeline_id,
                "runId": active.run_id,
                "nodeId": "",
                "status": status,
                "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
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
