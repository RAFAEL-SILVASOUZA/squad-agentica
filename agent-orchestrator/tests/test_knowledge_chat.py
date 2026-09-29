from __future__ import annotations

import uuid

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import register_exception_handlers
from app.db.models import User
from app.db.session import get_db


class Storage:
    async def save_document(self, *_args, **_kwargs):
        return None

    async def delete_document(self, *_args, **_kwargs):
        return None


class Rag:
    def __init__(self):
        self.results = []
        self.queries = []

    async def query(self, db, owner_id, text, knowledge_base_ids, top_k=None, **_kwargs):
        self.queries.append(
            (text, knowledge_base_ids, top_k, _kwargs.get("agent_id"), _kwargs.get("pipeline_id"))
        )
        return self.results

    async def ingest_document(self, db, kb, doc, content):
        doc.status = "ready"
        doc.chunk_count = 1
        kb.document_count += 1
        await db.commit()
        await db.refresh(doc)
        return 1


class RecordingLLM:
    def __init__(self):
        self.calls = []

    async def chat(self, messages, **_kwargs):
        self.calls.append(messages)
        return "Resposta com citação [1]."


@pytest_asyncio.fixture
async def user(session: AsyncSession):
    record = User(
        id=uuid.uuid4(),
        email="knowledge-chat@example.test",
        name="Owner",
        password_hash="x",
    )
    record.owner_id = record.id
    session.add(record)
    await session.commit()
    return record


@pytest_asyncio.fixture
async def chat_client(session, user, monkeypatch):
    from app.api.knowledge import router

    rag = Rag()
    llm = RecordingLLM()
    import app.api.knowledge as knowledge_module
    import app.core.llm as llm_module
    import app.knowledge.rag as rag_module

    monkeypatch.setattr(knowledge_module, "_get_storage", Storage)
    monkeypatch.setattr(rag_module, "get_rag_service", lambda: rag)
    monkeypatch.setattr(llm_module, "get_llm_client", lambda: llm)
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api")

    async def db_override():
        yield session

    async def user_override():
        return user

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = user_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, rag, llm, user, app


async def _new_base(client):
    response = await client.post(
        "/api/knowledge", json={"name": "Base", "scope": "global", "source": "upload"}
    )
    assert response.status_code == 201
    return response.json()["id"]


