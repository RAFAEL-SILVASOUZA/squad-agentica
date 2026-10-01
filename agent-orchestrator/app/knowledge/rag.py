"""RAG: ingestão (chunk -> embed -> pgvector) e query (cosine distance).

Dono: be-knowledge (FASE 4). Spec 7.2 + PLANO-BACKEND §2.11.

Contrato de query (entrega ao runtime, consome por D6):
    query(text, knowledge_base_ids, top_k) -> list[dict]
    cada dict: {"score": float, "content": str, "knowledgeBaseId": str,
                "documentId": str | None, "chunkIndex": int}

Decisões registradas:
- ``score`` = similaridade = ``1 - cosine_distance`` (pgvector ``<=>``).
  Como os embeddings são normalizados, ``1 - <a,b>`` == ``cosine_distance``.
  O ``similarityThreshold`` da KB filtra por ``score >= threshold``.
- Escopo (spec 7.3): ``global`` sempre visível; ``agent`` visível quando
  ``scope_ref == agent_id``; ``pipeline`` visível quando ``scope_ref ==
  pipeline_id``. O filtro é aplicado na query (defesa em profundidade).
- Isolamento por owner: toda query filtra ``owner_id``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument
from app.knowledge.chunker import chunk_text
from app.knowledge.embedder import RagEmbedder, get_embedder


class RagService:
    """Serviço de RAG: ingestão de documentos e busca semântica."""

    def __init__(self, embedder: RagEmbedder | None = None) -> None:
        self._embedder = embedder or get_embedder()

    # ------------------------------------------------------------------
    # Ingestão
    # ------------------------------------------------------------------

    async def ingest_document(
        self,
        db: AsyncSession,
        kb: KnowledgeBase,
        doc: KnowledgeDocument,
        content: str,
        *,
        commit: bool = True,
    ) -> int:
        """Chunka, embute e insere os vetores de um documento já criado.

        Args:
            db: sessão.
            kb: KnowledgeBase (para chunk_size/chunk_overlap/owner_id).
            doc: KnowledgeDocument já persistido (status "processing").
            content: texto bruto do documento.

        Returns:
            chunk_count. O documento fica com status ``ready`` (ou ``failed``).
        """
        try:
            chunks = chunk_text(content, kb.chunk_size, kb.chunk_overlap)
            if chunks:
                vectors = self._embedder.embed_batch(chunks)
                for idx, (text, vec) in enumerate(zip(chunks, vectors, strict=True)):
                    db.add(
                        KnowledgeChunk(
                            id=uuid.uuid4(),
                            owner_id=kb.owner_id,
                            knowledge_base_id=kb.id,
                            document_id=doc.id,
                            chunk_index=idx,
                            content=text,
                            embedding=vec,
                        )
                    )
            doc.chunk_count = len(chunks)
            doc.status = "ready"
            kb.document_count = (kb.document_count or 0) + 1
            await db.flush()
            if commit:
                await db.commit()
                await db.refresh(doc)
            return len(chunks)
        except Exception:
            doc.status = "failed"
            if commit:
                await db.commit()
            raise

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    async def query(
        self,
        db: AsyncSession,
        owner_id: uuid.UUID,
        text: str,
        knowledge_base_ids: list[uuid.UUID],
        top_k: int | None = None,
        agent_id: str | None = None,
        pipeline_id: str | None = None,
        threshold_override: float | None = None,
    ) -> list[dict[str, Any]]:
        """Busca semântica por cosine distance com filtro por escopo e owner.

        Args:
            db: sessão.
            owner_id: dono (isolamento).
            text: texto da query.
            knowledge_base_ids: KBs candidatas.
            top_k: nº de chunks (default: ``top_k`` da primeira KB).
            agent_id: contexto de agente (para escopo ``agent``).
            pipeline_id: contexto de pipeline (para escopo ``pipeline``).
            threshold_override: se definido, substitui o ``similarity_threshold``
                da KB (ex.: ``-1.0`` para não filtrar e devolver sempre o top-k).

        Returns:
            Lista de chunks ordenados por similaridade decrescente.
        """
        if not knowledge_base_ids:
            return []

        # Carrega as KBs candidatas (filtradas por owner) para aplicar escopo
        # e usar o top_k/similarity_threshold.
        result = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.id.in_(knowledge_base_ids),
                KnowledgeBase.owner_id == owner_id,
            )
        )
        kbs = {kb.id: kb for kb in result.scalars().all()}
        if not kbs:
            return []

        # Filtro por escopo (spec 7.3).
        visible_ids: list[uuid.UUID] = []
        for kb_id, kb in kbs.items():
            if kb.scope == "global":
                visible_ids.append(kb_id)
            elif kb.scope == "agent" and kb.scope_ref == agent_id:
                visible_ids.append(kb_id)
            elif kb.scope == "pipeline" and kb.scope_ref == pipeline_id:
                visible_ids.append(kb_id)
        if not visible_ids:
            return []

        # top_k: parâmetro explícito ou default da primeira KB visível.
        if top_k is None:
            top_k = next(iter(kbs.values())).top_k

        query_vec = self._embedder.embed(text)

        # Busca por cosine distance (``<=>``) no pgvector.
        distance = KnowledgeChunk.embedding.cosine_distance(query_vec)
        stmt = (
            select(
                KnowledgeChunk,
                distance.label("distance"),
            )
            .where(
                KnowledgeChunk.owner_id == owner_id,
                KnowledgeChunk.knowledge_base_id.in_(visible_ids),
            )
            .order_by(distance)
            .limit(top_k)
        )
        rows = (await db.execute(stmt)).all()

        # Filtra por similarityThreshold (score = 1 - distance). O override
        # (ex.: -1.0) desliga o filtro e devolve sempre o top-k, deixando a
        # decisão de "há material pra responder?" com a LLM.
        out: list[dict[str, Any]] = []
        for chunk, dist in rows:
            score = 1.0 - float(dist)
            threshold = (
                threshold_override
                if threshold_override is not None
                else kbs[chunk.knowledge_base_id].similarity_threshold
            )
            if score < threshold:
                continue
            out.append(
                {
                    "score": score,
                    "content": chunk.content,
                    "chunkId": str(chunk.id),
                    "knowledgeBaseId": str(chunk.knowledge_base_id),
                    "documentId": str(chunk.document_id) if chunk.document_id else None,
                    "chunkIndex": chunk.chunk_index,
                }
            )
        return out


def get_rag_service(embedder: RagEmbedder | None = None) -> RagService:
    """Fábrica do serviço de RAG (embedder injetável para testes)."""
    return RagService(embedder=embedder)


def _not_available() -> None:
    """Rivvn: fora do caminho crítico da V1 (contrato §10)."""
    raise AppError(
        501,
        "not available",
        "rivvn_not_available",
        {"message": "Rivvn não está disponível na V1 (requer contrato comercial ativo)."},
    )


# Mantido para referência: a fonte ``rivvn`` não é processada na V1.
def rivvn_query(*_args: Any, **_kwargs: Any) -> None:
    _not_available()
