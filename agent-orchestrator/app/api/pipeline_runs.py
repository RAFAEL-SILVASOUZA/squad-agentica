"""Pipeline execution endpoints (spec 9.1).

Dono: rt-executor (FASE 6). Endpoints:
- POST /api/pipelines/:id/execute
- POST /api/pipelines/:id/pause
- POST /api/pipelines/:id/resume
- POST /api/pipelines/:id/stop
- GET /api/pipelines/:id/runs
- GET /api/pipelines/:id/checkpoints
- POST /api/pipelines/:id/checkpoints/:cpId/resume

Contrato §8: envelope de erro, camelCase, 409/429/404.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.compiler.graph_builder import pipeline_from_dict
from app.core.config import settings
from app.core.errors import AppError
from app.db.models import (
    Checkpoint,
    Pipeline,
    PipelineEdge,
    PipelineNode,
    PipelineRun,
    User,
)
from app.db.session import get_db
from app.runtime.executor import (
    NoActiveRunError,
    PipelineAlreadyRunningError,
    PipelineExecutor,
    RateLimitError,
)
from app.runtime.worker_client import HttpWorkerClient

router = APIRouter(tags=["pipeline-runs"])

# ---------------------------------------------------------------------------
# Executor singleton (lazy initialization)
# ---------------------------------------------------------------------------

_executor: PipelineExecutor | None = None
_checkpointer: Any = None


async def _get_executor() -> PipelineExecutor:
    """Get or create the PipelineExecutor singleton.

    The checkpointer is created once at first use (startup).
    In production, this would be initialized in the app lifespan.
    """
    global _executor, _checkpointer
    if _executor is None:
        from app.runtime.checkpoint import create_checkpointer

        _checkpointer = await create_checkpointer(settings.database_url)
        _executor = PipelineExecutor(
            worker_client=HttpWorkerClient(),
            checkpointer=_checkpointer,
        )
    return _executor


async def _shutdown_executor() -> None:
    """Shutdown the executor (close checkpointer). Called at app shutdown."""
    global _executor, _checkpointer
    if _checkpointer is not None:
        from app.runtime.checkpoint import close_checkpointer

        await close_checkpointer(_checkpointer)
    _executor = None
    _checkpointer = None


# Nomes públicos usados no lifespan do app (main.py).
get_executor = _get_executor
shutdown_executor = _shutdown_executor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pipeline_to_dict(
    pipeline: Pipeline,
    nodes: list[PipelineNode],
    edges: list[PipelineEdge],
) -> dict[str, Any]:
    """Convert DB models to the JSON format expected by pipeline_from_dict."""
    return {
        "id": str(pipeline.id),
        "name": pipeline.name,
        "entryNodeId": str(pipeline.entry_node_id),
        "description": pipeline.description,
        "status": pipeline.status.value if hasattr(pipeline.status, "value") else pipeline.status,
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


async def _load_pipeline(
    db: AsyncSession, pipeline_id: uuid.UUID, owner_id: uuid.UUID | None = None
) -> tuple[Pipeline, list[PipelineNode], list[PipelineEdge]]:
    """Load pipeline with nodes and edges from DB.

    Se ``owner_id`` for fornecido, pipelines de outro owner viram 404
    (F4: isolamento do runtime de pipeline).
    """
    stmt = select(Pipeline).where(Pipeline.id == pipeline_id)
    if owner_id is not None:
        stmt = stmt.where(Pipeline.owner_id == owner_id)
    result = await db.execute(stmt)
    pipeline = result.scalar_one_or_none()
    if pipeline is None:
        raise AppError(404, "not_found", "pipeline_not_found")

    nodes_result = await db.execute(
        select(PipelineNode).where(PipelineNode.pipeline_id == pipeline_id)
    )
    nodes = list(nodes_result.scalars().all())

    edges_result = await db.execute(
        select(PipelineEdge).where(PipelineEdge.pipeline_id == pipeline_id)
    )
    edges = list(edges_result.scalars().all())

    return pipeline, nodes, edges


def _run_to_dict(run: PipelineRun) -> dict[str, Any]:
    """Convert PipelineRun to camelCase dict (spec 4.2)."""
    return {
        "id": str(run.id),
        "pipelineId": str(run.pipeline_id),
        "threadId": run.thread_id,
        "status": run.status.value if hasattr(run.status, "value") else run.status,
        "currentCheckpointId": run.current_checkpoint_id,
        "startedAt": run.started_at.isoformat().replace("+00:00", "Z")
        if run.started_at
        else None,
        "completedAt": run.completed_at.isoformat().replace("+00:00", "Z")
        if run.completed_at
        else None,
        "error": run.error,
    }


def _checkpoint_to_dict(cp: Checkpoint) -> dict[str, Any]:
    """Convert Checkpoint to camelCase dict (spec 4.3)."""
    return {
        "id": str(cp.id),
        "pipelineId": str(cp.pipeline_id),
        "nodeId": cp.node_id,
        "state": cp.state,
        "timestamp": cp.timestamp.isoformat().replace("+00:00", "Z")
        if cp.timestamp
        else None,
        "status": cp.status.value if hasattr(cp.status, "value") else cp.status,
        "metadata": cp.meta,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/pipelines/{pipeline_id}/execute")
async def execute_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/execute

    Creates a new PipelineRun and starts execution.
    409 if already running. 429 if rate limited.
    """
    # Load pipeline (só do owner; F4).
    db_pipeline, nodes, edges = await _load_pipeline(db, pipeline_id, user.owner_id)

    # 409 se já existe run running/paused no banco (fonte durável; o in-memory
    # do executor é a segunda camada).
    existing = await db.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.status == "running",
        )
    )
    running_run = existing.scalars().first()
    if running_run is not None:
        raise AppError(
            409, "conflict", "pipeline_already_running", {"runId": str(running_run.id)}
        )

    # Build Pipeline object for the compiler.
    pipeline_dict = _pipeline_to_dict(db_pipeline, nodes, edges)
    pipeline = pipeline_from_dict(pipeline_dict)

    # Get executor.
    executor = await _get_executor()

    # Create PipelineRun in DB (runId único; F7: o executor usa ESTE id).
    run_id = str(uuid.uuid4())
    thread_id = f"{pipeline_id}:{run_id}"
    run = PipelineRun(
        id=uuid.UUID(run_id),
        owner_id=user.owner_id,
        pipeline_id=pipeline_id,
        thread_id=thread_id,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)

    # Update pipeline status.
    db_pipeline.status = "running"
    db_pipeline.started_at = datetime.now(UTC)

    # Start execution (pode lançar 409/429). Em erro, o run NÃO vira órfão
    # (F8): removemos antes de re-levantar o envelope.
    try:
        await executor.execute(
            pipeline, owner_id=str(user.owner_id), run_id=run_id
        )
    except PipelineAlreadyRunningError as e:
        await db.rollback()
        raise AppError(
            409, "conflict", "pipeline_already_running", {"runId": e.run_id}
        ) from e
    except RateLimitError as e:
        await db.rollback()
        raise AppError(
            429, "rate_limited", "rate_limited", {"retryAfter": e.retry_after}
        ) from e

    await db.commit()

    return {
        "runId": run_id,
        "status": "running",
        "threadId": thread_id,
    }