class TestKnowledgeChat:
    async def test_create_ask_list_reopen_and_delete_conversation(self, chat_client):
        client, rag, llm, _user, _app = chat_client
        kb_id = await _new_base(client)
        uploaded = await client.post(
            f"/api/knowledge/{kb_id}/upload",
            files={"file": ("guia.txt", "Política de férias".encode(), "text/plain")},
        )
        assert uploaded.status_code == 200, uploaded.text
        document_id = uploaded.json()["documentId"]
        created = await client.post(f"/api/knowledge/{kb_id}/conversations", json={})
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        rag.results = [{
            "score": 0.91, "content": "Funcionários têm 30 dias de férias.",
            "knowledgeBaseId": kb_id, "documentId": document_id, "chunkIndex": 0,
        }]
        first = await client.post(
            f"/api/knowledge/{kb_id}/conversations/{conversation_id}/messages",
            json={"content": "Quantos dias de férias?"},
        )
        second = await client.post(
            f"/api/knowledge/{kb_id}/conversations/{conversation_id}/messages",
            json={"content": "E quem pode tirar?"},
        )
        listing = await client.get(f"/api/knowledge/{kb_id}/conversations")
        reopened = await client.get(f"/api/knowledge/{kb_id}/conversations/{conversation_id}")
        assert first.status_code == second.status_code == 200
        assert first.json()["sources"][0] == {
            "documentId": document_id,
            "documentName": "guia.txt",
            "chunkId": first.json()["sources"][0]["chunkId"],
            "text": "Funcionários têm 30 dias de férias.",
            "score": 0.91,
        }
        assert len(reopened.json()["messages"]) == 4
        message_rows = reopened.json()["messages"]
        assert [message["role"] for message in message_rows] == [
            "user", "assistant", "user", "assistant"
        ]
        assert [message["createdAt"] for message in message_rows] == sorted(
            message["createdAt"] for message in message_rows
        )
        assert listing.json()["items"][0]["messageCount"] == 4
        assert len(llm.calls) == 2
        assert any(
            message["content"].startswith("Quantos dias de férias?") for message in llm.calls[1]
        )
        assert any(
            message["content"].startswith("E quem pode tirar?") for message in llm.calls[1]
        )
        assert created.json()["title"] == "Nova conversa"
        assert listing.json()["items"][0]["title"] == "Quantos dias de férias?"
        removed = await client.delete(f"/api/knowledge/{kb_id}/conversations/{conversation_id}")
        assert removed.status_code == 204

    async def test_empty_results_skip_llm_and_foreign_owner_is_hidden(self, chat_client):
        client, rag, llm, _owner, app = chat_client
        kb_id = await _new_base(client)
        created = await client.post(
            f"/api/knowledge/{kb_id}/conversations", json={"title": "Busca"}
        )
        assert created.status_code == 201, created.text
        conversation_id = created.json()["id"]
        empty = await client.post(
            f"/api/knowledge/{kb_id}/conversations/{conversation_id}/messages",
            json={"content": "Pergunta sem resultado"},
        )
        assert empty.status_code == 200
        assert empty.json()["content"] == "Não encontrei nada sobre isso nesta base."
        assert empty.json()["sources"] == []
        assert llm.calls == []

        other = User(
            id=uuid.uuid4(),
            email="other-chat@example.test",
            name="Other",
            password_hash="x",
        )
        other.owner_id = other.id
        app.dependency_overrides[get_current_user] = lambda: other
        hidden = await client.get(f"/api/knowledge/{kb_id}/conversations/{conversation_id}")
        assert hidden.status_code == 404

    async def test_chat_passes_knowledge_scope_to_rag(self, chat_client):
        client, rag, _llm, _owner, _app = chat_client
        for scope, scope_ref in (
            ("agent", "agent-context-1"),
            ("pipeline", "pipeline-context-1"),
        ):
            created = await client.post(
                "/api/knowledge",
                json={
                    "name": f"Base {scope}",
                    "scope": scope,
                    "scopeRef": scope_ref,
                    "source": "upload",
                },
            )
            assert created.status_code == 201
            kb_id = created.json()["id"]
            conversation = await client.post(f"/api/knowledge/{kb_id}/conversations", json={})
            response = await client.post(
                f"/api/knowledge/{kb_id}/conversations/{conversation.json()['id']}/messages",
                json={"content": "Encontre o conteúdo."},
            )
            assert response.status_code == 200
        assert rag.queries[-2][3:] == ("agent-context-1", None)
        assert rag.queries[-1][3:] == (None, "pipeline-context-1")

    async def test_llm_failure_returns_502_and_keeps_question(self, chat_client):
        client, rag, llm, _owner, _app = chat_client
        kb_id = await _new_base(client)
        conversation_id = (
            await client.post(f"/api/knowledge/{kb_id}/conversations", json={})
        ).json()["id"]
        rag.results = [{"score": 0.9, "content": "Trecho", "chunkIndex": 0}]

        async def boom(messages, **_kwargs):
            raise RuntimeError("provider down")

        llm.chat = boom
        failed = await client.post(
            f"/api/knowledge/{kb_id}/conversations/{conversation_id}/messages",
            json={"content": "Pergunta que falha"},
        )
        assert failed.status_code == 502
        assert failed.json()["code"] == "llm_error"
        reopened = await client.get(f"/api/knowledge/{kb_id}/conversations/{conversation_id}")
        messages = reopened.json()["messages"]
        assert [m["role"] for m in messages] == ["user"]
        assert messages[0]["content"] == "Pergunta que falha"

    async def test_untitled_conversation_listing_has_label(self, chat_client):
        client, _rag, _llm, _owner, _app = chat_client
        kb_id = await _new_base(client)
        await client.post(f"/api/knowledge/{kb_id}/conversations", json={})
        listing = await client.get(f"/api/knowledge/{kb_id}/conversations")
        assert listing.json()["items"][0]["title"] == "Nova conversa"
