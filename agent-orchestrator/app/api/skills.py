"""Skills CRUD API router.

Dono: be-skills (FASE 4). Rotas (prefixo /api):
- GET /api/skills → 200 {items, total, page, limit}
- POST /api/skills → 201 Skill
- GET /api/skills/{id} → 200 Skill / 404
- PUT /api/skills/{id} → 200 Skill / 404 / 409
- DELETE /api/skills/{id} → 204 / 404
- GET /api/skills/builtins → 200 {items: BuiltinSkill[]}
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.skills.builtins import list_builtin_skills
from app.skills.registry import SkillRegistry
from app.skills.storage import get_skill_storage

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SkillCreateRequest(BaseModel):
    """Body para POST /api/skills."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="")
    category: str = Field(..., pattern="^(code|docs|infra|communication|analysis)$")
    definition: dict[str, Any] = Field(..., description="{'template': str, 'variables': str[]}")
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    required_integrations: list[str] = Field(default_factory=list)


class SkillUpdateRequest(BaseModel):
    """Body para PUT /api/skills/{id}. Todos os campos opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    category: str | None = Field(default=None, pattern="^(code|docs|infra|communication|analysis)$")
    definition: dict[str, Any] | None = None
    inputs: list[dict[str, Any]] | None = None
    outputs: list[dict[str, Any]] | None = None
    required_integrations: list[str] | None = None


class SkillResponse(BaseModel):
    """Response para uma skill."""

    id: uuid.UUID
    name: str
    description: str
    category: str
    type: str
    definition: dict[str, Any]
    inputs: list[Any]
    outputs: list[Any]
    required_integrations: list[str]
    created_at: str
    updated_at: str


class SkillListResponse(BaseModel):
    """Response para listagem de skills."""

    items: list[SkillResponse]
    total: int
    page: int
    limit: int


class BuiltinSkillResponse(BaseModel):
    """Response para uma skill built-in."""

    name: str
    description: str
    category: str
    template: str
    variables: list[str]
    inputs: list[dict[str, Any]]
    outputs: list[dict[str, Any]]
    required_integrations: list[str]


class BuiltinSkillsListResponse(BaseModel):
    """Response para listagem de skills built-in."""

    items: list[BuiltinSkillResponse]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_response(skill: Any) -> SkillResponse:
    """Converte um model Skill em SkillResponse."""
    return SkillResponse(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        category=skill.category,
        type=skill.type,
        definition=skill.definition,
        inputs=skill.inputs,
        outputs=skill.outputs,
        required_integrations=skill.required_integrations,
        created_at=skill.created_at.isoformat() if skill.created_at else "",
        updated_at=skill.updated_at.isoformat() if skill.updated_at else "",
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/builtins", response_model=BuiltinSkillsListResponse)
async def list_builtins() -> BuiltinSkillsListResponse:
    """Lista skills built-in da plataforma."""
    items = [
        BuiltinSkillResponse(
            name=s.name,
            description=s.description,
            category=s.category,
            template=s.template,
            variables=s.variables,
            inputs=s.inputs,
            outputs=s.outputs,
            required_integrations=s.required_integrations,
        )
        for s in list_builtin_skills()
    ]
    return BuiltinSkillsListResponse(items=items)


@router.get("", response_model=SkillListResponse)
async def list_skills(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    category: str | None = Query(default=None),
) -> SkillListResponse:
    """Lista skills do usuario."""
    registry = SkillRegistry(db, get_skill_storage())
    items, total = await registry.list(user.id, page=page, limit=limit, category=category)
    return SkillListResponse(
        items=[_to_response(s) for s in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    body: SkillCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Cria uma skill custom."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.create(
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        definition=body.definition,
        inputs=body.inputs,
        outputs=body.outputs,
        required_integrations=body.required_integrations,
    )
    return _to_response(skill)


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Obtem uma skill por id."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.get(skill_id, user.id)
    return _to_response(skill)


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SkillResponse:
    """Atualiza uma skill."""
    registry = SkillRegistry(db, get_skill_storage())
    skill = await registry.update(
        skill_id=skill_id,
        owner_id=user.id,
        name=body.name,
        description=body.description,
        category=body.category,
        definition=body.definition,
        inputs=body.inputs,
        outputs=body.outputs,
        required_integrations=body.required_integrations,
    )
    return _to_response(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove uma skill."""
    registry = SkillRegistry(db, get_skill_storage())
    await registry.delete(skill_id, user.id)
    return Response(status_code=204)
