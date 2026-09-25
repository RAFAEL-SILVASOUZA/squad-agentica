"""Skills registry: CRUD operations with Garage storage sync.

Dono: be-skills (FASE 4). Cada operacao de CRUD faz DUAS coisas:
(a) operacao no Postgres (metadados), (b) operacao no Garage (conteudo .md).

Estrategia de consistencia:
- Create: PUT no Garage -> INSERT no Postgres. Se o INSERT falhar, DELETE no Garage.
- Update: PUT no Garage -> UPDATE no Postgres. Se o UPDATE falhar, o conteudo
  novo ja esta no Garage mas o Postgres ainda aponta para o antigo (idempotente).
- Delete: DELETE no Garage -> DELETE no Postgres. Se o DELETE no Garage falhar,
  o Postgres nao e tocado.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Skill
from app.skills.storage import SkillStorage

logger = logging.getLogger(__name__)


class SkillRegistry:
    """CRUD de skills com sincronizacao Postgres + Garage."""

    def __init__(self, db: AsyncSession, storage: SkillStorage) -> None:
        self._db = db
        self._storage = storage

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        description: str,
        category: str,
        definition: dict[str, Any],
        inputs: list[Any] | None = None,
        outputs: list[Any] | None = None,
        required_integrations: list[str] | None = None,
    ) -> Skill:
        """Cria uma skill: PUT no Garage + INSERT no Postgres."""
        # Verifica unicidade de nome por owner.
        existing = await self._db.execute(
            select(Skill).where(Skill.owner_id == owner_id, Skill.name == name)
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "conflict", "skill_name_exists", {"name": name})

        skill = Skill(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            category=category,
            type="prompt",
            definition=definition,
            inputs=inputs or [],
            outputs=outputs or [],
            required_integrations=required_integrations or [],
        )

        # PUT no Garage primeiro.
        content_md = definition.get("template", "")
        await self._storage.save_skill(str(skill.id), content_md)

        try:
            self._db.add(skill)
            await self._db.commit()
            await self._db.refresh(skill)
        except Exception:
            # Compensacao: remove o artefato orfa do Garage.
            try:
                await self._storage.delete_skill(str(skill.id))
            except Exception:
                logger.warning("Failed to compensate Garage delete for skill %s", skill.id)
            raise

        return skill

    async def get(self, skill_id: uuid.UUID, owner_id: uuid.UUID) -> Skill:
        """Obtem uma skill por id (validando ownership)."""
        result = await self._db.execute(
            select(Skill).where(Skill.id == skill_id, Skill.owner_id == owner_id)
        )
        skill = result.scalar_one_or_none()
        if skill is None:
            raise AppError(404, "not found", "skill_not_found")
        return skill

    async def list(
        self,
        owner_id: uuid.UUID,
        page: int = 1,
        limit: int = 50,
        category: str | None = None,
    ) -> tuple[list[Skill], int]:
        """Lista skills do owner com paginacao."""
        query = select(Skill).where(Skill.owner_id == owner_id)
        count_query = select(func.count()).select_from(Skill).where(Skill.owner_id == owner_id)

        if category:
            query = query.where(Skill.category == category)
            count_query = count_query.where(Skill.category == category)

        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Skill.created_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await self._db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def update(
        self,
        skill_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        definition: dict[str, Any] | None = None,
        inputs: list[Any] | None = None,
        outputs: list[Any] | None = None,
        required_integrations: list[str] | None = None,
    ) -> Skill:
        """Atualiza uma skill: PUT no Garage + UPDATE no Postgres."""
        skill = await self.get(skill_id, owner_id)

        # Se o nome mudou, verifica unicidade.
        if name and name != skill.name:
            existing = await self._db.execute(
                select(Skill).where(Skill.owner_id == owner_id, Skill.name == name)
            )
            if existing.scalar_one_or_none():
                raise AppError(409, "conflict", "skill_name_exists", {"name": name})
            skill.name = name

        if description is not None:
            skill.description = description
        if category is not None:
            skill.category = category
        if inputs is not None:
            skill.inputs = inputs
        if outputs is not None:
            skill.outputs = outputs
        if required_integrations is not None:
            skill.required_integrations = required_integrations

        # Se a definicao mudou, atualiza o conteudo no Garage.
        if definition is not None:
            skill.definition = definition
            content_md = definition.get("template", "")
            await self._storage.save_skill(str(skill.id), content_md)

        await self._db.commit()
        await self._db.refresh(skill)
        return skill

    async def delete(self, skill_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Remove uma skill: DELETE no Garage + DELETE no Postgres."""
        skill = await self.get(skill_id, owner_id)

        # DELETE no Garage primeiro.
        await self._storage.delete_skill(str(skill.id))

        await self._db.delete(skill)
        await self._db.commit()

    async def get_content(self, skill_id: uuid.UUID) -> str:
        """Baixa o conteudo .md da skill do Garage."""
        return await self._storage.get_skill(str(skill_id))
