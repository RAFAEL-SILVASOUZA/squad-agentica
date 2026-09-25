"""Tests for integrations CRUD (registry + API).

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Integration, User
from app.integrations.registry import IntegrationRegistry


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
# Tests: Registry CRUD
# ---------------------------------------------------------------------------


class TestIntegrationRegistry:
    async def test_create_github_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        integration = await registry.create(
            owner_id=owner_id,
            type="github",
            name="my-github",
            config={"owner": "myorg", "repos": ["repo1", "repo2"]},
        )
        assert integration.id is not None
        assert integration.name == "my-github"
        assert integration.type.value == "github"
        assert integration.status.value == "active"
        assert integration.config["owner"] == "myorg"

    async def test_create_invalid_type(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                type="slack",
                name="my-slack",
                config={},
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_integration_type"

    async def test_create_github_without_owner(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                type="github",
                name="no-owner",
                config={"repos": ["repo1"]},
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_config"

    async def test_create_duplicate_name(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        await registry.create(
            owner_id=owner_id,
            type="github",
            name="dup",
            config={"owner": "org1"},
        )
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                type="github",
                name="dup",
                config={"owner": "org2"},
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "integration_name_exists"

    async def test_get_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            type="github",
            name="find-me",
            config={"owner": "org"},
        )
        found = await registry.get(created.id, owner_id)
        assert found.id == created.id
        assert found.name == "find-me"

    async def test_get_integration_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.get(uuid.uuid4(), owner_id)
        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "integration_not_found"

    async def test_get_integration_wrong_owner(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            type="github",
            name="private",
            config={"owner": "org"},
        )
        other_owner = uuid.uuid4()
        with pytest.raises(AppError) as exc_info:
            await registry.get(created.id, other_owner)
        assert exc_info.value.status_code == 404

    async def test_list_integrations(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        for i in range(3):
            await registry.create(
                owner_id=owner_id,
                type="github",
                name=f"int-{i}",
                config={"owner": f"org{i}"},
            )
        items, total = await registry.list(owner_id)
        assert total == 3
        assert len(items) == 3

    async def test_list_integrations_pagination(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        for i in range(5):
            await registry.create(
                owner_id=owner_id,
                type="github",
                name=f"int-{i}",
                config={"owner": f"org{i}"},
            )
        items, total = await registry.list(owner_id, page=1, limit=2)
        assert total == 5
        assert len(items) == 2

        items, total = await registry.list(owner_id, page=3, limit=2)
        assert total == 5
        assert len(items) == 1

    async def test_update_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            type="github",
            name="update-me",
            config={"owner": "org1"},
        )
        updated = await registry.update(
            integration_id=created.id,
            owner_id=owner_id,
            name="updated-name",
            config={"owner": "org2"},
            status="disabled",
        )
        assert updated.name == "updated-name"
        assert updated.config["owner"] == "org2"
        assert updated.status.value == "disabled"

    async def test_update_integration_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.update(
                integration_id=uuid.uuid4(),
                owner_id=owner_id,
                name="new-name",
            )
        assert exc_info.value.status_code == 404

    async def test_update_duplicate_name(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        await registry.create(
            owner_id=owner_id,
            type="github",
            name="name-a",
            config={"owner": "org1"},
        )
        created_b = await registry.create(
            owner_id=owner_id,
            type="github",
            name="name-b",
            config={"owner": "org2"},
        )
        with pytest.raises(AppError) as exc_info:
            await registry.update(
                integration_id=created_b.id,
                owner_id=owner_id,
                name="name-a",
            )
        assert exc_info.value.status_code == 409

    async def test_delete_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            type="github",
            name="delete-me",
            config={"owner": "org"},
        )
        await registry.delete(created.id, owner_id)
        with pytest.raises(AppError):
            await registry.get(created.id, owner_id)

    async def test_delete_integration_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.delete(uuid.uuid4(), owner_id)
        assert exc_info.value.status_code == 404

    async def test_get_github_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        created = await registry.create(
            owner_id=owner_id,
            type="github",
            name="gh",
            config={"owner": "myorg"},
        )
        found = await registry.get_github_integration(owner_id)
        assert found.id == created.id

    async def test_get_github_integration_not_found(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.get_github_integration(owner_id)
        assert exc_info.value.status_code == 404

    async def test_get_github_integration_disabled(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """Integração GitHub desabilitada não é retornada."""
        registry = IntegrationRegistry(session)
        await registry.create(
            owner_id=owner_id,
            type="github",
            name="gh-disabled",
            config={"owner": "myorg"},
            status="disabled",
        )
        with pytest.raises(AppError) as exc_info:
            await registry.get_github_integration(owner_id)
        assert exc_info.value.status_code == 404
