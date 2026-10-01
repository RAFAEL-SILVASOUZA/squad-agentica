from __future__ import annotations

import hashlib
import uuid
from unittest.mock import patch

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db
from app.knowledge.embedder import get_embedder
from app.knowledge.rag import RagService


class Storage:
    def __init__(self):
        self.files = {}

    async def save_document(self, kb_id, doc_id, data, ext=""):
        self.files[f"{kb_id}/{doc_id}.{ext}"] = data

    async def delete_document(self, kb_id, doc_id, ext=""):
        self.files.pop(f"{kb_id}/{doc_id}.{ext}", None)


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    record = User(
        id=uuid.uuid4(), email="knowledge-duplicates@example.test", name="Owner", password_hash="x"
    )
    record.owner_id = record.id
    session.add(record)
    await session.commit()
    return record


@pytest_asyncio.fixture
async def knowledge_client(session, user):
    from app.api.knowledge import router

    storage = Storage()
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api")

    async def db_override():
        yield session

    async def user_override():
        return user

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    with (
        patch("app.api.knowledge._get_storage", return_value=storage),
        patch("app.api.knowledge._get_rag_service", return_value=RagService(get_embedder())),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client, storage


async def _create_kb(client: AsyncClient) -> str:
    response = await client.post(
        "/api/knowledge", json={"name": "Arquivos", "scope": "global", "source": "upload"}
    )
    assert response.status_code == 201
    return response.json()["id"]


class TestKnowledgeDuplicateDocuments:
    async def test_duplicate_upload_returns_conflict_with_existing_document(self, knowledge_client):
        client, _ = knowledge_client
        kb_id = await _create_kb(client)
        first = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("original.txt", b"same body", "text/plain")},
        )
        duplicate = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("copy.txt", b"same body", "text/plain")},
        )
        assert first.status_code == 200
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "duplicate_document"
        assert duplicate.json()["details"] == {
            "documentId": first.json()["documentId"], "name": "original.txt"
        }

    async def test_replace_swaps_document_and_keeps_count(self, knowledge_client):
        client, storage = knowledge_client
        kb_id = await _create_kb(client)
        first = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("old.txt", b"identical", "text/plain")},
        )
        old_id = first.json()["documentId"]
        replaced = await client.post(
            f"/api/knowledge/{kb_id}/upload?replace={old_id}",
            files={"file": ("new.txt", b"identical", "text/plain")},
        )
        docs = await client.get(f"/api/knowledge/{kb_id}/documents")
        base = await client.get(f"/api/knowledge/{kb_id}")
        assert replaced.status_code == 200
        assert replaced.json()["documentId"] != old_id
        assert [doc["id"] for doc in docs.json()["items"]] == [replaced.json()["documentId"]]
        assert base.json()["documentCount"] == 1
        assert len(storage.files) == 1

    async def test_unique_constraint_race_returns_duplicate_conflict(
        self, knowledge_client, session, test_engine, user, monkeypatch
    ):
        from app.db.models import KnowledgeDocument

        client, storage = knowledge_client
        kb_id = await _create_kb(client)
        original_flush = session.flush
        inserted_racer = False
        content_hash = hashlib.sha256(b"concurrent body").hexdigest()

        async def flush_with_racer(*args, **kwargs):
            nonlocal inserted_racer
            if not inserted_racer:
                inserted_racer = True
                factory = async_sessionmaker(
                    test_engine, class_=AsyncSession, expire_on_commit=False
                )
                async with factory() as racer:
                    racer.add(
                        KnowledgeDocument(
                            id=uuid.uuid4(),
                            owner_id=user.id,
                            knowledge_base_id=uuid.UUID(kb_id),
                            name="parallel.txt",
                            source="upload",
                            size=len(b"concurrent body"),
                            content_hash=content_hash,
                            status="ready",
                        )
                    )
                    await racer.commit()
            return await original_flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", flush_with_racer)
        response = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("parallel-copy.txt", b"concurrent body", "text/plain")},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "duplicate_document"
        assert response.json()["details"]["name"] == "parallel.txt"
        assert storage.files == {}

    async def test_replace_failure_preserves_original_document_and_storage(
        self, knowledge_client, monkeypatch, session, user
    ):
        import app.api.knowledge as knowledge_module

        client, storage = knowledge_client
        kb_id = await _create_kb(client)
        original = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("original.txt", b"replace me", "text/plain")},
        )
        original_id = original.json()["documentId"]
        original_key = next(iter(storage.files))

        class FailingRag:
            async def ingest_document(self, db, kb, doc, content, *, commit=True):
                doc.status = "failed"
                if commit:
                    await db.commit()
                raise RuntimeError("embedding failed")

        # Adendo 9: _get_rag_service é async e recebe owner_id; factory mock.
        async def _failing_factory(*_a, **_k):
            return FailingRag()

        monkeypatch.setattr(knowledge_module, "_get_rag_service", _failing_factory)
        response = await client.post(
            f"/api/knowledge/{kb_id}/upload?replace={original_id}",
            files={"file": ("replacement.txt", b"replace me", "text/plain")},
        )
        await session.refresh(user)
        docs = await client.get(f"/api/knowledge/{kb_id}/documents")
        base = await client.get(f"/api/knowledge/{kb_id}")
        assert response.status_code == 500
        assert [doc["id"] for doc in docs.json()["items"]] == [original_id]
        assert docs.json()["items"][0]["status"] == "ready"
        assert base.json()["documentCount"] == 1
        assert set(storage.files) == {original_key}

    async def test_failed_regular_upload_can_be_retried(
        self, knowledge_client, monkeypatch, session, user
    ):
        import app.api.knowledge as knowledge_module

        client, storage = knowledge_client
        kb_id = await _create_kb(client)
        real_factory = knowledge_module._get_rag_service

        class FailingRag:
            async def ingest_document(self, db, kb, doc, content, *, commit=True):
                doc.status = "failed"
                if commit:
                    await db.commit()
                raise RuntimeError("embedding unavailable")

        # Adendo 9: _get_rag_service é async e recebe owner_id; factory mock.
        async def _failing_factory(*_a, **_k):
            return FailingRag()

        monkeypatch.setattr(knowledge_module, "_get_rag_service", _failing_factory)
        failed = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("retry.txt", b"retry after failure", "text/plain")},
        )
        await session.refresh(user)
        assert failed.status_code == 500
        assert storage.files == {}

        monkeypatch.setattr(knowledge_module, "_get_rag_service", real_factory)
        retried = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("retry.txt", b"retry after failure", "text/plain")},
        )
        docs = await client.get(f"/api/knowledge/{kb_id}/documents")
        base = await client.get(f"/api/knowledge/{kb_id}")
        assert retried.status_code == 200, retried.text
        assert docs.json()["total"] == 1
        assert docs.json()["items"][0]["status"] == "ready"
        assert base.json()["documentCount"] == 1
        assert len(storage.files) == 1
