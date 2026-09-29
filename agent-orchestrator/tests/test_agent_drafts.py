"""Tests for persistent agent drafts (Task 3: rascunho persistente).

Cobre:
- Draft sobrevive à recriação do store (persistência no banco)
- Isolamento por dono (draft alheio é invisível; rota responde 404)
- POST /api/agents/chat/restore → 201 {draftId}
- POST /api/agents/validate → {valid, missing, errors}
- purge_expired_drafts remove drafts com updated_at > 24h
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db


@pytest_asyncio.fixture
async def draft_app(session: AsyncSession, test_user: User):
    """App de teste com o router de chat de agentes (DraftStore no banco)."""
    from app.api.agent_chat import router as chat_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(chat_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    yield app


@pytest_asyncio.fixture
async def draft_client(draft_app):
    transport = ASGITransport(app=draft_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# DraftStore (persistência + isolamento)
# ---------------------------------------------------------------------------


async def test_draft_survives_store_recreation(session: AsyncSession, test_user: User):
    from app.agents.chat.conversation import DraftStore

    d = await DraftStore().create(session, str(test_user.id))
    d.config["name"] = "Resumidor"
    await DraftStore().save(session, d)

    again = await DraftStore().get(session, d.draft_id, str(test_user.id))
    assert again is not None
    assert again.config["name"] == "Resumidor"


async def test_draft_of_other_owner_is_invisible(
    session: AsyncSession, test_user: User, other_user: User
):
    from app.agents.chat.conversation import DraftStore

    d = await DraftStore().create(session, str(test_user.id))
    d.config["name"] = "Secret"
    await DraftStore().save(session, d)

    assert await DraftStore().get(session, d.draft_id, str(other_user.id)) is None


async def test_draft_delete(session: AsyncSession, test_user: User):
    from app.agents.chat.conversation import DraftStore

    d = await DraftStore().create(session, str(test_user.id))
    await DraftStore().save(session, d)
    await DraftStore().delete(session, d.draft_id)
    assert await DraftStore().get(session, d.draft_id, str(test_user.id)) is None


async def test_restore_draft_owner_isolation(
    session: AsyncSession, other_user: User, draft_app: FastAPI
):
    """Draft de outro dono não é visível: confirm responde 404."""
    from app.agents.chat.conversation import DraftStore

    d = await DraftStore().create(session, str(other_user.id))
    d.config["name"] = "Outro dono"
    await DraftStore().save(session, d)

    transport = ASGITransport(app=draft_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post(
            "/api/agents/chat/confirm",
            json={"draftId": d.draft_id},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "draft_not_found"


# ---------------------------------------------------------------------------
# Rota: POST /api/agents/chat/restore
# ---------------------------------------------------------------------------


async def test_restore_creates_draft_from_config(draft_client: AsyncClient):
    r = await draft_client.post(
        "/api/agents/chat/restore",
        json={"config": {"name": "X", "prompt": "p"}},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["draftId"]
    # draftId é um UUID válido.
    uuid.UUID(body["draftId"])


async def test_restore_draft_config_roundtrip(
    draft_client: AsyncClient, session: AsyncSession, test_user: User
):
    """O draft restaurado pertence ao usuário e traz a config + mensagens."""
    from app.agents.chat.conversation import DraftStore

    r = await draft_client.post(
        "/api/agents/chat/restore",
        json={
            "config": {"name": "Restaurado", "prompt": "faça X", "actions": ["finalize"]},
            "messages": [{"role": "user", "content": "oi"}],
        },
    )
    assert r.status_code == 201
    draft_id = r.json()["draftId"]

    d = await DraftStore().get(session, draft_id, str(test_user.id))
    assert d is not None
    assert d.config["name"] == "Restaurado"
    assert len(d.messages) == 1
    assert d.messages[0].role == "user"
    assert d.messages[0].content == "oi"


async def test_validate_lists_missing(draft_client: AsyncClient):
    r = await draft_client.post(
        "/api/agents/validate",
        json={"name": "", "outputs": []},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is False
    assert "name" in body["missing"]
    assert isinstance(body["errors"], list)


async def test_validate_valid_config(draft_client: AsyncClient):
    r = await draft_client.post(
        "/api/agents/validate",
        json={
            "name": "Ok",
            "prompt": "p",
            "inputs": [{"name": "a", "type": "document", "required": True}],
            "outputs": [{"name": "b", "type": "code", "required": False}],
            "actions": ["finalize"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["missing"] == []
    assert body["errors"] == []


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------


async def test_expired_drafts_are_purged(session: AsyncSession, test_user: User):
    from sqlalchemy import select

    from app.agents.chat.conversation import DraftStore, purge_expired_drafts
    from app.db.models import AgentDraft

    d = await DraftStore().create(session, str(test_user.id))
    d.config["name"] = "Antigo"
    await DraftStore().save(session, d)
    assert await DraftStore().get(session, d.draft_id, str(test_user.id)) is not None

    # Envelhece o draft: updated_at 25h atrás.
    await session.execute(
        text("UPDATE agent_drafts SET updated_at = now() - interval '25 hours'")
    )
    await session.commit()

    removed = await purge_expired_drafts(session)
    assert removed == 1

    rows = (
        await session.execute(
            select(AgentDraft).where(AgentDraft.id == uuid.UUID(d.draft_id))
        )
    ).scalars().all()
    assert rows == []
