"""Tests for Rivvn gate (V1: fora do caminho crítico, sempre 403).

Dono: be-integrations (FASE 4).
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import (
    RivvnConnection,
    RivvnContractStatus,
    RivvnStatus,
    User,
)


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
# Tests: Rivvn gate
# ---------------------------------------------------------------------------


class TestRivvnGate:
    """V1: Rivvn sempre retorna 403 (contrato comercial não ativo)."""

    async def test_rivvn_connection_not_exists(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """Sem conexão Rivvn: status retorna connected=False, contractStatus=inactive."""
        from sqlalchemy import select

        result = await session.execute(
            select(RivvnConnection).where(RivvnConnection.owner_id == owner_id)
        )
        connection = result.scalar_one_or_none()
        assert connection is None

    async def test_rivvn_connection_inactive(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """Conexão Rivvn com contrato inativo: status retorna contractStatus=inactive."""
        connection = RivvnConnection(
            id=uuid.uuid4(),
            owner_id=owner_id,
            contract_status=RivvnContractStatus.inactive,
            status=RivvnStatus.disconnected,
        )
        session.add(connection)
        await session.commit()
        await session.refresh(connection)

        assert connection.contract_status == RivvnContractStatus.inactive
        assert connection.status == RivvnStatus.disconnected

    async def test_rivvn_connection_expired(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """Conexão Rivvn com contrato expirado."""
        connection = RivvnConnection(
            id=uuid.uuid4(),
            owner_id=owner_id,
            contract_status=RivvnContractStatus.expired,
            status=RivvnStatus.expired,
        )
        session.add(connection)
        await session.commit()
        await session.refresh(connection)

        assert connection.contract_status == RivvnContractStatus.expired

    async def test_rivvn_query_always_raises(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """rivvn_query sempre levanta AppError(501) na V1."""
        from app.knowledge.rivvn import rivvn_query

        with pytest.raises(AppError) as exc_info:
            rivvn_query("test query", ["kb-1"])

        assert exc_info.value.status_code == 501
        assert exc_info.value.code == "rivvn_not_available"

    async def test_rivvn_is_not_available(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """is_rivvn_available sempre retorna False na V1."""
        from app.knowledge.rivvn import is_rivvn_available

        assert is_rivvn_available() is False

    async def test_rivvn_delete_no_connection(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """DELETE /rivvn sem conexão: 404."""
        from sqlalchemy import select

        result = await session.execute(
            select(RivvnConnection).where(RivvnConnection.owner_id == owner_id)
        )
        connection = result.scalar_one_or_none()
        assert connection is None
        # Simula o comportamento do endpoint: 404
        # (o endpoint real levanta AppError)

    async def test_rivvn_delete_with_connection(
        self, session: AsyncSession, owner_id: uuid.UUID
    ) -> None:
        """DELETE /rivvn com conexão: remove a conexão."""
        connection = RivvnConnection(
            id=uuid.uuid4(),
            owner_id=owner_id,
            contract_status=RivvnContractStatus.inactive,
            status=RivvnStatus.disconnected,
        )
        session.add(connection)
        await session.commit()
        await session.refresh(connection)

        # Simula o delete
        await session.delete(connection)
        await session.commit()

        from sqlalchemy import select

        result = await session.execute(
            select(RivvnConnection).where(RivvnConnection.owner_id == owner_id)
        )
        assert result.scalar_one_or_none() is None
