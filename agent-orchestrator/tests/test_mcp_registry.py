"""Tests for MCP registry and validator.

Dono: be-skills (FASE 4).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import User
from app.mcp.registry import MCPRegistry
from app.mcp.validator import validate_mcp_config

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests: Validator
# ---------------------------------------------------------------------------


class TestMCPValidator:
    def test_valid_stdio_config(self) -> None:
        errors = validate_mcp_config(
            transport="stdio",
            command="npx -y @acme/mcp-jira",
            env={"JIRA_TOKEN": "ref:secret-1"},
        )
        assert errors == []

    def test_valid_sse_config(self) -> None:
        errors = validate_mcp_config(
            transport="sse",
            url="https://mcp.example.com/sse",
        )
        assert errors == []

    def test_valid_http_config(self) -> None:
        errors = validate_mcp_config(
            transport="http",
            url="http://localhost:9000/mcp",
        )
        assert errors == []

    def test_stdio_missing_command(self) -> None:
        errors = validate_mcp_config(transport="stdio", command=None)
        assert any("command" in e.lower() for e in errors)

    def test_stdio_empty_command(self) -> None:
        errors = validate_mcp_config(transport="stdio", command="  ")
        assert any("command" in e.lower() for e in errors)

    def test_sse_missing_url(self) -> None:
        errors = validate_mcp_config(transport="sse", url=None)
        assert any("url" in e.lower() for e in errors)

    def test_http_missing_url(self) -> None:
        errors = validate_mcp_config(transport="http", url=None)
        assert any("url" in e.lower() for e in errors)

    def test_invalid_url_scheme(self) -> None:
        errors = validate_mcp_config(transport="http", url="ftp://example.com")
        assert any("http://" in e or "https://" in e for e in errors)

    def test_invalid_transport(self) -> None:
        errors = validate_mcp_config(transport="websocket")
        assert any("transport" in e.lower() for e in errors)

    def test_env_non_string_value(self) -> None:
        errors = validate_mcp_config(
            transport="stdio",
            command="npx test",
            env={"KEY": 123},
        )
        assert any("string" in e.lower() for e in errors)

    def test_command_too_long(self) -> None:
        errors = validate_mcp_config(
            transport="stdio",
            command="x" * 501,
        )
        assert any("500" in e for e in errors)


# ---------------------------------------------------------------------------
# Tests: Registry
# ---------------------------------------------------------------------------


class TestMCPRegistry:
    async def test_create_server(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        server = await registry.create(
            owner_id=owner_id,
            name="jira-mcp",
            description="Jira MCP server",
            transport="stdio",
            command="npx -y @acme/mcp-jira",
            env={"JIRA_TOKEN": "ref:secret-1"},
        )
        assert server.id is not None
        assert server.name == "jira-mcp"
        assert server.transport == "stdio"
        assert server.status == "disconnected"
        assert server.discovered_tools == []

    async def test_create_server_duplicate_name(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        await registry.create(
            owner_id=owner_id,
            name="dup-server",
            description="",
            transport="stdio",
            command="npx test",
        )
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                name="dup-server",
                description="",
                transport="stdio",
                command="npx test",
            )
        assert exc_info.value.status_code == 409

    async def test_get_server(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            name="find-me",
            description="",
            transport="http",
            url="http://localhost:9000",
        )
        found = await registry.get(created.id, owner_id)
        assert found.id == created.id
        assert found.name == "find-me"

    async def test_get_server_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.get(uuid.uuid4(), owner_id)
        assert exc_info.value.status_code == 404

    async def test_get_server_wrong_owner(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            name="private-server",
            description="",
            transport="stdio",
            command="npx test",
        )
        with pytest.raises(AppError):
            await registry.get(created.id, uuid.uuid4())

    async def test_list_servers(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        for i in range(3):
            await registry.create(
                owner_id=owner_id,
                name=f"server-{i}",
                description="",
                transport="stdio",
                command=f"npx test-{i}",
            )
        items, total = await registry.list(owner_id)
        assert total == 3
        assert len(items) == 3

    async def test_list_servers_with_transport_filter(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        await registry.create(
            owner_id=owner_id, name="stdio-srv", description="",
            transport="stdio", command="npx test",
        )
        await registry.create(
            owner_id=owner_id, name="http-srv", description="",
            transport="http", url="http://localhost:9000",
        )
        items, total = await registry.list(owner_id, transport="stdio")
        assert total == 1
        assert items[0].name == "stdio-srv"

    async def test_update_server(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            name="update-me",
            description="old",
            transport="stdio",
            command="npx old",
        )
        updated = await registry.update(
            server_id=created.id,
            owner_id=owner_id,
            description="new",
            command="npx new",
        )
        assert updated.description == "new"
        assert updated.command == "npx new"
        # Status should reset to disconnected.
        assert updated.status == "disconnected"

    async def test_delete_server(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            name="delete-me",
            description="",
            transport="stdio",
            command="npx test",
        )
        await registry.delete(created.id, owner_id)
        with pytest.raises(AppError):
            await registry.get(created.id, owner_id)

    async def test_update_connection_status(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = MCPRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            name="connect-me",
            description="",
            transport="stdio",
            command="npx test",
        )
        tools = [{"name": "search", "description": "Search", "inputSchema": {}}]
        updated = await registry.update_connection_status(
            server_id=created.id,
            owner_id=owner_id,
            status="connected",
            discovered_tools=tools,
        )
        assert updated.status == "connected"
        assert updated.last_connected_at is not None
        assert len(updated.discovered_tools) == 1
        assert updated.discovered_tools[0]["name"] == "search"
