"""Tests for the RAG query + ingestion (D9 9.3/9.4, spec 7.2).

Cobre: ingestão (chunk -> embed mock -> vector(1536) no pgvector), busca por
similaridade real (cosine distance ``<=>``), top-K, filtro por escopo e
isolamento por owner.
"""

from __future__ import annotations

import uuid

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import MockEmbedder
from app.db.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, User
from app.knowledge.embedder import get_embedder
from app.knowledge.rag import RagService

# A coluna pgvector é fixa em 1536 dims na V1 (spec 7.2), então o mock
# precisa produzir vetores de 1536 dims para o insert real no banco.
TEST_DIM = 1536


@pytest_asyncio.fixture
async def owner(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email="owner@example.com", name="Owner", password_hash="h")
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def other_owner(session: AsyncSession) -> User:
    user = User(id=uuid.uuid4(), email="other@example.com", name="Other", password_hash="h")
    user.owner_id = user.id
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest_asyncio.fixture
async def service() -> RagService:
    return RagService(embedder=get_embedder(embedder=MockEmbedder(dim=TEST_DIM)))


def _make_kb(
    owner_id: uuid.UUID,
    name: str,
    scope: str = "global",
    scope_ref: str | None = None,
    source: str = "upload",
) -> KnowledgeBase:
    return KnowledgeBase(
        id=uuid.uuid4(),
        owner_id=owner_id,
        name=name,
        scope=scope,
        scope_ref=scope_ref,
        source=source,
        reference="",
        chunk_size=512,
        chunk_overlap=64,
        top_k=5,
        similarity_threshold=0.0,
        embedding_model="text-embedding-3-small",
        embedding_dim=TEST_DIM,
    )


async def _ingest(
    session: AsyncSession,
    service: RagService,
    kb: KnowledgeBase,
    name: str,
    content: str,
) -> KnowledgeDocument:
    """Cria um documento e ingere (chunk -> embed -> vector)."""
    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        owner_id=kb.owner_id,
        knowledge_base_id=kb.id,
        name=name,
        source="upload",
        url=None,
        size=0,
        chunk_count=0,
        status="processing",
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    await service.ingest_document(session, kb, doc, content=content)
    return doc


class TestIngest:
    async def test_ingest_creates_chunks_and_vectors(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        kb = _make_kb(owner.id, "KB1")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)

        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            owner_id=owner.id,
            knowledge_base_id=kb.id,
            name="doc.txt",
            source="upload",
            url=None,
            size=0,
            chunk_count=0,
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunk_count = await service.ingest_document(
            session, kb, doc, content="alpha beta gamma delta " * 200
        )
        doc_id = doc.id

        assert chunk_count > 1
        # Chunks persistidos com embedding vector(16).
        result = await session.execute(
            select(KnowledgeChunk).where(
                KnowledgeChunk.knowledge_base_id == kb.id,
                KnowledgeChunk.document_id == doc_id,
            )
        )
        chunks = list(result.scalars().all())
        assert len(chunks) == chunk_count
        for c in chunks:
            assert len(c.embedding) == TEST_DIM
        # Documento registrado.
        doc = await session.get(KnowledgeDocument, doc_id)
        assert doc is not None
        assert doc.status == "ready"
        assert doc.chunk_count == chunk_count

    async def test_ingest_empty_content_zero_chunks(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        kb = _make_kb(owner.id, "KBE")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            owner_id=owner.id,
            knowledge_base_id=kb.id,
            name="empty.txt",
            source="upload",
            url=None,
            size=0,
            chunk_count=0,
            status="processing",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)
        chunk_count = await service.ingest_document(session, kb, doc, content="   ")
        assert chunk_count == 0
        assert doc.status == "ready"
        assert doc.chunk_count == 0


class TestQuery:
    async def test_query_returns_relevant_topk(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        kb = _make_kb(owner.id, "KBQ")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)

        # Ingesta um documento com um termo distinto e marcante.
        await _ingest(
            session,
            service,
            kb,
            "d.txt",
            "zebra zebra zebra zebra zebra zebra zebra zebra " * 50,
        )

        results = await service.query(session, owner.id, "zebra", [kb.id], top_k=3)
        assert len(results) >= 1
        # O chunk mais relevante menciona "zebra".
        assert "zebra" in results[0]["content"]
        # Score é similaridade (1 - cosine distance), em [0, 1].
        assert 0.0 <= results[0]["score"] <= 1.0
        # Ordenado por score decrescente.
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    async def test_query_respects_topk(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        kb = _make_kb(owner.id, "KBK")
        session.add(kb)
        await session.commit()
        await session.refresh(kb)
        await _ingest(
            session, service, kb, "d.txt", " ".join(f"w{i}" for i in range(2000))
        )
        results = await service.query(session, owner.id, "w0", [kb.id], top_k=2)
        assert len(results) <= 2

    async def test_query_owner_isolation(
        self, session: AsyncSession, owner: User, other_owner: User, service: RagService
    ):
        """Owner B não vê chunks do owner A."""
        kb_a = _make_kb(owner.id, "KBA")
        session.add(kb_a)
        await session.commit()
        await session.refresh(kb_a)
        await _ingest(session, service, kb_a, "d.txt", "secret secret secret " * 50)

        # Query do other_owner apontando para a KB do owner -> vazio.
        results = await service.query(session, other_owner.id, "secret", [kb_a.id], top_k=5)
        assert results == []

    async def test_query_scope_isolation(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        """KB com escopo agent só é acessível quando o contexto casa."""
        kb_agent = _make_kb(owner.id, "KBAgent", scope="agent", scope_ref="agent-123")
        kb_global = _make_kb(owner.id, "KBGlobal", scope="global")
        session.add(kb_agent)
        session.add(kb_global)
        await session.commit()
        await session.refresh(kb_agent)
        await session.refresh(kb_global)

        await _ingest(session, service, kb_agent, "a.txt", "agentonly agentonly " * 50)
        await _ingest(session, service, kb_global, "g.txt", "globalonly globalonly " * 50)

        # Contexto do agente agent-123: vê a KB de escopo agent + global.
        res_agent = await service.query(
            session, owner.id, "agentonly", [kb_agent.id, kb_global.id], top_k=5,
            agent_id="agent-123",
        )
        assert any("agentonly" in r["content"] for r in res_agent)

        # Contexto de outro agente: a KB de escopo agent é filtrada fora.
        res_other = await service.query(
            session, owner.id, "agentonly", [kb_agent.id, kb_global.id], top_k=5,
            agent_id="agent-999",
        )
        assert not any("agentonly" in r["content"] for r in res_other)

    async def test_query_unknown_kb_returns_empty(
        self, session: AsyncSession, owner: User, service: RagService
    ):
        results = await service.query(session, owner.id, "x", [uuid.uuid4()], top_k=5)
        assert results == []