@router.post("/pipelines/{pipeline_id}/pause")
async def pause_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/pause

    Pauses the active execution. The checkpoint is preserved.
    """
    # Dono da pipeline (F4).
    owner_result = await db.execute(
        select(Pipeline.owner_id).where(Pipeline.id == pipeline_id)
    )
    owner_id = owner_result.scalar_one_or_none()
    if owner_id is None or owner_id != user.owner_id:
        raise AppError(404, "not_found", "pipeline_not_found")

    executor = await _get_executor()

    try:
        run_id = await executor.pause(str(pipeline_id))
    except NoActiveRunError:
        raise AppError(404, "not_found", "no_active_run") from None

    # Update run status in DB.
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.id == uuid.UUID(run_id),
        )
    )
    run = result.scalar_one_or_none()
    if run:
        run.status = "paused"
        await db.commit()

    # Update pipeline status.
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline:
        pipeline.status = "paused"
        await db.commit()

    return {"runId": run_id, "status": "paused"}


@router.post("/pipelines/{pipeline_id}/resume")
async def resume_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/resume

    Resumes a paused execution from the last checkpoint.
    Recompiles the graph (ADR-004) and continues via thread_id.
    """
    # Load pipeline (só do owner; F4).
    db_pipeline, nodes, edges = await _load_pipeline(db, pipeline_id, user.owner_id)

    # Find the paused run.
    result = await db.execute(
        select(PipelineRun)
        .where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.status == "paused",
        )
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise AppError(404, "not_found", "no_paused_run")

    # Build Pipeline object.
    pipeline_dict = _pipeline_to_dict(db_pipeline, nodes, edges)
    pipeline = pipeline_from_dict(pipeline_dict)

    # Get executor.
    executor = await _get_executor()

    try:
        await executor.resume(pipeline, owner_id=str(user.owner_id), run_id=str(run.id))
    except PipelineAlreadyRunningError as e:
        raise AppError(
            409, "conflict", "pipeline_already_running", {"runId": e.run_id}
        ) from e

    # Update run status.
    run.status = "running"
    await db.commit()

    # Update pipeline status.
    db_pipeline.status = "running"
    await db.commit()

    return {"runId": str(run.id), "status": "running"}


