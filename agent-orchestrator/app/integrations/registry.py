"""Integrations registry: CRUD operations for Integration model.

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Integration, IntegrationStatus, IntegrationType


class IntegrationRegistry:
    """CRUD de integrações por usuário."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list(
        self,
        owner_id: uuid.UUID,
        page: int = 1,
        limit: int = 50,
        type_filter: str | None = None,
    ) -> tuple[list[Integration], int]:
        """Lista integrações do usuário com paginação."""
        query = select(Integration).where(Integration.owner_id == owner_id)
        count_query = select(func.count(Integration.id)).where(
            Integration.owner_id == owner_id
        )

        if type_filter:
            query = query.where(Integration.type == type_filter)
            count_query = count_query.where(Integration.type == type_filter)

        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(Integration.created_at.desc())
        query = query.offset((page - 1) * limit).limit(limit)
        result = await self._db.execute(query)
        items = list(result.scalars().all())

        return items, total

    async def get(self, integration_id: uuid.UUID, owner_id: uuid.UUID) -> Integration:
        """Obtém uma integração por id (validando ownership)."""
        result = await self._db.execute(
            select(Integration).where(
                Integration.id == integration_id,
                Integration.owner_id == owner_id,
            )
        )
        integration = result.scalar_one_or_none()
        if integration is None:
            raise AppError(404, "not found", "integration_not_found")
        return integration

    async def create(
        self,
        owner_id: uuid.UUID,
        type: str,
        name: str,
        config: dict[str, Any],
        status: str = "active",
    ) -> Integration:
        """Cria uma integração.

        V1: apenas type="github" é aceito.
        """
        # Validação de tipo (V1: apenas github)
        valid_types = {"github"}
        if type not in valid_types:
            raise AppError(
                400,
                "validation error",
                "invalid_integration_type",
                {"message": f"Tipo '{type}' não suportado na V1. Use 'github'."},
            )

        # Validação de config para github
        if type == "github":
            if "owner" not in config or not config["owner"]:
                raise AppError(
                    400,
                    "validation error",
                    "invalid_config",
                    {"message": "Config do GitHub deve conter 'owner'."},
                )

        # Verifica nome único por owner
        existing = await self._db.execute(
            select(Integration).where(
                Integration.owner_id == owner_id,
                Integration.name == name,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise AppError(
                409,
                "conflict",
                "integration_name_exists",
                {"message": f"Já existe uma integração com o nome '{name}'."},
            )

        integration = Integration(
            id=uuid.uuid4(),
            owner_id=owner_id,
            type=IntegrationType(type),
            name=name,
            config=config,
            status=IntegrationStatus(status),
        )
        self._db.add(integration)
        await self._db.commit()
        await self._db.refresh(integration)
        return integration

    async def update(
        self,
        integration_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str | None = None,
        config: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> Integration:
        """Atualiza uma integração."""
        integration = await self.get(integration_id, owner_id)

        if name is not None:
            # Verifica nome único (excluindo a própria integração)
            existing = await self._db.execute(
                select(Integration).where(
                    Integration.owner_id == owner_id,
                    Integration.name == name,
                    Integration.id != integration_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise AppError(
                    409,
                    "conflict",
                    "integration_name_exists",
                    {"message": f"Já existe uma integração com o nome '{name}'."},
                )
            integration.name = name

        if config is not None:
            if integration.type == IntegrationType.github:
                if "owner" not in config or not config["owner"]:
                    raise AppError(
                        400,
                        "validation error",
                        "invalid_config",
                        {"message": "Config do GitHub deve conter 'owner'."},
                    )
            integration.config = config

        if status is not None:
            if status not in ("active", "disabled"):
                raise AppError(
                    400,
                    "validation error",
                    "invalid_status",
                    {"message": "Status deve ser 'active' ou 'disabled'."},
                )
            integration.status = IntegrationStatus(status)

        await self._db.commit()
        await self._db.refresh(integration)
        return integration

    async def delete(self, integration_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Remove uma integração."""
        integration = await self.get(integration_id, owner_id)
        await self._db.delete(integration)
        await self._db.commit()

    async def get_github_integration(self, owner_id: uuid.UUID) -> Integration:
        """Obtém a integração GitHub ativa do usuário.

        Raises:
            AppError(404): se não existe integração GitHub ativa.
        """
        result = await self._db.execute(
            select(Integration).where(
                Integration.owner_id == owner_id,
                Integration.type == IntegrationType.github,
                Integration.status == IntegrationStatus.active,
            )
        )
        integration = result.scalars().first()
        if integration is None:
            raise AppError(
                404,
                "not found",
                "integration_not_found",
                {"message": "Nenhuma integração GitHub ativa encontrada."},
            )
        return integration
