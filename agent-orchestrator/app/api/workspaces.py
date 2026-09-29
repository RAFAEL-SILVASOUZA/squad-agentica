"""API de arquivos do run: listagem, conteúdo, diff e zip (Task 8).

Dono: rt-executor (Task 8, 2026-09-28-projeto-git-e-usabilidade). Endpoints:
- GET /api/runs/:runId/files
- GET /api/runs/:runId/files/content?path=
- GET /api/runs/:runId/diff
- GET /api/runs/:runId/archive

Todos exigem que o run pertença ao usuário autenticado (404 ``run_not_found``
caso contrário, via ``get_owned_run`` — mesma verificação de
``app/api/pipeline_runs.py``). Workspace ausente (ex.: já purgado pela
retenção) não é erro para listagem/diff (resposta vazia); ``archive`` exige
que o workspace exista (404 ``workspace_not_found``).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.pipeline_runs import get_owned_run
from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.db.models import Pipeline, User
from app.db.session import get_db
from app.runtime.workspace import (
    TREE_MAX_ENTRIES,
    ArchiveTooLargeError,
    WorkspaceError,
    WorkspaceManager,
    slugify,
    truncate_diff,
)

router = APIRouter(tags=["run-workspace"])

# Revisão final I1: todo I/O de disco (árvore, leitura, zip) roda em thread
# (``asyncio.to_thread``) — nunca no loop de eventos do orchestrator.


@router.get("/runs/{run_id}/files")
async def list_files(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    await get_owned_run(db, run_id, user.owner_id)
    ws = WorkspaceManager()
    rid = str(run_id)
    if not ws.path(rid).is_dir():
        return {"items": [], "truncated": False}

    tree, truncated = await asyncio.to_thread(ws.tree_limited, rid, TREE_MAX_ENTRIES)
    try:
        changed = {c["path"]: c["status"] for c in await ws.changed_files(rid)}
    except WorkspaceError:
        # Status do git indisponível (repositório corrompido etc.): a
        # listagem continua útil sem a coluna de status.
        changed = {}
    items = [
        {
            "path": f["path"],
            "size": f["size"],
            "binary": f["binary"],
            "status": changed.get(f["path"]),
        }
        for f in tree
    ]
    tree_paths = {f["path"] for f in tree}
    for path, status in changed.items():
        if status == "deleted" and path not in tree_paths:
            items.append({"path": path, "size": 0, "binary": False, "status": "deleted"})
    return {"items": items, "truncated": truncated}


@router.get("/runs/{run_id}/files/content")
async def get_file_content(
    run_id: uuid.UUID,
    path: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    await get_owned_run(db, run_id, user.owner_id)
    ws = WorkspaceManager()
    try:
        return await asyncio.to_thread(ws.read_file, str(run_id), path)
    except WorkspaceError as e:
        if "fora do workspace" in e.message:
            raise AppError(400, "validation error", "invalid_path") from e
        raise AppError(404, "not_found", "file_not_found") from e


@router.get("/runs/{run_id}/diff")
async def get_diff(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    await get_owned_run(db, run_id, user.owner_id)
    ws = WorkspaceManager()
    rid = str(run_id)
    if not ws.path(rid).is_dir():
        return {"diff": "", "truncated": False}
    try:
        raw = await ws.diff(rid)
    except WorkspaceError as e:
        raise AppError(409, "conflict", "diff_unavailable", {
            "message": "Não foi possível calcular as alterações do workspace agora. "
                       "Tente de novo em instantes.",
        }) from e
    text, truncated = truncate_diff(raw)
    return {"diff": text, "truncated": truncated}


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


@router.get("/runs/{run_id}/archive", response_model=None)
async def get_archive(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> FileResponse:
    run = await get_owned_run(db, run_id, user.owner_id)
    ws = WorkspaceManager()
    rid = str(run_id)
    if not ws.path(rid).is_dir():
        raise AppError(404, "not_found", "workspace_not_found")

    pipeline_name = (
        await db.execute(select(Pipeline.name).where(Pipeline.id == run.pipeline_id))
    ).scalar_one_or_none() or "run"
    filename = f"{slugify(pipeline_name)}-{run_id.hex[:8]}.zip"
    # Zip num arquivo temporário (não em memória), transmitido pelo
    # FileResponse e apagado depois do envio (BackgroundTask).
    fd, tmp = tempfile.mkstemp(prefix="agent-portal-archive-", suffix=".zip")
    os.close(fd)
    try:
        await asyncio.to_thread(ws.zip_to_file, rid, tmp)
    except ArchiveTooLargeError as e:
        _unlink_quietly(tmp)
        raise AppError(413, "payload too large", "archive_too_large", {
            "message": "O workspace é grande demais para baixar como zip (limite de 200 MB).",
        }) from e
    except BaseException:
        _unlink_quietly(tmp)
        raise
    return FileResponse(
        tmp,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_unlink_quietly, tmp),
    )
