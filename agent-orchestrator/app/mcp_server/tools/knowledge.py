"""Ferramentas MCP de Knowledge Base + RAG (CRUD + upload + query).

Registra as ferramentas de gerenciamento de knowledge bases no servidor MCP.
Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
delega a operação ao service layer (mesmo caminho usado pelo router REST em
``app/api/knowledge.py``).

Erros do service (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.core.errors import AppError
from app.core.ai_resolution import resolve_embedder
from app.db.models import (
    KnowledgeBase,
    KnowledgeChunk,
    KnowledgeDocument,
)
from app.db.session import async_session_factory
from app.knowledge.embedder import get_embedder
from app.knowledge.extract import UnreadableDocumentError, extract_text
from app.knowledge.rag import RagService
from app.knowledge.storage import get_knowledge_storage
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Constantes (mesmas do router REST)
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {"pdf", "md", "txt"}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

_VALID_SCOPES = {"global", "agent", "pipeline"}
_VALID_SOURCES = {"upload", "vector-db", "url", "rivvn"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _ext_from_name(name: str) -> str:
    dot = name.rfind(".")
    if dot == -1:
        return ""
    return name[dot + 1 :].lower()


def _kb_to_dict(kb: KnowledgeBase) -> dict[str, Any]:
    """Converte o model KnowledgeBase para dict (camelCase, como a API)."""
    return {
        "id": str(kb.id),
        "ownerId": str(kb.owner_id),
        "name": kb.name,
        "description": kb.description,
        "scope": kb.scope,
        "scopeRef": kb.scope_ref,
        "source": kb.source,
        "reference": kb.reference,
        "chunkSize": kb.chunk_size,
        "chunkOverlap": kb.chunk_overlap,
        "topK": kb.top_k,
        "similarityThreshold": kb.similarity_threshold,
        "embeddingModel": kb.embedding_model,
        "embeddingDim": kb.embedding_dim,
        "documentCount": kb.document_count,
        "createdAt": kb.created_at.isoformat() if kb.created_at else "",
        "updatedAt": kb.updated_at.isoformat() if kb.updated_at else "",
    }


async def _get_kb(db, owner_id: uuid.UUID, kb_id: uuid.UUID) -> KnowledgeBase:
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise AppError(404, "not_found", "knowledge_base_not_found")
    return kb


async def _get_rag_service(owner_id: uuid.UUID) -> RagService:
    return RagService(embedder=get_embedder(await resolve_embedder(owner_id)))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_knowledge_base(
    name: str,
    description: str | None = None,
    scope: str = "global",
    scope_ref: str | None = None,
    source: str = "upload",
    reference: str = "",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
    top_k: int = 5,
    similarity_threshold: float = 0.7,
    embedding_model: str = "text-embedding-3-small",
    embedding_dim: int = 1536,
) -> dict[str, Any]:
    """Cria uma nova knowledge base.

    ``scope`` pode ser 'global', 'agent' ou 'pipeline' (este último exige
    ``scope_ref``). ``source`` pode ser 'upload', 'vector-db', 'url' ou
    'rivvn'.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    if scope not in _VALID_SCOPES:
        raise ToolError(f"Scope inválido: {scope}. Use global, agent ou pipeline.")
    if source not in _VALID_SOURCES:
        raise ToolError(f"Source inválido: {source}. Use upload, vector-db, url ou rivvn.")
    if scope in ("agent", "pipeline") and not scope_ref:
        raise ToolError("scope_ref é obrigatório quando scope é agent ou pipeline.")

    async with async_session_factory() as db:
        existing = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == user.id, KnowledgeBase.name == name
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ToolError(f"Erro ao criar knowledge base: nome '{name}' já existe.")

        kb = KnowledgeBase(
            id=uuid.uuid4(),
            owner_id=user.id,
            name=name,
            description=description,
            scope=scope,
            scope_ref=scope_ref,
            source=source,
            reference=reference,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
            embedding_model=embedding_model,
            embedding_dim=embedding_dim,
            document_count=0,
        )
        db.add(kb)
        await db.commit()
        await db.refresh(kb)
        return _kb_to_dict(kb)


