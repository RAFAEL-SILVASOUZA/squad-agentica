"""Tests for skills registry, storage, and builtins.

Dono: be-skills (FASE 4).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Skill, User
from app.skills.builtins import BUILTIN_SKILLS, get_builtin_skill, list_builtin_skills
from app.skills.registry import SkillRegistry
from app.skills.storage import SkillStorage

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_storage() -> AsyncMock:
    """Mock do SkillStorage."""
    storage = AsyncMock(spec=SkillStorage)
    storage.save_skill = AsyncMock()
    storage.get_skill = AsyncMock(return_value="# Test Skill\n\nContent here.")
    storage.delete_skill = AsyncMock()
    return storage


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
# Tests: Builtins
# ---------------------------------------------------------------------------


class TestBuiltinSkills:
    def test_list_builtin_skills(self) -> None:
        skills = list_builtin_skills()
        assert len(skills) == 6
        names = [s.name for s in skills]
        assert "code-gen" in names
        assert "test-runner" in names
        assert "security-scanner" in names
        assert "doc-writer" in names
        assert "api-client" in names
        assert "deploy-runner" in names

    def test_get_builtin_skill(self) -> None:
        skill = get_builtin_skill("code-gen")
        assert skill is not None
        assert skill.name == "code-gen"
        assert skill.category == "code"
        assert "task" in skill.variables

    def test_get_builtin_skill_not_found(self) -> None:
        assert get_builtin_skill("nonexistent") is None

    def test_builtin_skill_has_template(self) -> None:
        for skill in BUILTIN_SKILLS:
            assert skill.template, f"Skill {skill.name} has empty template"
            assert len(skill.variables) > 0, f"Skill {skill.name} has no variables"


# ---------------------------------------------------------------------------
# Tests: Registry
# ---------------------------------------------------------------------------


class TestSkillRegistry:
    async def test_create_skill(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        skill = await registry.create(
            owner_id=owner_id,
            name="test-skill",
            description="A test skill",
            category="code",
            definition={"template": "Hello {name}", "variables": ["name"]},
        )
        assert skill.id is not None
        assert skill.name == "test-skill"
        assert skill.category == "code"
        assert skill.type == "prompt"
        mock_storage.save_skill.assert_called_once()

    async def test_create_skill_duplicate_name(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        await registry.create(
            owner_id=owner_id,
            name="dup-skill",
            description="",
            category="code",
            definition={"template": "x", "variables": []},
        )
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                name="dup-skill",
                description="",
                category="code",
                definition={"template": "x", "variables": []},
            )
        assert exc_info.value.status_code == 409

    async def test_get_skill(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        created = await registry.create(
            owner_id=owner_id,
            name="find-me",
            description="",
            category="docs",
            definition={"template": "x", "variables": []},
        )
        found = await registry.get(created.id, owner_id)
        assert found.id == created.id
        assert found.name == "find-me"

    async def test_get_skill_not_found(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        with pytest.raises(AppError) as exc_info:
            await registry.get(uuid.uuid4(), owner_id)
        assert exc_info.value.status_code == 404

    async def test_get_skill_wrong_owner(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        created = await registry.create(
            owner_id=owner_id,
            name="private-skill",
            description="",
            category="code",
            definition={"template": "x", "variables": []},
        )
        other_owner = uuid.uuid4()
        with pytest.raises(AppError) as exc_info:
            await registry.get(created.id, other_owner)
        assert exc_info.value.status_code == 404

    async def test_list_skills(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        for i in range(3):
            await registry.create(
                owner_id=owner_id,
                name=f"skill-{i}",
                description="",
                category="code",
                definition={"template": "x", "variables": []},
            )
        items, total = await registry.list(owner_id)
        assert total == 3
        assert len(items) == 3

    async def test_list_skills_with_category_filter(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        await registry.create(
            owner_id=owner_id, name="a", description="", category="code",
            definition={"template": "x", "variables": []},
        )
        await registry.create(
            owner_id=owner_id, name="b", description="", category="docs",
            definition={"template": "x", "variables": []},
        )
        items, total = await registry.list(owner_id, category="code")
        assert total == 1
        assert items[0].name == "a"

    async def test_update_skill(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        created = await registry.create(
            owner_id=owner_id,
            name="update-me",
            description="old",
            category="code",
            definition={"template": "old", "variables": []},
        )
        updated = await registry.update(
            skill_id=created.id,
            owner_id=owner_id,
            description="new",
            definition={"template": "new {x}", "variables": ["x"]},
        )
        assert updated.description == "new"
        assert updated.definition["template"] == "new {x}"
        # Storage should have been called again for the new content.
        assert mock_storage.save_skill.call_count == 2

    async def test_delete_skill(
        self, session: AsyncSession, mock_storage: AsyncMock, owner_id: uuid.UUID
    ) -> None:
        registry = SkillRegistry(session, mock_storage)
        created = await registry.create(
            owner_id=owner_id,
            name="delete-me",
            description="",
            category="code",
            definition={"template": "x", "variables": []},
        )
        await registry.delete(created.id, owner_id)
        mock_storage.delete_skill.assert_called_once_with(str(created.id))

        with pytest.raises(AppError):
            await registry.get(created.id, owner_id)

    async def test_create_skill_storage_failure_compensates(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """Se o Garage falhar no create, nao ha INSERT no Postgres."""
        failing_storage = AsyncMock(spec=SkillStorage)
        failing_storage.save_skill = AsyncMock(side_effect=Exception("Garage down"))
        failing_storage.delete_skill = AsyncMock()

        registry = SkillRegistry(session, failing_storage)
        with pytest.raises(Exception, match="Garage down"):
            await registry.create(
                owner_id=owner_id,
                name="will-fail",
                description="",
                category="code",
                definition={"template": "x", "variables": []},
            )
        # Nao deve ter INSERT no Postgres.
        from sqlalchemy import select
        result = await session.execute(select(Skill).where(Skill.name == "will-fail"))
        assert result.scalar_one_or_none() is None
