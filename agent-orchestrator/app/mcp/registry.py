"""MCP servers registry: CRUD operations.

Dono: be-skills (FASE 4). CRUD de servidores MCP no Postgres.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import MCPServer

logger = logging.getLogger(__name__)


class MCPRegistry:
    """CRUD de servidores MCP."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        description: str,
        transport: str,
        command: str | None = None,
        url: str | None = None,
        env: dict[str, Any] | None = None,
    ) -> MCPServer:
        """Registra um servidor MCP."""
        existing = await self._db.execute(
            select(MCPServer).where(MCPServer.owner_id == owner_id, MCPServer.name == name)
        )
        if existing.scalar_one_or_none():
            raise AppError(409, "conflict", "mcp_server_name_exists", {"name": name})

        server = MCPServer(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=name,
            description=description,
            transport=transport,
            command=command,
            url=url,
            env=env or {},
            status="disconnected",
            last_connected_at=None,
            discovered_tools=[],
        )
        self._db.add(server)
        await self._db.commit()
        await self._db.refresh(server)
        return server

    async def get(self, server_id: uuid.UUID, owner_id: uuid.UUID) -> MCPServer:
        """Obtem um servidor MCP por id (validando ownership)."""
        result = await self._db.execute(
            select(MCPServer).where(MCPServer.id == server_id, MCPServer.owner_id == owner_id)
        )
        server = result.scalar_one_or_none()
        if server is None:
            raise AppError(404, "not found", "mcp_server_not_found")
        return server

    async def list(
        self,
        owner_id: uuid.UUID,
        page: int = 1,
        limit: int = 50,
        transport: str | None = None,
        status: str | None = None,
    ) -> tuple[list[MCPServer], int]:
        """Lista servidores MCP do owner com paginacao."""
        query = select(MCPServer).where(MCPServer.owner_id == owner_id)
        count_query = (
            select(func.count())
            .select_from(MCPServer)
            .where(MCPServer.owner_id == owner_id)
        )

        if transport:
            query = query.where(MCPServer.transport == transport)
            count_query = count_query.where(MCPServer.transport == transport)
        if status:
            query = query.where(MCPServer.status == status)
            count_query = count_query.where(MCPServer.status == status)

        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        query = query.order_by(MCPServer.created_at.desc()).offset((page - 1) * limit).limit(limit)
        result = await self._db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def update(
        self,
        server_id: uuid.UUID,
        owner_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        transport: str | None = None,
        command: str | None = None,
        url: str | None = None,
        env: dict[str, Any] | None = None,
    ) -> MCPServer:
        """Atualiza um servidor MCP."""
        server = await self.get(server_id, owner_id)

        if name and name != server.name:
            existing = await self._db.execute(
                select(MCPServer).where(MCPServer.owner_id == owner_id, MCPServer.name == name)
            )
            if existing.scalar_one_or_none():
                raise AppError(409, "conflict", "mcp_server_name_exists", {"name": name})
            server.name = name

        if description is not None:
            server.description = description
        if transport is not None:
            server.transport = transport
        if command is not None:
            server.command = command
        if url is not None:
            server.url = url
        if env is not None:
            server.env = env

        # Reset status se a configuracao de conexao mudou.
        if transport or command or url:
            server.status = "disconnected"
            server.discovered_tools = []

        await self._db.commit()
        await self._db.refresh(server)
        return server

    async def delete(self, server_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        """Remove um servidor MCP."""
        server = await self.get(server_id, owner_id)
        await self._db.delete(server)
        await self._db.commit()

    async def update_connection_status(
        self,
        server_id: uuid.UUID,
        owner_id: uuid.UUID,
        status: str,
        discovered_tools: list[dict[str, Any]] | None = None,
    ) -> MCPServer:
        """Atualiza o status de conexao e as tools descobertas."""
        server = await self.get(server_id, owner_id)
        server.status = status
        if status == "connected":
            server.last_connected_at = datetime.now(UTC)
        if discovered_tools is not None:
            server.discovered_tools = discovered_tools
        await self._db.commit()
        await self._db.refresh(server)
        return server
