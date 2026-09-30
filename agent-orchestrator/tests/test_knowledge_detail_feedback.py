"""Tests for document detail (GET) and source feedback (PATCH) endpoints.

Cobre:
- GET /api/knowledge/{kb_id}/documents/{doc_id} → detail com preview
- GET 404 para documento de outro owner
- PATCH /api/knowledge/{kb_id}/conversations/{cid}/messages/{mid}/sources/{index}
- PATCH 422 para índice fora de range
- PATCH 422 para mensagem de usuário (não assistant)
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeConversation,
    KnowledgeDocument,
    KnowledgeMessage,
    User,
)
from app.db.session import get_db
from app.knowledge.embedder import get_embedder
from app.knowledge.rag import RagService


class MockKnowledgeStorage:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}

    async def save_document(self, kb_id, doc_id, data, ext=""):
        self.store[f"{kb_id}/{doc_id}.{ext}"] = data
        return f"{kb_id}/{doc_id}.{ext}"

    async def get_document(self, kb_id, doc_id, ext=""):
        key = f"{kb_id}/{doc_id}.{ext}"
        if key not in self.store:
            raise FileNotFoundError(key)
        return self.store[key]

    async def delete_document(self, kb_id, doc_id, ext=""):
        self.store.pop(f"{kb_id}/{doc_id}.{ext}", None)


@pytest_asyncio.fixture
async def test_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(), email="detail-fb@example.com", name="Detail FB User", password_hash="h"
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_user(session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(), email="other-detail-fb@example.com", name="Other Detail FB", password_hash="h"
    )
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def mock_storage() -> MockKnowledgeStorage:
    return MockKnowledgeStorage()


@pytest_asyncio.fixture(autouse=True)
async def clean_knowledge(session: AsyncSession):
    """Limpa dados de knowledge entre testes."""
    from sqlalchemy import delete as sa_delete

    await session.execute(sa_delete(KnowledgeChunk))
    await session.execute(sa_delete(KnowledgeDocument))
    await session.execute(sa_delete(KnowledgeBase))
    await session.commit()
    yield


@pytest_asyncio.fixture
async def test_app(session, test_user, mock_storage):
    from app.api.knowledge import router as knowledge_router

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(knowledge_router, prefix="/api")

    async def override_get_db():
        yield session

    async def override_get_current_user():
        return test_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with (
        patch("app.api.knowledge._get_storage", return_value=mock_storage),
        patch(
            "app.api.knowledge._get_rag_service",
            return_value=RagService(embedder=get_embedder()),
        ),
    ):
        yield app


@pytest_asyncio.fixture
async def client(test_app):
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def client_other_user(test_app, other_user):
    """Client autenticado como outro usuário."""
    from app.auth.dependencies import get_current_user as gcu

    async def override_other():
        return other_user

    test_app.dependency_overrides[gcu] = override_other
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _create_kb(client: AsyncClient, name: str = "TestKB") -> str:
    resp = await client.post(
        "/api/knowledge", json={"name": name, "scope": "global", "source": "upload"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_doc_with_chunks(
    session: AsyncSession, kb_id: str, user_id: uuid.UUID, num_chunks: int = 3
) -> str:
    """Cria um documento + chunks diretamente no banco (sem upload)."""
    from datetime import UTC, datetime

    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        owner_id=user_id,
        knowledge_base_id=uuid.UUID(kb_id),
        name="test-doc.txt",
        source="upload",
        url=None,
        size=1024,
        content_hash=None,
        chunk_count=num_chunks,
        status="ready",
    )
    session.add(doc)
    await session.flush()

    for i in range(num_chunks):
        chunk = KnowledgeChunk(
            id=uuid.uuid4(),
            owner_id=user_id,
            knowledge_base_id=uuid.UUID(kb_id),
            document_id=doc.id,
            chunk_index=i,
            content=f"Chunk {i} content " + "x" * 700,  # > 600 chars to test truncation
            embedding=[0.0] * 1536,
        )
        session.add(chunk)

    await session.commit()
    await session.refresh(doc)
    return str(doc.id)


async def _create_conversation_with_assistant_message(
    session: AsyncSession, kb_id: str, user_id: uuid.UUID
) -> tuple[str, str]:
    """Cria uma conversa + mensagem assistant com sources. Retorna (conv_id, msg_id)."""
    from datetime import UTC, datetime

    conversation = KnowledgeConversation(
        id=uuid.uuid4(),
        owner_id=user_id,
        knowledge_base_id=uuid.UUID(kb_id),
        title="Test conversation",
    )
    session.add(conversation)
    await session.flush()

    message = KnowledgeMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content="Resposta com fontes.",
        sources=[
            {"documentId": str(uuid.uuid4()), "documentName": "doc.txt", "chunkId": "c1", "text": "trecho", "score": 0.9},
            {"documentId": str(uuid.uuid4()), "documentName": "doc2.txt", "chunkId": "c2", "text": "trecho2", "score": 0.8},
        ],
        created_at=datetime.now(UTC),
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return str(conversation.id), str(message.id)


async def _create_user_message(
    session: AsyncSession, kb_id: str, user_id: uuid.UUID
) -> tuple[str, str]:
    """Cria uma conversa + mensagem user. Retorna (conv_id, msg_id)."""
    from datetime import UTC, datetime

    conversation = KnowledgeConversation(
        id=uuid.uuid4(),
        owner_id=user_id,
        knowledge_base_id=uuid.UUID(kb_id),
        title="User msg test",
    )
    session.add(conversation)
    await session.flush()

    message = KnowledgeMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="user",
        content="Pergunta do usuário.",
        sources=[],
        created_at=datetime.now(UTC),
    )
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return str(conversation.id), str(message.id)


class TestDocumentDetail:
    async def test_document_detail(self, client: AsyncClient, session: AsyncSession, test_user: User):
        kb_id = await _create_kb(client)
        doc_id = await _create_doc_with_chunks(session, kb_id, test_user.id, num_chunks=3)

        resp = await client.get(f"/api/knowledge/{kb_id}/documents/{doc_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == doc_id
        assert data["name"] == "test-doc.txt"
        assert data["size"] == 1024
        assert data["status"] == "ready"
        assert data["chunkCount"] == 3
        assert "createdAt" in data
        # Preview: first 3 chunks, each truncated to 600 chars
        assert "preview" in data
        assert len(data["preview"]) == 3
        for i, chunk_text in enumerate(data["preview"]):
            assert len(chunk_text) <= 600
            assert chunk_text.startswith(f"Chunk {i} content")

    async def test_document_detail_404_other_user(
        self,
        client: AsyncClient,
        session: AsyncSession,
        test_user: User,
        other_user: User,
    ):
        kb_id = await _create_kb(client)
        doc_id = await _create_doc_with_chunks(session, kb_id, test_user.id, num_chunks=1)

        # Outro usuário não acessa: testa via _get_kb diretamente (mesmo
        # padrão de test_knowledge_crud.py).
        from app.api.knowledge import _get_kb
        from app.core.errors import AppError

        with pytest.raises(AppError) as exc:
            await _get_kb(session, other_user.id, uuid.UUID(kb_id))
        assert exc.value.code == "knowledge_base_not_found"

    async def test_document_detail_404_not_found(self, client: AsyncClient):
        kb_id = await _create_kb(client)
        resp = await client.get(f"/api/knowledge/{kb_id}/documents/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestFeedback:
    async def test_feedback_patch(self, client: AsyncClient, session: AsyncSession, test_user: User):
        kb_id = await _create_kb(client)
        conv_id, msg_id = await _create_conversation_with_assistant_message(
            session, kb_id, test_user.id
        )

        resp = await client.patch(
            f"/api/knowledge/{kb_id}/conversations/{conv_id}/messages/{msg_id}/sources/0",
            json={"wrong": True},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "feedback" in data
        feedback = data["feedback"]
        assert "sources" in feedback
        assert "0" in feedback["sources"]
        assert feedback["sources"]["0"]["wrong"] is True
        assert "at" in feedback["sources"]["0"]

        # Verifica no banco
        from sqlalchemy import select

        msg = (
            await session.execute(
                select(KnowledgeMessage).where(KnowledgeMessage.id == uuid.UUID(msg_id))
            )
        ).scalar_one()
        assert msg.feedback is not None
        assert msg.feedback["sources"]["0"]["wrong"] is True

    async def test_feedback_invalid_index(self, client: AsyncClient, session: AsyncSession, test_user: User):
        kb_id = await _create_kb(client)
        conv_id, msg_id = await _create_conversation_with_assistant_message(
            session, kb_id, test_user.id
        )

        # Índice 5 fora de range (só tem 2 sources: 0 e 1)
        resp = await client.patch(
            f"/api/knowledge/{kb_id}/conversations/{conv_id}/messages/{msg_id}/sources/5",
            json={"wrong": True},
        )
        assert resp.status_code == 422

    async def test_feedback_on_user_message(self, client: AsyncClient, session: AsyncSession, test_user: User):
        kb_id = await _create_kb(client)
        conv_id, msg_id = await _create_user_message(session, kb_id, test_user.id)

        resp = await client.patch(
            f"/api/knowledge/{kb_id}/conversations/{conv_id}/messages/{msg_id}/sources/0",
            json={"wrong": True},
        )
        assert resp.status_code == 422