@router.post("/pipelines/{pipeline_id}/stop")
async def stop_pipeline(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/stop

    Cancels the active run and all pending approvals.
    """
    # Dono da pipeline (F4).
    owner_result = await db.execute(
        select(Pipeline.owner_id).where(Pipeline.id == pipeline_id)
    )
    owner_id = owner_result.scalar_one_or_none()
    if owner_id is None or owner_id != user.owner_id:
        raise AppError(404, "not_found", "pipeline_not_found")

    executor = await _get_executor()

    try:
        run_id = await executor.stop(str(pipeline_id))
    except NoActiveRunError:
        # No active run: check if there's a paused/running run to cancel.
        result = await db.execute(
            select(PipelineRun)
            .where(
                PipelineRun.pipeline_id == pipeline_id,
                PipelineRun.status.in_(["running", "paused"]),
            )
            .order_by(PipelineRun.started_at.desc())
            .limit(1)
        )
        run = result.scalar_one_or_none()
        if run is None:
            raise AppError(404, "not_found", "no_active_run") from None
        run_id = str(run.id)

    # Update run status to cancelled.
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.pipeline_id == pipeline_id,
            PipelineRun.id == uuid.UUID(run_id),
        )
    )
    run = result.scalar_one_or_none()
    if run:
        run.status = "cancelled"
        run.completed_at = datetime.now(UTC)
        await db.commit()

    # Cancel pending approvals for this pipeline (spec 9.6).
    from app.db.models import ApprovalRequest

    approvals_result = await db.execute(
        select(ApprovalRequest).where(
            ApprovalRequest.pipeline_id == pipeline_id,
            ApprovalRequest.status == "pending",
        )
    )
    pending_approvals = list(approvals_result.scalars().all())
    for approval in pending_approvals:
        approval.status = "cancelled"
    if pending_approvals:
        await db.commit()

    # Update pipeline status.
    result = await db.execute(select(Pipeline).where(Pipeline.id == pipeline_id))
    pipeline = result.scalar_one_or_none()
    if pipeline:
        pipeline.status = "draft"
        pipeline.completed_at = datetime.now(UTC)
        await db.commit()

    return {"runId": run_id, "status": "cancelled"}


@router.get("/pipelines/{pipeline_id}/runs")
async def list_runs(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """GET /api/pipelines/:id/runs

    Lists runs of a pipeline (paginated, spec §8). F4: só do owner.
    """
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id, Pipeline.owner_id == user.owner_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise AppError(404, "not_found", "pipeline_not_found")

    # Count total (ordenado por started_at desc para paginação estável).
    count_result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.pipeline_id == pipeline_id)
        .order_by(PipelineRun.started_at.desc())
    )
    all_runs = list(count_result.scalars().all())
    total = len(all_runs)

    # Paginate.
    offset = (page - 1) * limit
    items = all_runs[offset : offset + limit]

    return {
        "items": [_run_to_dict(r) for r in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.get("/pipelines/{pipeline_id}/checkpoints")
async def list_checkpoints(
    pipeline_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """GET /api/pipelines/:id/checkpoints

    Lists checkpoints of a pipeline (paginated). F4: só do owner.
    """
    # Verify pipeline exists (só do owner; F4).
    result = await db.execute(
        select(Pipeline).where(
            Pipeline.id == pipeline_id, Pipeline.owner_id == user.owner_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise AppError(404, "not_found", "pipeline_not_found")

    # Query checkpoints.
    result = await db.execute(
        select(Checkpoint)
        .where(Checkpoint.pipeline_id == pipeline_id)
        .order_by(Checkpoint.timestamp.desc())
    )
    all_cps = list(result.scalars().all())
    total = len(all_cps)

    offset = (page - 1) * limit
    items = all_cps[offset : offset + limit]

    return {
        "items": [_checkpoint_to_dict(cp) for cp in items],
        "total": total,
        "page": page,
        "limit": limit,
    }


@router.post("/pipelines/{pipeline_id}/checkpoints/{cp_id}/resume")
async def resume_from_checkpoint(
    pipeline_id: uuid.UUID,
    cp_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """POST /api/pipelines/:id/checkpoints/:cpId/resume

    Resumes execution from a specific checkpoint (time travel).
    This creates a new run that starts from the checkpoint's state.
    F4: só do owner.
    """
    # Load pipeline (só do owner; F4).
    db_pipeline, nodes, edges = await _load_pipeline(db, pipeline_id, user.owner_id)

    # Find the checkpoint.
    result = await db.execute(
        select(Checkpoint).where(
            Checkpoint.id == cp_id,
            Checkpoint.pipeline_id == pipeline_id,
        )
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        raise AppError(404, "not_found", "checkpoint_not_found")

    # Build Pipeline object.
    pipeline_dict = _pipeline_to_dict(db_pipeline, nodes, edges)
    pipeline = pipeline_from_dict(pipeline_dict)

    # Create a new run (time travel creates a new run from the checkpoint).
    # O runId é este e o executor usa o MESMO id (F7). Em 409/429 o run
    # é removido (F8: sem órfão).
    run_id = str(uuid.uuid4())
    thread_id = f"{pipeline_id}:{run_id}"

    run = PipelineRun(
        id=uuid.UUID(run_id),
        owner_id=user.owner_id,
        pipeline_id=pipeline_id,
        thread_id=thread_id,
        status="running",
        started_at=datetime.now(UTC),
    )
    db.add(run)
    db_pipeline.status = "running"

    # Get executor and resume from checkpoint state.
    executor = await _get_executor()

    try:
        # Resume from checkpoint: use the checkpoint's state as initial state.
        # The thread_id is new, so we pass the checkpoint state as input.
        await executor.execute(
            pipeline,
            owner_id=str(user.owner_id),
            run_id=run_id,
            initial_inputs=checkpoint.state,
        )
    except PipelineAlreadyRunningError as e:
        await db.delete(run)
        db_pipeline.status = "draft"
        await db.commit()
        raise AppError(
            409, "conflict", "pipeline_already_running", {"runId": e.run_id}
        ) from e
    except RateLimitError as e:
        await db.delete(run)
        db_pipeline.status = "draft"
        await db.commit()
        raise AppError(
            429, "rate_limited", "rate_limited", {"retryAfter": e.retry_after}
        ) from e

    await db.commit()

    return {
        "runId": run_id,
        "status": "running",
        "resumedFromCheckpoint": str(cp_id),
    }