@mcp.tool()
async def list_knowledge_bases(
    page: int = 1,
    limit: int = 20,
    scope: str | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    """Lista as knowledge bases do usuário autenticado, com paginação e filtros opcionais."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        base = KnowledgeBase.owner_id == user.id
        query = select(KnowledgeBase).where(base)
        count_q = select(func.count()).select_from(KnowledgeBase).where(base)
        if scope:
            query = query.where(KnowledgeBase.scope == scope)
            count_q = count_q.where(KnowledgeBase.scope == scope)
        if source:
            query = query.where(KnowledgeBase.source == source)
            count_q = count_q.where(KnowledgeBase.source == source)

        total = (await db.execute(count_q)).scalar() or 0
        query = query.order_by(KnowledgeBase.created_at.desc()).offset((page - 1) * limit).limit(limit)
        items = list((await db.execute(query)).scalars().all())
        return {
            "items": [_kb_to_dict(kb) for kb in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_knowledge_base(knowledge_base_id: str) -> dict[str, Any]:
    """Obtém uma knowledge base por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(knowledge_base_id)

    async with async_session_factory() as db:
        try:
            kb = await _get_kb(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Knowledge base não encontrado: {e.error}") from e
        return _kb_to_dict(kb)


@mcp.tool()
async def delete_knowledge_base(knowledge_base_id: str) -> dict[str, Any]:
    """Remove uma knowledge base (somente se pertencer ao usuário autenticado).

    Remove também os arquivos originais, vetores e documentos associados.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(knowledge_base_id)

    async with async_session_factory() as db:
        try:
            kb = await _get_kb(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Knowledge base não encontrado: {e.error}") from e

        storage = get_knowledge_storage()
        docs = list(
            (
                await db.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.knowledge_base_id == kb.id
                    )
                )
            ).scalars().all()
        )
        for doc in docs:
            try:
                await storage.delete_document(str(kb.id), str(doc.id), _ext_from_name(doc.name))
            except Exception:
                pass

        await db.delete(kb)
        await db.commit()
        return {"deleted": True, "id": knowledge_base_id}


@mcp.tool()
async def upload_knowledge_file(
    knowledge_base_id: str,
    file_name: str,
    content: str,
) -> dict[str, Any]:
    """Envia um arquivo de texto para uma knowledge base e o indexa (RAG).

    ``file_name`` deve ter extensão .pdf, .md ou .txt. ``content`` é o texto
    bruto do documento. O arquivo é chunkado, embutido e indexado no pgvector.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(knowledge_base_id)
    ext = _ext_from_name(file_name)
    if ext not in ALLOWED_EXTENSIONS:
        raise ToolError(
            f"Tipo de arquivo inválido: .{ext}. Use .pdf, .md ou .txt."
        )

    data = content.encode("utf-8")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ToolError("Arquivo grande demais (limite de 25 MB).")
    content_hash = hashlib.sha256(data).hexdigest()

    async with async_session_factory() as db:
        try:
            kb = await _get_kb(db, user.id, parsed_id)
        except AppError as e:
            raise ToolError(f"Knowledge base não encontrado: {e.error}") from e

        try:
            text_content = extract_text(data, ext)
        except UnreadableDocumentError:
            raise ToolError("Arquivo ilegível.") from None

        storage = get_knowledge_storage()
        rag = await _get_rag_service(user.id)

        doc = KnowledgeDocument(
            id=uuid.uuid4(),
            owner_id=user.id,
            knowledge_base_id=kb.id,
            name=file_name,
            source="upload",
            url=None,
            size=len(data),
            content_hash=content_hash,
            chunk_count=0,
            status="processing",
        )
        db.add(doc)
        await db.flush()

        try:
            await storage.save_document(str(kb.id), str(doc.id), data, ext)
        except Exception:
            await db.rollback()
            raise ToolError("Erro ao salvar arquivo no storage.") from None

        try:
            await rag.ingest_document(db, kb, doc, content=text_content, commit=False)
            await db.commit()
            await db.refresh(doc)
        except Exception:
            await db.rollback()
            try:
                await storage.delete_document(str(kb.id), str(doc.id), ext)
            except Exception:
                pass
            raise ToolError("Erro ao indexar documento.") from None

        return {
            "documentId": str(doc.id),
            "name": doc.name,
            "status": doc.status,
            "chunkCount": doc.chunk_count,
            "size": doc.size,
        }


@mcp.tool()
async def query_knowledge(
    query: str,
    knowledge_base_ids: list[str],
    top_k: int | None = None,
) -> dict[str, Any]:
    """Executa uma query RAG (busca semântica) contra uma ou mais knowledge bases.

    Retorna os chunks mais relevantes ordenados por similaridade decrescente.
    Cada chunk tem: score, content, chunkId, knowledgeBaseId, documentId, chunkIndex.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    kb_ids = [_parse_uuid(k) for k in knowledge_base_ids]

    async with async_session_factory() as db:
        rag = await _get_rag_service(user.id)
        try:
            chunks = await rag.query(db, user.id, query, kb_ids, top_k=top_k)
        except AppError as e:
            raise ToolError(f"Erro na query de knowledge: {e.error}") from e
        return {"chunks": chunks}
