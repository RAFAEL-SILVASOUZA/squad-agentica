"""Tools custom registry: CRUD operations.

Dono: be-skills (FASE 4). CRUD de tools custom no Postgres.
O conteudo do script fica no campo `script` do model CustomTool.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import CustomTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """CRUD de tools custom."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        description: str,
        category: str,
        script: str,
        io: dict[str, Any],
    ) -> CustomTool:
        """Cria uma tool custom (status=draft)."""
        existing = await self._db.execute(
            select(CustomTool).where(CustomTool.owner_id == owner_id, CustomTool.name == name)
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "conflict", "tool_name_exists", {"name": name})

        tool = CustomTool(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            category=category,
            script=script,
            io=io,
            version=1,
            status="draft",
        )
        self._db.add(tool)
        await self._db.commit()
        await self._db.refresh(tool)
        return tool

    async def get(self, tool_id: uuid.UUID, owner_id: uuid.UUID) -> CustomTool:
        """Obtem uma tool por id (validando ownership)."""
        result = await self._db.execute(
            select(CustomTool).where(CustomTool.id == tool_id, CustomTool.owner_id == owner_id)
        )
        tool = result.scalar_one_or_none()
        if tool is None:
            raise AppError(404, "not found", "tool_not_found")
        return tool

    async def list(
        self,
        owner_id: uuid.UUID,
        page: int = 1,
        limit: int = 50,
        status: str | None = None,
        category: str | None = None,
    ) -> tuple[list[CustomTool], int]:
        """Lista tools do owner com paginacao."""
        query = select(CustomTool).where(CustomTool.owner_id == owner_id)
        count_query = (
            select(func.count())
            .select_from(CustomTool)
            .where(CustomTool.owner_id == owner_id)
        )

        if status:
            query = query.where(CustomTool.status == status)
            count_query = count_query.where(CustomTool.status == status)
        if category:
            query = query.where(CustomTool.category == category)
            count_query = count_query.where(CustomTool.category == category)

        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(CustomTool.created_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await self._db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def update(
        self,
        tool_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        category: str | None = None,
        script: str | None = None,
        io: dict[str, Any] | None = None,
    ) -> CustomTool:
        """Atualiza uma tool custom."""
        tool = await self.get(tool_id, owner_id)

        if name and name != tool.name:
            existing = await self._db.execute(
                select(CustomTool).where(CustomTool.owner_id == owner_id, CustomTool.name == name)
            )
            if existing.scalar_one_or_none():
                raise AppError(409, "conflict", "tool_name_exists", {"name": name})
            tool.name = name

        if description is not None:
            tool.description = description
        if category is not None:
            tool.category = category
        if script is not None:
            tool.script = script
        if io is not None:
            tool.io = io

        # Reset status para draft se o script mudou.
        if script is not None and tool.status == "deployed":
            tool.status = "draft"

        await self._db.commit()
        await self._db.refresh(tool)
        return tool

    async def delete(self, tool_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Arquiva uma tool (soft delete)."""
        tool = await self.get(tool_id, owner_id)
        tool.status = "archived"
        await self._db.commit()

    async def deploy(self, tool_id: uuid.UUID, owner_id: uuid.UUID) -> CustomTool:
        """Deploy: valida e marca como deployed."""
        from app.tools.validator import validate_tool

        tool = await self.get(tool_id, owner_id)
        errors = validate_tool(tool.script, tool.io)
        if errors:
            raise AppError(422, "validation failed", "tool_validation_failed", {"errors": errors})

        tool.status = "deployed"
        tool.version += 1
        await self._db.commit()
        await self._db.refresh(tool)
        return tool
