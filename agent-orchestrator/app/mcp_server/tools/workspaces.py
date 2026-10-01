"""Ferramentas MCP de Workspaces (arquivos dos runs).

Registra as ferramentas de gerenciamento de workspaces (árvore de arquivos
dos runs) no servidor MCP. Cada ferramenta lê o usuário autenticado via
``get_current_mcp_user`` e delega a operação ao ``WorkspaceManager`` (mesmo
service usado pelo router REST em ``app/api/workspaces.py``).

O "workspace" é identificado pelo ``run_id`` (cada run tem um diretório de
arquivos no disco). Erros (``AppError``/``WorkspaceError``) e de parsing de
UUID são convertidos em ``ToolError`` com mensagem amigável em pt-BR.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.errors import AppError
from app.db.models import PipelineRun
from app.db.session import async_session_factory
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError
from app.runtime.workspace import TREE_MAX_ENTRIES, WorkspaceError, WorkspaceManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _run_to_dict(run: PipelineRun, has_workspace: bool, file_count: int) -> dict[str, Any]:
    """Converte o model PipelineRun para dict de workspace (camelCase)."""
    status_val = (
        run.status.value if hasattr(run.status, "value") else str(run.status)
    )
    return {
        "id": str(run.id),
        "pipelineId": str(run.pipeline_id),
        "status": status_val,
        "hasWorkspace": has_workspace,
        "fileCount": file_count,
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
    }


async def _get_owned_run(db, owner_id: uuid.UUID, run_id: uuid.UUID) -> PipelineRun:
    result = await db.execute(
        select(PipelineRun).where(
            PipelineRun.id == run_id, PipelineRun.owner_id == owner_id
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise AppError(404, "not_found", "workspace_not_found")
    return run


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_workspaces(
    page: int = 1,
    limit: int = 20,
) -> dict[str, Any]:
    """Lista os workspaces (runs) do usuário autenticado, com paginação.

    Cada item indica se o workspace existe no disco e quantos arquivos tem.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    ws = WorkspaceManager()

    async with async_session_factory() as db:
        base = PipelineRun.owner_id == user.id
        total = (
            await db.execute(select(func.count()).select_from(PipelineRun).where(base))
        ).scalar() or 0
        query = (
            select(PipelineRun)
            .where(base)
            .order_by(PipelineRun.started_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        runs = list((await db.execute(query)).scalars().all())

        items = []
        for run in runs:
            rid = str(run.id)
            if not ws.path(rid).is_dir():
                items.append(_run_to_dict(run, has_workspace=False, file_count=0))
                continue
            try:
                tree, _ = await asyncio.to_thread(ws.tree_limited, rid, TREE_MAX_ENTRIES)
                items.append(_run_to_dict(run, has_workspace=True, file_count=len(tree)))
            except WorkspaceError:
                items.append(_run_to_dict(run, has_workspace=True, file_count=0))

        return {"items": items, "total": total, "page": page, "limit": limit}


@mcp.tool()
async def get_workspace(run_id: str) -> dict[str, Any]:
    """Obtém o workspace de um run por id (somente se pertencer ao usuário autenticado).

    Retorna a árvore de arquivos do workspace (path, size, binary). Se o
    workspace não existe no disco, ``files`` é vazio.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(run_id)
    ws = WorkspaceManager()

    async with async_session_factory() as db:
        try:
            run = await _get_owned_run(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Workspace não encontrado: {e.error}") from e

        rid = str(run.id)
        files: list[dict[str, Any]] = []
        if ws.path(rid).is_dir():
            try:
                tree, _ = await asyncio.to_thread(ws.tree_limited, rid, TREE_MAX_ENTRIES)
                files = [
                    {"path": f["path"], "size": f["size"], "binary": f["binary"]}
                    for f in tree
                ]
            except WorkspaceError:
                files = []

        status_val = (
            run.status.value if hasattr(run.status, "value") else str(run.status)
        )
        return {
            "id": rid,
            "pipelineId": str(run.pipeline_id),
            "status": status_val,
            "files": files,
        }


@mcp.tool()
async def delete_workspace(run_id: str) -> dict[str, Any]:
    """Remove o workspace (arquivos) de um run (somente se pertencer ao usuário autenticado).

    Remove o diretório de arquivos e o repositório git privado do run. O
    registro do run no banco não é alterado.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(run_id)
    ws = WorkspaceManager()

    async with async_session_factory() as db:
        try:
            run = await _get_owned_run(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Workspace não encontrado: {e.error}") from e

        rid = str(run.id)
        try:
            await asyncio.to_thread(ws.remove, rid)
        except WorkspaceError as e:
            raise ToolError(f"Erro ao remover workspace: {e.message}") from e
        return {"deleted": True, "id": run_id}
