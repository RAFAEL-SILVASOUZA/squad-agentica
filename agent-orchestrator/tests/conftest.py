"""Fixtures de banco de teste isolado (contrato §4 / protocolo comum §5).

Cada sessão de pytest cria um banco próprio ``agent_portal_test_<uuid>`` e o
destrói no teardown. O fixture usa o mesmo ``DATABASE_URL`` base mudando apenas
o nome do banco; o usuário ``agent_portal`` tem ``CREATEDB`` (postgres/init.sql).
Nunca usa o banco ``agent_portal``.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator
from urllib.parse import urlparse, urlunparse

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import Base


def _test_database_url() -> str:
    """DATABASE_URL do banco de teste isolado (mesmo host/credenciais, banco novo)."""
    parsed = urlparse(settings.database_url)
    db_name = f"agent_portal_test_{uuid.uuid4().hex[:12]}"
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def _asyncpg_url(url: str) -> str:
    """Converte ``postgresql+asyncpg://`` em ``postgresql://`` para o driver asyncpg."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _test_database_url()


@pytest_asyncio.fixture(scope="function")
async def test_engine(test_database_url: str):
    """Cria o banco de teste, o schema (create_all) e o engine async.

    Teardown: drop do schema, drop do banco, dispose do engine.
    """
    # Cria o banco (fora de transação: CREATE DATABASE não transaciona).
    # Conecta no banco de aplicação (que existe) para criar o banco de teste.
    admin_url = _asyncpg_url(settings.database_url)
    db_match = re.search(r"/(agent_portal_test_[a-f0-9]+)$", test_database_url)
    db_name = db_match.group(1) if db_match else "agent_portal_test_unknown"
    conn = await asyncpg.connect(admin_url)
    await conn.execute(f'CREATE DATABASE "{db_name}"')
    await conn.close()

    engine = create_async_engine(test_database_url, pool_pre_ping=True)
    # A extensão vector vem do postgres/init.sql (infra-postgres); o banco de
    # teste é criado do zero, então habilitamos aqui (idempotente).
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

    conn = await asyncpg.connect(_asyncpg_url(admin_url))
    await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
    await conn.close()


@pytest_asyncio.fixture
async def session(test_engine) -> AsyncIterator[AsyncSession]:
    """Sessão por teste (commit no fim, rollback em falha)."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()


# Import shared API fixtures so pytest can discover them from integration_api_fixtures
from tests.integration_api_fixtures import client, owner_id, test_app, test_user  # noqa: F401
