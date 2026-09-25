"""Async engine, sessionmaker and declarative Base.

Dono do skeleton: infra-docker. O nó db-models preenche ``models.py`` e confirma
o ``Base``/engine. O engine usa a ``DATABASE_URL`` (asyncpg) do contrato §3.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# Engine assíncrono (SQLAlchemy 2 async + asyncpg, contrato §3/§6).
engine = create_async_engine(settings.database_url, pool_pre_ping=True)

# Sessionmaker assíncrono.
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base declarativa de todos os models (db-models)."""


async def get_session() -> AsyncIterator[AsyncSession]:
    """Dependência FastAPI: fornece uma sessão por request."""
    async with async_session_factory() as session:
        yield session
