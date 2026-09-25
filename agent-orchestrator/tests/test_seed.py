"""Tests for the admin seed (contrato §0).

Cobertura:
- Cria o admin na primeira execução.
- Idempotente: segunda execução não duplica nem altera.
- Sem ADMIN_EMAIL ou ADMIN_PASSWORD: não cria nada, sai com código 0.
- Não cria nenhum outro registro.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.security import verify_password
from app.db import seed as seed_module
from app.db.models import User


@pytest_asyncio.fixture
async def seed_session(test_engine) -> AsyncIterator[AsyncSession]:
    """Sessão de teste com o schema criado (mesma engine do conftest)."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def seed_factory(test_engine):
    """Factory que aponta para o engine de teste (substitui o de produção)."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    return factory


@pytest.mark.asyncio
async def test_seed_creates_admin(
    seed_session: AsyncSession,
    seed_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Primeira execução cria o admin com hash bcrypt e owner_id == id."""
    monkeypatch.setattr(seed_module.settings, "admin_email", "admin@test.local")
    monkeypatch.setattr(seed_module.settings, "admin_password", "s3cur3-p@ss")
    monkeypatch.setattr(seed_module.settings, "admin_name", "Admin Teste")
    monkeypatch.setattr(seed_module, "async_session_factory", seed_factory)

    await seed_module._seed()

    # O commit do seed já persistiu; usamos uma sessão nova para ver o commit.
    async with seed_factory() as s:
        result = await s.execute(select(User).where(User.email == "admin@test.local"))
        admin = result.scalar_one_or_none()
        assert admin is not None, "Admin não foi criado"
        assert admin.name == "Admin Teste"
        assert admin.owner_id == admin.id, "owner_id deve ser igual ao id (self-referente)"
        assert verify_password("s3cur3-p@ss", admin.password_hash)
        # Não cria nenhum outro registro
        count = await s.execute(select(func.count()).select_from(User))
        assert count.scalar_one() == 1


@pytest.mark.asyncio
async def test_seed_idempotent(
    seed_session: AsyncSession,
    seed_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Segunda execução não duplica nem altera o admin."""
    monkeypatch.setattr(seed_module.settings, "admin_email", "admin@test.local")
    monkeypatch.setattr(seed_module.settings, "admin_password", "s3cur3-p@ss")
    monkeypatch.setattr(seed_module.settings, "admin_name", "Admin Teste")
    monkeypatch.setattr(seed_module, "async_session_factory", seed_factory)

    # Primeira execução
    await seed_module._seed()

    async with seed_factory() as s:
        result = await s.execute(select(User).where(User.email == "admin@test.local"))
        admin = result.scalar_one()
        original_hash = admin.password_hash
        original_id = admin.id

    # Segunda execução (idempotente)
    await seed_module._seed()

    async with seed_factory() as s:
        result = await s.execute(select(User).where(User.email == "admin@test.local"))
        admin2 = result.scalar_one()
        assert admin2.id == original_id, "ID não deve mudar"
        assert admin2.password_hash == original_hash, "Hash não deve mudar"
        count = await s.execute(select(func.count()).select_from(User))
        assert count.scalar_one() == 1, "Não deve duplicar"


@pytest.mark.asyncio
async def test_seed_no_email_creates_nothing(
    seed_session: AsyncSession,
    seed_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem ADMIN_EMAIL: não cria nada, não lança exceção."""
    monkeypatch.setattr(seed_module.settings, "admin_email", "")
    monkeypatch.setattr(seed_module.settings, "admin_password", "s3cur3-p@ss")
    monkeypatch.setattr(seed_module, "async_session_factory", seed_factory)

    await seed_module._seed()  # não deve lançar

    async with seed_factory() as s:
        count = await s.execute(select(func.count()).select_from(User))
        assert count.scalar_one() == 0


@pytest.mark.asyncio
async def test_seed_no_password_creates_nothing(
    seed_session: AsyncSession,
    seed_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sem ADMIN_PASSWORD: não cria nada, não lança exceção."""
    monkeypatch.setattr(seed_module.settings, "admin_email", "admin@test.local")
    monkeypatch.setattr(seed_module.settings, "admin_password", "")
    monkeypatch.setattr(seed_module, "async_session_factory", seed_factory)

    await seed_module._seed()  # não deve lançar

    async with seed_factory() as s:
        count = await s.execute(select(func.count()).select_from(User))
        assert count.scalar_one() == 0


@pytest.mark.asyncio
async def test_seed_default_name(
    seed_session: AsyncSession,
    seed_factory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADMIN_NAME vazio usa o default 'Administrador'."""
    monkeypatch.setattr(seed_module.settings, "admin_email", "admin@test.local")
    monkeypatch.setattr(seed_module.settings, "admin_password", "s3cur3-p@ss")
    monkeypatch.setattr(seed_module.settings, "admin_name", "")
    monkeypatch.setattr(seed_module, "async_session_factory", seed_factory)

    await seed_module._seed()

    async with seed_factory() as s:
        result = await s.execute(select(User).where(User.email == "admin@test.local"))
        admin = result.scalar_one()
        assert admin.name == "Administrador"
