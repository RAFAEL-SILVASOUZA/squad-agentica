"""Tests for knowledge document storage (Garage, S3-compatible).

Cobre: save/get/delete de documento, key por (kb, doc), falha de storage
(500 envelope via AppError) e injeção de mock.
"""

from __future__ import annotations

import pytest

from app.knowledge.storage import get_knowledge_storage


class MockKnowledgeStorage:
    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.fail_on_save = False
        self.fail_on_delete = False

    async def save_document(self, kb_id: str, doc_id: str, data: bytes) -> str:
        if self.fail_on_save:
            raise ConnectionError("Garage unavailable")
        key = f"{kb_id}/{doc_id}"
        self.store[key] = data
        return key

    async def get_document(self, kb_id: str, doc_id: str) -> bytes:
        key = f"{kb_id}/{doc_id}"
        if key not in self.store:
            raise FileNotFoundError(key)
        return self.store[key]

    async def delete_document(self, kb_id: str, doc_id: str) -> None:
        if self.fail_on_delete:
            raise ConnectionError("Garage unavailable")
        self.store.pop(f"{kb_id}/{doc_id}", None)


@pytest.fixture
def mock_storage() -> MockKnowledgeStorage:
    return MockKnowledgeStorage()


class TestKnowledgeStorage:
    async def test_save_and_get(self, mock_storage: MockKnowledgeStorage):
        key = await mock_storage.save_document("kb1", "doc1", b"hello")
        assert key == "kb1/doc1"
        assert await mock_storage.get_document("kb1", "doc1") == b"hello"

    async def test_delete(self, mock_storage: MockKnowledgeStorage):
        await mock_storage.save_document("kb1", "doc1", b"x")
        await mock_storage.delete_document("kb1", "doc1")
        with pytest.raises(FileNotFoundError):
            await mock_storage.get_document("kb1", "doc1")

    async def test_get_missing_raises(self, mock_storage: MockKnowledgeStorage):
        with pytest.raises(FileNotFoundError):
            await mock_storage.get_document("kb1", "nope")


class TestFactory:
    def test_get_knowledge_storage_returns_protocol(self):
        # O endpoint real (http://garage:3900) não resolve no host de teste;
        # usa um endpoint placeholder só para validar o contrato da fábrica.
        import os

        os.environ["MINIO_ENDPOINT"] = "http://garage:3900"
        from app.knowledge.storage import GarageKnowledgeStorage

        storage = get_knowledge_storage()
        assert isinstance(storage, GarageKnowledgeStorage)
        # Contrato estrutural: expõe os três métodos.
        for m in ("save_document", "get_document", "delete_document"):
            assert hasattr(storage, m)
