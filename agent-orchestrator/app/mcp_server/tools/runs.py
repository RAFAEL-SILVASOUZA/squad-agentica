"""Ferramentas MCP de runs de pipeline (execução e gerenciamento).

Registra as ferramentas de execução e gerenciamento de runs no servidor MCP.
Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
delega a operação às funções reutilizáveis de ``app.api.pipeline_runs``.

Erros do banco (``AppError``), do executor e de parsing de UUID são
convertidos em ``ToolError`` com mensagem amigável em pt-BR para o cliente
MCP.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.api.pipeline_runs import (
    _get_executor,
    _load_pipeline,
    _prepare_workspace,
    _run_to_dict,
    get_owned_run,
)
from app.compiler.graph_builder import pipeline_from_dict
from app.core.errors import AppError
from app.db.models import Pipeline, PipelineRun
from app.db.session import async_session_factory
from app.integrations.git_providers import GitProviderError
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError
from app.runtime.executor import (
    NoActiveRunError,
    PipelineAlreadyRunningError,
    RateLimitError,
)
from app.runtime.workspace import WorkspaceError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
async def run_pipeline(
    pipeline_id: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Dispara a execução de uma pipeline.

    Cria um novo run e inicia a execução. Retorna erro se já existe um run
    ativo (409) ou se a pipeline não pertence ao usuário autenticado.

    ``inputs`` é opcional: valores dos inputs do agente de entrada.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(pipeline_id)
    run_inputs = inputs or {}

    async with async_session_factory() as db:
        try:
            # Carrega a pipeline (só do owner).
            db_pipeline, nodes, edges = await _load_pipeline(
                db, parsed_id, user.owner_id
            )

            # 409 se já existe run running no banco.
            existing = await db.execute(
                select(PipelineRun).where(
                    PipelineRun.pipeline_id == parsed_id,
                    PipelineRun.status == "running",
                )
            )
            running_run = existing.scalars().first()
            if running_run is not None:
                raise ToolError(
                    f"Pipeline já está em execução (runId: {running_run.id})."
                )

            # Constrói o dict para o compiler (formato da spec 4.2).
            pipeline_dict = {
                "id": str(db_pipeline.id),
                "name": db_pipeline.name,
                "entryNodeId": str(db_pipeline.entry_node_id),
                "description": db_pipeline.description,
                "status": db_pipeline.status.value
                if hasattr(db_pipeline.status, "value")
                else db_pipeline.status,
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
                        "type": e.type.value
                        if hasattr(e.type, "value")
                        else e.type,
                        "source": str(e.source),
                        "target": str(e.target),
                        "condition": e.condition,
                        "label": e.label,
                        "requiresApproval": e.requires_approval,
                        "approvalChannel": (
                            e.approval_channel.value
                            if e.approval_channel
                            and hasattr(e.approval_channel, "value")
                            else e.approval_channel
                        ),
                        "approvalMessage": e.approval_message,
                        "dataMapping": e.data_mapping,
                        "rejectTarget": e.reject_target,
                    }
                    for e in edges
                ],
            }
            pipeline = pipeline_from_dict(pipeline_dict)

            # Obtém o executor.
            executor = await _get_executor()

            # Cria o PipelineRun no banco.
            run_id = str(uuid.uuid4())
            thread_id = f"{parsed_id}:{run_id}"
            run = PipelineRun(
                id=uuid.UUID(run_id),
                owner_id=user.owner_id,
                pipeline_id=parsed_id,
                thread_id=thread_id,
                status="running",
                started_at=datetime.now(UTC),
            )
            db.add(run)

            # Atualiza status da pipeline.
            db_pipeline.status = "running"
            db_pipeline.started_at = datetime.now(UTC)

            # Prepara o workspace.
            from app.runtime.workspace import WorkspaceManager

            ws = WorkspaceManager()
            try:
                await _prepare_workspace(db, db_pipeline, ws, run_id)
            except (WorkspaceError, GitProviderError) as e:
                ws.remove(run_id)
                run.status = "failed"
                run.error = e.message
                run.completed_at = datetime.now(UTC)
                db_pipeline.status = "failed"
                db_pipeline.completed_at = datetime.now(UTC)
                await db.commit()
                return {
                    "runId": run_id,
                    "status": "failed",
                    "threadId": thread_id,
                    "error": e.message,
                }

            # Inicia a execução.
            try:
                await executor.execute(
                    pipeline,
                    owner_id=str(user.owner_id),
                    run_id=run_id,
                    run_inputs=run_inputs,
                    workspace_dir=str(ws.path(run_id)),
                )
            except PipelineAlreadyRunningError as e:
                await db.rollback()
                ws.remove(run_id)
                raise ToolError(
                    f"Pipeline já está em execução (runId: {e.run_id})."
                ) from e
            except RateLimitError as e:
                await db.rollback()
                ws.remove(run_id)
                raise ToolError(
                    f"Limite de execução atingido. Tente novamente em {e.retry_after}s."
                ) from e

            await db.commit()

            return {
                "runId": run_id,
                "status": "running",
                "threadId": thread_id,
            }
        except AppError as e:
            raise ToolError(f"Erro ao executar pipeline: {e.error}") from e


@mcp.tool()
async def list_runs(
    pipeline_id: str,
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Lista os runs de uma pipeline (paginado, ordenado por data de início desc)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(pipeline_id)

    async with async_session_factory() as db:
        try:
            # Verifica que a pipeline pertence ao usuário.
            result = await db.execute(
                select(Pipeline).where(
                    Pipeline.id == parsed_id,
                    Pipeline.owner_id == user.owner_id,
                )
            )
            if result.scalar_one_or_none() is None:
                raise AppError(404, "not_found", "pipeline_not_found")

            count_result = await db.execute(
                select(PipelineRun)
                .where(PipelineRun.pipeline_id == parsed_id)
                .order_by(PipelineRun.started_at.desc())
            )
            all_runs = list(count_result.scalars().all())
            total = len(all_runs)

            offset = (page - 1) * limit
            items = all_runs[offset : offset + limit]

            return {
                "items": [_run_to_dict(r) for r in items],
                "total": total,
                "page": page,
                "limit": limit,
            }
        except AppError as e:
            raise ToolError(f"Erro ao listar runs: {e.error}") from e


@mcp.tool()
async def get_run(run_id: str) -> dict[str, Any]:
    """Obtém um run por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(run_id)

    async with async_session_factory() as db:
        try:
            run = await get_owned_run(db, parsed_id, user.owner_id)
        except AppError as e:
            raise ToolError(f"Erro ao obter run: {e.error}") from e
        return _run_to_dict(run)


@mcp.tool()
async def cancel_run(run_id: str) -> dict[str, Any]:
    """Cancela um run ativo (running ou paused) de uma pipeline.

    Retorna o id do run cancelado e o novo status.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(run_id)

    async with async_session_factory() as db:
        try:
            run = await get_owned_run(db, parsed_id, user.owner_id)
            pipeline_id = run.pipeline_id

            executor = await _get_executor()

            try:
                stopped_run_id = await executor.stop(str(pipeline_id))
            except NoActiveRunError:
                # Sem run ativo no executor: usa o run do banco.
                stopped_run_id = str(run.id)

            # Atualiza o status do run para cancelled.
            run.status = "cancelled"
            run.completed_at = datetime.now(UTC)

            # Atualiza o status da pipeline.
            result = await db.execute(
                select(Pipeline).where(Pipeline.id == pipeline_id)
            )
            pipeline = result.scalar_one_or_none()
            if pipeline:
                pipeline.status = "draft"
                pipeline.completed_at = datetime.now(UTC)

            await db.commit()

            return {
                "runId": stopped_run_id,
                "status": "cancelled",
            }
        except AppError as e:
            raise ToolError(f"Erro ao cancelar run: {e.error}") from e
