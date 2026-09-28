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

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.pipeline_runs import get_owned_run
from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.db.models import Pipeline, User
from app.db.session import get_db
from app.runtime.workspace import WorkspaceError, WorkspaceManager, slugify, truncate_diff

router = APIRouter(tags=["run-workspace"])


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
        return {"items": []}

    tree = ws.tree(rid)
    changed = {c["path"]: c["status"] for c in await ws.changed_files(rid)}
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
    return {"items": items}


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
        return ws.read_file(str(run_id), path)
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
    text, truncated = truncate_diff(await ws.diff(rid))
    return {"diff": text, "truncated": truncated}


@router.get("/runs/{run_id}/archive")
async def get_archive(
    run_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    run = await get_owned_run(db, run_id, user.owner_id)
    ws = WorkspaceManager()
    rid = str(run_id)
    if not ws.path(rid).is_dir():
        raise AppError(404, "not_found", "workspace_not_found")

    pipeline_name = (
        await db.execute(select(Pipeline.name).where(Pipeline.id == run.pipeline_id))
    ).scalar_one_or_none() or "run"
    filename = f"{slugify(pipeline_name)}-{run_id.hex[:8]}.zip"
    data = ws.zip_bytes(rid)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
