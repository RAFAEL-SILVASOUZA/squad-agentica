"""Respostas RAG persistidas para conversas de uma base de conhecimento."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_resolution import resolve_embedder, resolve_llm_client
from app.core.errors import AppError
from app.db.models import (
    KnowledgeBase,
    KnowledgeConversation,
    KnowledgeDocument,
    KnowledgeMessage,
)
from app.knowledge import rag as rag_module
from app.knowledge.embedder import get_embedder

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
    """Consulta a base, chama o provedor configurado e persiste a resposta.

    A pergunta já deve estar commitada. Falhas de RAG/LLM viram 502 "llm_error"
    e a pergunta permanece salva.
    """
    conversation_id = conversation.id
    # Adendo 9: embedder resolvido pela integração do usuário (sem env).
    rag = rag_module.get_rag_service(get_embedder(await resolve_embedder(owner_id)))
    try:
        results = await rag.query(
            db,
            owner_id,
            question,
            [kb.id],
            top_k=kb.top_k,
            agent_id=kb.scope_ref if kb.scope == "agent" else None,
            pipeline_id=kb.scope_ref if kb.scope == "pipeline" else None,
        )
        # Se o threshold da KB filtrou tudo, refaz sem filtro (top-k) e deixa a
        # LLM decidir se há material pra responder (o SYSTEM_PROMPT já instrui
        # a dizer "não encontrei" quando não há). Evita o dead-end de "não
        # encontrei nada" quando o threshold ficou restritivo pro embedding real.
        if not results:
            results = await rag.query(
                db,
                owner_id,
                question,
                [kb.id],
                top_k=kb.top_k,
                agent_id=kb.scope_ref if kb.scope == "agent" else None,
                pipeline_id=kb.scope_ref if kb.scope == "pipeline" else None,
                threshold_override=-1.0,
            )
    except Exception as exc:
        await db.rollback()
        raise AppError(
            502, "bad gateway", "llm_error",
            {"errors": ["Não foi possível consultar a base de conhecimento."]},
        ) from exc

    document_ids = {
        uuid.UUID(str(item["documentId"])) for item in results if item.get("documentId")
    }
    names: dict[uuid.UUID, str] = {}
    if document_ids:
        rows = await db.execute(
            select(KnowledgeDocument.id, KnowledgeDocument.name).where(
                KnowledgeDocument.id.in_(document_ids)
            )
        )
        names = {row.id: row.name for row in rows}
    sources: list[dict[str, Any]] = []
    for item in results:
        document_id = item.get("documentId")
        sources.append({
            "documentId": str(document_id) if document_id else "",
            "documentName": names.get(uuid.UUID(str(document_id)), "") if document_id else "",
            "chunkId": str(item.get("chunkId") or ""),
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
                    .where(KnowledgeMessage.conversation_id == conversation_id)
                    .order_by(KnowledgeMessage.created_at.desc(), KnowledgeMessage.id.desc())
                    .limit(6)
                )
            )
            .scalars()
            .all()
        )
        # A pergunta atual já foi persistida e é a última do histórico.
        history = list(reversed(previous))
        excerpts = "\n\n".join(
            f"[{index}] {source['text']}" for index, source in enumerate(sources, start=1)
        )
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for message in history[:-1]:
            messages.append({"role": message.role, "content": message.content})
        messages.append({"role": "user", "content": f"{question}\n\nTrechos:\n{excerpts}"})
        # Encerra a transação de leitura antes da chamada lenta ao LLM.
        await db.commit()
        try:
            # Adendo 9: LLM resolvido pela integração do usuário (sem env).
            llm_client = await resolve_llm_client(owner_id)
            content = await llm_client.chat(messages)
        except Exception as exc:
            raise AppError(
                502, "bad gateway", "llm_error",
                {"errors": ["Não foi possível gerar a resposta agora. Tente novamente."]},
            ) from exc

    # Nova transação curta: trava a conversa e persiste a resposta.
    locked = (
        await db.execute(
            select(KnowledgeConversation)
            .where(KnowledgeConversation.id == conversation_id)
            .with_for_update()
        )
    ).scalar_one()
    latest_timestamp = (
        await db.execute(
            select(KnowledgeMessage.created_at)
            .where(KnowledgeMessage.conversation_id == conversation_id)
            .order_by(KnowledgeMessage.created_at.desc(), KnowledgeMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if latest_timestamp is not None and now <= latest_timestamp:
        now = latest_timestamp + timedelta(microseconds=1)
    response = KnowledgeMessage(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        role="assistant",
        content=content,
        sources=sources,
        created_at=now,
    )
    locked.updated_at = now
    db.add(response)
    await db.commit()
    await db.refresh(response)
    return response
