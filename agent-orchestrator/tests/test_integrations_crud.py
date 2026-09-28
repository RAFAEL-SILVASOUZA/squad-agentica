"""Tests for integrations CRUD (registry + API).

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Integration
from app.integrations.registry import IntegrationRegistry

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
        assert integration.type == "github"
        assert integration.status == "active"
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
        """GitHub without owner is allowed; routes can validate later."""
        registry = IntegrationRegistry(session)
        integration = await registry.create(
            owner_id=owner_id,
            type="github",
            name="no-owner",
            config={"repos": ["repo1"]},
        )
        assert integration.type == "github"
        assert integration.config == {"repos": ["repo1"]}

    async def test_create_azure_integration(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        integration = await registry.create(
            owner_id=owner_id,
            type="azure",
            name="my-azure",
            config={"organization": "myorg"},
        )
        assert integration.id is not None
        assert integration.name == "my-azure"
        assert integration.type == "azure"
        assert integration.status == "active"
        assert integration.config["organization"] == "myorg"

    async def test_create_azure_without_organization(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        registry = IntegrationRegistry(session)
        with pytest.raises(AppError) as exc_info:
            await registry.create(
                owner_id=owner_id,
                type="azure",
                name="no-org",
                config={},
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "invalid_config"
        assert "organization" in exc_info.value.details["message"]

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
        assert updated.status == "disabled"

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


# ---------------------------------------------------------------------------
# Tests: token criptografado (Fernet) via API
# ---------------------------------------------------------------------------


class TestTokenEncryption:
    async def test_token_is_encrypted_at_rest(
        self, client: AsyncClient, session: AsyncSession, monkeypatch
    ) -> None:
        from cryptography.fernet import Fernet
        from sqlalchemy import select

        from app.core.config import settings

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        r = await client.post(
            "/api/integrations",
            json={
                "type": "github",
                "name": "gh-teste",
                "config": {"owner": "myorg", "token": "ghp_segredo"},
            },
        )
        assert r.status_code == 201
        assert r.json()["config"]["token"] == "***"
        row = (
            await session.execute(select(Integration).where(Integration.name == "gh-teste"))
        ).scalar_one()
        assert "token" not in row.config and "ghp_segredo" not in str(row.config)
        assert row.config["token_encrypted"]

    async def test_legacy_plain_token_is_sealed_on_read(
        self, client: AsyncClient, session: AsyncSession, owner_id: uuid.UUID, monkeypatch
    ) -> None:
        from cryptography.fernet import Fernet

        from app.core.config import settings

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        row = Integration(
            owner_id=owner_id,
            type="github",
            name="legado",
            config={"owner": "myorg", "token": "ghp_velho"},
        )
        session.add(row)
        await session.commit()

        r = await client.get("/api/integrations")
        assert r.status_code == 200

        await session.refresh(row)
        assert "token" not in row.config and row.config["token_encrypted"]

    async def test_legacy_plain_token_is_sealed_on_get_by_id(
        self, client: AsyncClient, session: AsyncSession, owner_id: uuid.UUID, monkeypatch
    ) -> None:
        from cryptography.fernet import Fernet

        from app.core.config import settings

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        row = Integration(
            owner_id=owner_id,
            type="github",
            name="legado-2",
            config={"owner": "myorg", "token": "ghp_velho2"},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)

        r = await client.get(f"/api/integrations/{row.id}")
        assert r.status_code == 200
        assert r.json()["config"]["token"] == "***"

        await session.refresh(row)
        assert "token" not in row.config and row.config["token_encrypted"]

    async def test_update_with_masked_token_keeps_encrypted_value(
        self, client: AsyncClient, session: AsyncSession, monkeypatch
    ) -> None:
        from cryptography.fernet import Fernet
        from sqlalchemy import select

        from app.core.config import settings

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        create = await client.post(
            "/api/integrations",
            json={
                "type": "github",
                "name": "gh-upd",
                "config": {"owner": "myorg", "token": "ghp_original"},
            },
        )
        assert create.status_code == 201
        integration_id = create.json()["id"]

        row = (
            await session.execute(select(Integration).where(Integration.name == "gh-upd"))
        ).scalar_one()
        original_encrypted = row.config["token_encrypted"]

        r = await client.put(
            f"/api/integrations/{integration_id}",
            json={"config": {"owner": "myorg2", "token": "***"}},
        )
        assert r.status_code == 200
        assert r.json()["config"]["token"] == "***"
        assert r.json()["config"]["owner"] == "myorg2"

        await session.refresh(row)
        assert row.config["token_encrypted"] == original_encrypted
        assert "token" not in row.config

    async def test_update_with_new_token_reencrypts(
        self, client: AsyncClient, session: AsyncSession, monkeypatch
    ) -> None:
        from cryptography.fernet import Fernet
        from sqlalchemy import select

        from app.core.config import settings
        from app.core.secrets import decrypt_secret

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        create = await client.post(
            "/api/integrations",
            json={
                "type": "github",
                "name": "gh-upd2",
                "config": {"owner": "myorg", "token": "ghp_original"},
            },
        )
        integration_id = create.json()["id"]

        r = await client.put(
            f"/api/integrations/{integration_id}",
            json={"config": {"owner": "myorg", "token": "ghp_novo"}},
        )
        assert r.status_code == 200
        assert r.json()["config"]["token"] == "***"

        row = (
            await session.execute(select(Integration).where(Integration.name == "gh-upd2"))
        ).scalar_one()
        assert decrypt_secret(row.config["token_encrypted"]) == "ghp_novo"

    async def test_create_with_token_and_missing_key_returns_500(
        self, client: AsyncClient, monkeypatch
    ) -> None:
        from app.core.config import settings

        monkeypatch.setattr(settings, "integrations_secret_key", "")
        r = await client.post(
            "/api/integrations",
            json={
                "type": "github",
                "name": "gh-nokey",
                "config": {"owner": "myorg", "token": "ghp_x"},
            },
        )
        assert r.status_code == 500
        assert r.json()["code"] == "secret_key_missing"


class TestGetIntegrationToken:
    def test_get_integration_token_decrypts(self, monkeypatch) -> None:
        from cryptography.fernet import Fernet

        from app.api.integrations import get_integration_token
        from app.core.config import settings
        from app.core.secrets import encrypt_secret

        monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
        integration = Integration(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            type="github",
            name="x",
            config={"token_encrypted": encrypt_secret("ghp_plain")},
            status="active",
        )
        assert get_integration_token(integration) == "ghp_plain"

    def test_get_integration_token_plain_fallback(self) -> None:
        from app.api.integrations import get_integration_token

        integration = Integration(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            type="github",
            name="x",
            config={"token": "ghp_plain"},
            status="active",
        )
        assert get_integration_token(integration) == "ghp_plain"
