"""Download de artefatos (spec 9.1: GET /api/artifacts/:id).

Dono: rt-executor (FASE 6). O executor grava um Artifact por porta de output
de cada nó (F10); este endpoint devolve o ``Artifact`` com o ``content``.

Convenções (contrato §8): envelope de erro, camelCase.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.db.models import Artifact, User
from app.db.session import get_db

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    """GET /api/artifacts/:id (spec 9.1): devolve o Artifact com content.

    404 ``artifact_not_found`` se não existe ou não é do owner (F4: o
    isolamento vale também para artefatos, mesmo não tendo sido testado
    explicitamente na suíte).
    """
    result = await db.execute(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.owner_id == user.owner_id,
        )
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise AppError(404, "not_found", "artifact_not_found")

    return {
        "id": str(artifact.id),
        "ownerId": str(artifact.owner_id),
        "runId": str(artifact.run_id),
        "nodeId": artifact.node_id,
        "name": artifact.name,
        "type": artifact.type.value if hasattr(artifact.type, "value") else artifact.type,
        "content": artifact.content,
        "size": artifact.size,
        "createdAt": artifact.created_at.isoformat().replace("+00:00", "Z")
        if artifact.created_at
        else None,
    }
