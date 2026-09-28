"""Tests for the knowledge API router (D9 9.5, spec 9.3).

Cobre: CRUD de KB, upload (multipart) com indexação, listagem de documentos,
removal, query semântica, rate limiting de upload (10/min por KB), validação
de tipo/tamanho e isolamento por owner.
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
from app.db.models import User
from app.db.session import get_db
from app.knowledge.embedder import get_embedder
from app.knowledge.rag import RagService


class MockKnowledgeStorage:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.fail_on_save = False

    async def save_document(self, kb_id, doc_id, data, ext=""):
        if self.fail_on_save:
            raise ConnectionError("Garage unavailable")
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
    user = User(id=uuid.uuid4(), email="kb@example.com", name="KB User", password_hash="h")
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def second_user(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email="kb2@example.com", name="KB User2", password_hash="h")
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def mock_storage() -> MockKnowledgeStorage:
    return MockKnowledgeStorage()


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiter():
    """Reseta o rate limiter de upload entre testes (in-memory, module-level)."""
    from app.api.knowledge import _upload_rate_limiter

    _upload_rate_limiter.cleanup()
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_knowledge(session: AsyncSession):
    """Limpa dados de knowledge entre testes.

    O service faz commit (não rollback), então dados persistem na sessão
    compartilhada. Limpa chunks, documentos e KBs antes de cada teste.
    """
    from sqlalchemy import delete as sa_delete

    from app.db.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument

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

    # Injeta mock storage + embedder mock no service.
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


class TestCreateKB:
    async def test_create_kb(self, client: AsyncClient):
        resp = await client.post(
            "/api/knowledge",
            json={"name": "Docs", "scope": "global", "source": "upload"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Docs"
        assert data["scope"] == "global"
        assert data["source"] == "upload"
        assert data["chunkSize"] == 512
        assert data["topK"] == 5
        assert data["embeddingDim"] == 1536
        assert data["documentCount"] == 0

    async def test_create_kb_duplicate_name(self, client: AsyncClient):
        body = {"name": "Dup", "scope": "global", "source": "upload"}
        await client.post("/api/knowledge", json=body)
        resp = await client.post("/api/knowledge", json=body)
        assert resp.status_code == 409
        assert resp.json()["code"] == "knowledge_base_name_exists"

    async def test_create_kb_invalid_scope(self, client: AsyncClient):
        resp = await client.post(
            "/api/knowledge", json={"name": "X", "scope": "bad", "source": "upload"}
        )
        assert resp.status_code == 422

    async def test_create_kb_agent_scope_requires_ref(self, client: AsyncClient):
        resp = await client.post(
            "/api/knowledge", json={"name": "X", "scope": "agent", "source": "upload"}
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "scope_ref_required"


class TestListKB:
    async def test_list_empty(self, client: AsyncClient):
        resp = await client.get("/api/knowledge")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0

    async def test_list_with_items_and_filter(self, client: AsyncClient):
        await client.post(
            "/api/knowledge", json={"name": "A", "scope": "global", "source": "upload"}
        )
        await client.post(
            "/api/knowledge",
            json={"name": "B", "scope": "agent", "source": "upload", "scopeRef": "a1"},
        )
        resp = await client.get("/api/knowledge?scope=global")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["name"] == "A"

    async def test_list_filter_by_source(self, client: AsyncClient):
        await client.post(
            "/api/knowledge", json={"name": "A", "scope": "global", "source": "upload"}
        )
        await client.post(
            "/api/knowledge",
            json={"name": "B", "scope": "global", "source": "url", "reference": "http://x"},
        )
        resp = await client.get("/api/knowledge?source=url")
        assert resp.json()["total"] == 1
        assert resp.json()["items"][0]["name"] == "B"


class TestGetKB:
    async def test_get_kb(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "G", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.get(f"/api/knowledge/{cid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "G"

    async def test_get_kb_not_found(self, client: AsyncClient):
        resp = await client.get(f"/api/knowledge/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.json()["code"] == "knowledge_base_not_found"

    async def test_get_kb_owner_isolation(
        self, client: AsyncClient, session, second_user
    ):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Priv", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        # Simula acesso de outro owner via service.
        from app.api.knowledge import _get_kb
        from app.core.errors import AppError

        with pytest.raises(AppError) as exc:
            await _get_kb(session, second_user.id, uuid.UUID(cid))
        assert exc.value.code == "knowledge_base_not_found"


class TestUpdateKB:
    async def test_update_kb(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "U", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.put(
            f"/api/knowledge/{cid}", json={"name": "U2", "topK": 10, "chunkSize": 256}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "U2"
        assert resp.json()["topK"] == 10
        assert resp.json()["chunkSize"] == 256

    async def test_update_name_and_description(self, client: AsyncClient):
        created = await client.post(
            "/api/knowledge",
            json={"name": "Antes", "description": "Antiga", "scope": "global", "source": "upload"},
        )
        resp = await client.put(
            f"/api/knowledge/{created.json()['id']}",
            json={"name": "Depois", "description": "Nova descrição"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Depois"
        assert resp.json()["description"] == "Nova descrição"

    async def test_update_kb_not_found(self, client: AsyncClient):
        resp = await client.put(f"/api/knowledge/{uuid.uuid4()}", json={"name": "X"})
        assert resp.status_code == 404

    async def test_update_kb_empty_body(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "U", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.put(f"/api/knowledge/{cid}", json={})
        assert resp.status_code == 400


class TestDeleteKB:
    async def test_delete_kb(self, client: AsyncClient, mock_storage):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "D", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        # Upload um doc para ter vetores + arquivo.
        await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("d.txt", b"content here", "text/plain")},
        )
        assert mock_storage.store  # arquivo no storage
        resp = await client.delete(f"/api/knowledge/{cid}")
        assert resp.status_code == 204
        # Arquivo removido do storage.
        assert mock_storage.store == {}

    async def test_delete_kb_not_found(self, client: AsyncClient):
        resp = await client.delete(f"/api/knowledge/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestUpload:
    async def test_upload_txt(self, client: AsyncClient, mock_storage):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Up", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("doc.txt", b"hello world " * 100, "text/plain")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["documentId"] is not None
        assert data["status"] == "ready"
        assert data["chunkCount"] >= 1
        # Arquivo original no storage.
        assert any(k.startswith(f"{cid}/") for k in mock_storage.store)

    async def test_upload_invalid_type(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Up", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("doc.exe", b"MZ", "application/octet-stream")},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_file_type"

    async def test_upload_too_large(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Up", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        big = b"x" * (26 * 1024 * 1024)  # > 25MB
        resp = await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("big.txt", big, "text/plain")},
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "file_too_large"

    async def test_upload_rate_limited(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "RL", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        # 10/min por KB: 10 ok, 11º -> 429.
        for index in range(10):
            r = await client.post(
                f"/api/knowledge/{cid}/upload",
                files={"file": ("a.txt", f"data {index}".encode(), "text/plain")},
            )
            assert r.status_code == 200
        r = await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("b.txt", b"data", "text/plain")},
        )
        assert r.status_code == 429
        assert r.json()["code"] == "rate_limited"
        assert "retryAfter" in r.json().get("details", {})

    async def test_upload_storage_failure(self, client: AsyncClient, mock_storage):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "SF", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        mock_storage.fail_on_save = True
        resp = await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("d.txt", b"data", "text/plain")},
        )
        assert resp.status_code == 500
        assert resp.json()["code"] == "storage_error"


class TestDocuments:
    async def test_list_documents(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Docs", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        await client.post(
            f"/api/knowledge/{cid}/upload", files={"file": ("a.txt", b"x", "text/plain")}
        )
        await client.post(
            f"/api/knowledge/{cid}/upload", files={"file": ("b.txt", b"y", "text/plain")}
        )
        resp = await client.get(f"/api/knowledge/{cid}/documents")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    async def test_delete_document(self, client: AsyncClient, mock_storage, session: AsyncSession):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Docs", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        doc_id = (
            await client.post(
                f"/api/knowledge/{cid}/upload",
                files={"file": ("a.txt", b"x", "text/plain")},
            )
        ).json()["documentId"]
        assert mock_storage.store
        resp = await client.delete(f"/api/knowledge/{cid}/documents/{doc_id}")
        assert resp.status_code == 204

        from sqlalchemy import select

        from app.db.models import KnowledgeBase, KnowledgeChunk

        remaining = await client.get(f"/api/knowledge/{cid}/documents")
        assert remaining.json()["total"] == 0
        assert mock_storage.store == {}
        assert (await session.execute(select(KnowledgeChunk))).scalars().all() == []
        base = await session.get(KnowledgeBase, uuid.UUID(cid))
        assert base.document_count == 0

    async def test_delete_document_not_found(self, client: AsyncClient):
        cid = (
            await client.post(
                "/api/knowledge",
                json={"name": "Docs", "scope": "global", "source": "upload"},
            )
        ).json()["id"]
        resp = await client.delete(f"/api/knowledge/{cid}/documents/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestQuery:
    async def test_query(self, client: AsyncClient, session: AsyncSession):
        # similarityThreshold=-1.0: o embedder mock gera vetores aleatórios;
        # o score (1 - cosine_distance) pode ser negativo. -1.0 desliga o filtro.
        cid = (
            await client.post(
                "/api/knowledge",
                json={
                    "name": "Q",
                    "scope": "global",
                    "source": "upload",
                    "similarityThreshold": -1.0,
                },
            )
        ).json()["id"]
        await client.post(
            f"/api/knowledge/{cid}/upload",
            files={"file": ("d.txt", b"zebra zebra zebra zebra " * 50, "text/plain")},
        )
        resp = await client.post(
            "/api/knowledge/query",
            json={"query": "zebra", "knowledgeBaseIds": [cid], "topK": 3},
        )
        assert resp.status_code == 200
        chunks = resp.json()["chunks"]
        assert len(chunks) >= 1
        assert "zebra" in chunks[0]["content"]
        # Score = 1 - cosine_distance; com o embedder mock pode ser negativo.
        assert -1.0 <= chunks[0]["score"] <= 1.0

    async def test_query_empty_ids(self, client: AsyncClient):
        resp = await client.post(
            "/api/knowledge/query", json={"query": "x", "knowledgeBaseIds": []}
        )
        assert resp.status_code == 200
        assert resp.json()["chunks"] == []
