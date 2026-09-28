"""Shared fixtures for API integration tests.

Contains fixtures for test_user, owner_id, test_app, and client that are
reused across multiple test files.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db


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


@pytest_asyncio.fixture
async def test_app(session: AsyncSession, test_user: User):
    """Cria uma app FastAPI de teste com o router de integrações."""
    from app.api.integrations import router as integrations_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(integrations_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield app


@pytest_asyncio.fixture
async def client(test_app):
    """HTTP client para testes de API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
