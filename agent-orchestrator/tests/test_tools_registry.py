"""Tests for tools custom registry CRUD.

Dono: be-skills (FASE 4).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import User
from app.tools.registry import ToolRegistry


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    """Cria um usuario de teste no banco."""
    user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        name="Test User",
        password_hash="hashed",
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def owner_id(test_user: User) -> uuid.UUID:
    return test_user.id


VALID_SCRIPT = """
def execute(name: str) -> dict:
    return {"greeting": f"Hello {name}"}
"""

VALID_IO: dict[str, Any] = {
    "inputs": [{"name": "name", "type": "string", "description": "Name", "required": True}],
    "outputs": [{"name": "greeting", "type": "string", "description": "Greeting"}],
}


class TestToolRegistry:
    async def test_create_tool(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        registry = ToolRegistry(session)
        tool = await registry.create(
            owner_id=owner_id,
            name="greet",
            description="Greets someone",
            category="custom",
            script=VALID_SCRIPT,
            io=VALID_IO,
        )
        assert tool.id is not None
        assert tool.name == "greet"
        assert tool.status == "draft"
        assert tool.version == 1

    async def test_create_tool_duplicate_name(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        await registry.create(
            owner_id=owner_id, name="dup", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id, name="dup", description="",
                category="custom", script=VALID_SCRIPT, io=VALID_IO,
            )
        assert exc_info.value.status_code == 409

    async def test_get_tool(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="find-me", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        found = await registry.get(created.id, owner_id)
        assert found.id == created.id
        assert found.name == "find-me"

    async def test_get_tool_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.get(uuid.uuid4(), owner_id)
        assert exc_info.value.status_code == 404

    async def test_list_tools(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        registry = ToolRegistry(session)
        for i in range(3):
            await registry.create(
                owner_id=owner_id, name=f"tool-{i}", description="",
                category="custom", script=VALID_SCRIPT, io=VALID_IO,
            )
        items, total = await registry.list(owner_id)
        assert total == 3
        assert len(items) == 3

    async def test_list_tools_with_status_filter(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        await registry.create(
            owner_id=owner_id, name="draft-tool", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        # Deploy one.
        tool = await registry.list(owner_id)
        await registry.deploy(tool[0][0].id, owner_id)

        items, total = await registry.list(owner_id, status="draft")
        assert total == 0  # All deployed now? No, only one was created.
        # Actually we created 1 and deployed it, so draft count is 0.

    async def test_update_tool(self, session: AsyncSession, owner_id: uuid.UUID) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="update-me", description="old",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        updated = await registry.update(
            tool_id=created.id,
            owner_id=owner_id,
            description="new",
        )
        assert updated.description == "new"

    async def test_update_tool_script_resets_status(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="reset-test", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        # Deploy it.
        await registry.deploy(created.id, owner_id)
        deployed = await registry.get(created.id, owner_id)
        assert deployed.status == "deployed"

        # Update script -> should reset to draft.
        updated = await registry.update(
            tool_id=created.id,
            owner_id=owner_id,
            script="def execute(x: int) -> dict:\n    return {'x': x}\n",
        )
        assert updated.status == "draft"

    async def test_delete_tool_archives(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="archive-me", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        await registry.delete(created.id, owner_id)
        tool = await registry.get(created.id, owner_id)
        assert tool.status == "archived"

    async def test_deploy_valid_tool(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="deploy-me", description="",
            category="custom", script=VALID_SCRIPT, io=VALID_IO,
        )
        deployed = await registry.deploy(created.id, owner_id)
        assert deployed.status == "deployed"
        assert deployed.version == 2

    async def test_deploy_invalid_tool_fails(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = ToolRegistry(session)
        created = await registry.create(
            owner_id=owner_id, name="bad-tool", description="",
            category="custom", script="def wrong():\n    pass\n", io=VALID_IO,
        )
        with pytest.raises(AppError) as exc_info:
            await registry.deploy(created.id, owner_id)
        assert exc_info.value.status_code == 422
