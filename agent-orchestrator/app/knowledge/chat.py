"""Respostas RAG persistidas para conversas de uma base de conhecimento."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.db.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeConversation,
    KnowledgeDocument,
    KnowledgeMessage,
)
from app.knowledge import rag as rag_module

NO_RESULTS = "Não encontrei nada sobre isso nesta base."
SYSTEM_PROMPT = (
    "Responda em pt-BR usando apenas os trechos fornecidos; se a resposta não estiver "
    "nos trechos, diga que não encontrou na base; cite as fontes como [1], [2]"
)


async def answer(
    db: AsyncSession,
    owner_id: uuid.UUID,
    kb: KnowledgeBase,
    conversation: KnowledgeConversation,
    question: str,
) -> KnowledgeMessage:
    """Consulta a base, chama o provedor configurado e persiste a resposta."""
    results = await rag_module.get_rag_service().query(
        db,
        owner_id,
        question,
        [kb.id],
        top_k=kb.top_k,
        agent_id=kb.scope_ref if kb.scope == "agent" else None,
        pipeline_id=kb.scope_ref if kb.scope == "pipeline" else None,
    )
    now = datetime.now(UTC)
    latest_timestamp = (
        await db.execute(
            select(KnowledgeMessage.created_at)
            .where(KnowledgeMessage.conversation_id == conversation.id)
            .order_by(KnowledgeMessage.created_at.desc(), KnowledgeMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest_timestamp is not None and now <= latest_timestamp:
        now = latest_timestamp + timedelta(microseconds=1)
    sources: list[dict[str, Any]] = []
    for item in results:
        document_id = item.get("documentId")
        document_name = ""
        if document_id:
            document = await db.get(KnowledgeDocument, uuid.UUID(str(document_id)))
            document_name = document.name if document else ""
        chunk_id = item.get("chunkId")
        if not chunk_id and document_id:
            chunk = await db.execute(
                select(KnowledgeChunk.id).where(
                    KnowledgeChunk.document_id == uuid.UUID(str(document_id)),
                    KnowledgeChunk.chunk_index == item.get("chunkIndex", 0),
                )
            )
            found_id = chunk.scalar_one_or_none()
            chunk_id = str(found_id) if found_id else f"{document_id}:{item.get('chunkIndex', 0)}"
        sources.append({
            "documentId": str(document_id) if document_id else "",
            "documentName": document_name,
            "chunkId": str(chunk_id or ""),
            "text": str(item.get("content", "")),
            "score": float(item.get("score", 0)),
        })

    if not sources:
        content = NO_RESULTS
    else:
        previous = list(
            (
                await db.execute(
                    select(KnowledgeMessage)
                    .where(KnowledgeMessage.conversation_id == conversation.id)
                    .order_by(KnowledgeMessage.created_at.desc(), KnowledgeMessage.id.desc())
                    .limit(6)
                )
            )
            .scalars()
            .all()
        )
        history = list(reversed(previous))
        if not history or history[-1].role != "user" or history[-1].content != question:
            history.append(KnowledgeMessage(role="user", content=question))

        excerpts = "\n\n".join(
            f"[{index}] {source['text']}" for index, source in enumerate(sources, start=1)
        )
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in history[:-1]:
            messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": f"{question}\n\nTrechos:\n{excerpts}"})
        content = await llm.get_llm_client().chat(messages)
    response = KnowledgeMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        sources=sources,
        created_at=now,
    )
    conversation.updated_at = now
    db.add(response)
    await db.commit()
    await db.refresh(response)
    return response
