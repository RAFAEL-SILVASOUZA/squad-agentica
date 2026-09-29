"""Knowledge Base + RAG API router (D9 9.5, spec 9.3).

Dono: be-knowledge (FASE 4). Rotas (prefixo /api):
- POST /api/knowledge → 201 KnowledgeBase / 400 / 409
- GET /api/knowledge?scope=&source= → 200 paginado
- GET /api/knowledge/{id} → 200 / 404 knowledge_base_not_found
- PUT /api/knowledge/{id} → 200 / 404 / 400
- DELETE /api/knowledge/{id} → 204 / 404 (remove KB + docs + vetores + arquivo)
- POST /api/knowledge/{id}/upload (multipart `file`) → 200 {documentId,...}
  (rate limit 10/min por KB, spec 14.1)
- GET /api/knowledge/{id}/documents → paginado
- DELETE /api/knowledge/{id}/documents/{docId} → 204 / 404
- POST /api/knowledge/query → 200 {chunks:[{score, content, ...}]}

Rivvn (fonte externa) é stub fora do caminho crítico da V1 (contrato §10):
KB com ``source="rivvn"`` responde erro claro "não disponível".
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import AppError
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
from app.knowledge.extract import UnreadableDocumentError, extract_text
from app.knowledge.rag import RagService
from app.knowledge.storage import KnowledgeStorage, get_knowledge_storage

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

# Tipos de arquivo aceitos no upload (spec: PDF, MD, TXT).
# Sem o ponto: ``_ext_from_name`` devolve a extensão sem o ponto inicial.
ALLOWED_EXTENSIONS = {"pdf", "md", "txt"}
# Limite de tamanho do upload (bytes). NGINX: client_max_body_size 25m.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Rate limit de upload: 10 requests/min por KB (spec 14.1), in-memory (V1).
from app.auth.rate_limiter import RateLimiter  # noqa: E402

UNTITLED_CONVERSATION = "Nova conversa"
_upload_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)


# ---------------------------------------------------------------------------
# Schemas (request/response)
# ---------------------------------------------------------------------------


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    scope: str = Field(..., pattern="^(global|agent|pipeline)$")
    scopeRef: str | None = Field(default=None, max_length=200)
    source: str = Field(..., pattern="^(upload|vector-db|url|rivvn)$")
    reference: str = Field(default="", max_length=500)
    chunkSize: int = Field(default=512, ge=1, le=100000)
    chunkOverlap: int = Field(default=64, ge=0)
    topK: int = Field(default=5, ge=1, le=100)
    similarityThreshold: float = Field(default=0.7, ge=-1.0, le=1.0)
    embeddingModel: str = Field(default="text-embedding-3-small", max_length=100)
    embeddingDim: int = Field(default=1536, ge=1, le=4096)


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    chunkSize: int | None = Field(default=None, ge=1, le=100000)
    chunkOverlap: int | None = Field(default=None, ge=0)
    topK: int | None = Field(default=None, ge=1, le=100)
    similarityThreshold: float | None = Field(default=None, ge=-1.0, le=1.0)


class KnowledgeBaseResponse(BaseModel):
    id: str
    ownerId: str
    name: str
    description: str | None
    scope: str
    scopeRef: str | None
    source: str
    reference: str
    chunkSize: int
    chunkOverlap: int
    topK: int
    similarityThreshold: float
    embeddingModel: str
    embeddingDim: int
    documentCount: int
    createdAt: str
    updatedAt: str


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    total: int
    page: int
    limit: int


class KnowledgeDocumentResponse(BaseModel):
    id: str
    knowledgeBaseId: str
    name: str
    source: str
    url: str | None
    size: int
    chunkCount: int
    status: str
    createdAt: str


class KnowledgeDocumentListResponse(BaseModel):
    items: list[KnowledgeDocumentResponse]
    total: int
    page: int
    limit: int


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    knowledgeBaseIds: list[str] = Field(default_factory=list)
    topK: int | None = Field(default=None, ge=1, le=100)


class QueryResponse(BaseModel):
    chunks: list[dict[str, Any]]


class ConversationCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class MessageCreateRequest(BaseModel):
    content: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_storage() -> KnowledgeStorage:
    return get_knowledge_storage()


def _get_rag_service() -> RagService:
    return RagService(embedder=get_embedder())


def _kb_to_response(kb: KnowledgeBase) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=str(kb.id),
        ownerId=str(kb.owner_id),
        name=kb.name,
        description=kb.description,
        scope=kb.scope,
        scopeRef=kb.scope_ref,
        source=kb.source,
        reference=kb.reference,
        chunkSize=kb.chunk_size,
        chunkOverlap=kb.chunk_overlap,
        topK=kb.top_k,
        similarityThreshold=kb.similarity_threshold,
        embeddingModel=kb.embedding_model,
        embeddingDim=kb.embedding_dim,
        documentCount=kb.document_count,
        createdAt=kb.created_at.isoformat() if kb.created_at else "",
        updatedAt=kb.updated_at.isoformat() if kb.updated_at else "",
    )


def _doc_to_response(doc: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse(
        id=str(doc.id),
        knowledgeBaseId=str(doc.knowledge_base_id),
        name=doc.name,
        source=doc.source,
        url=doc.url,
        size=doc.size,
        chunkCount=doc.chunk_count,
        status=doc.status,
        createdAt=doc.created_at.isoformat() if doc.created_at else "",
    )


async def _get_kb(
    db: AsyncSession, owner_id: uuid.UUID, kb_id: uuid.UUID
) -> KnowledgeBase:
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id, KnowledgeBase.owner_id == owner_id
        )
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise AppError(404, "not_found", "knowledge_base_not_found")
    return kb


def _validate_scope(scope: str, scope_ref: str | None) -> None:
    if scope in ("agent", "pipeline") and not scope_ref:
        raise AppError(400, "validation error", "scope_ref_required")


def _ext_from_name(name: str) -> str:
    dot = name.rfind(".")
    if dot == -1:
        return ""
    return name[dot + 1 :].lower()


# ---------------------------------------------------------------------------
# Routes: CRUD de KnowledgeBase
# ---------------------------------------------------------------------------


@router.post("", status_code=201, response_model=KnowledgeBaseResponse)
async def create_knowledge_base(
    body: KnowledgeBaseCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    _validate_scope(body.scope, body.scopeRef)
    existing = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.owner_id == user.id, KnowledgeBase.name == body.name
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError(409, "conflict", "knowledge_base_name_exists")

    kb = KnowledgeBase(
        id=uuid.uuid4(),
        owner_id=user.id,
        name=body.name,
        description=body.description,
        scope=body.scope,
        scope_ref=body.scopeRef,
        source=body.source,
        reference=body.reference,
        chunk_size=body.chunkSize,
        chunk_overlap=body.chunkOverlap,
        top_k=body.topK,
        similarity_threshold=body.similarityThreshold,
        embedding_model=body.embeddingModel,
        embedding_dim=body.embeddingDim,
        document_count=0,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return _kb_to_response(kb)


@router.get("", response_model=KnowledgeBaseListResponse)
async def list_knowledge_bases(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    scope: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> KnowledgeBaseListResponse:
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
    return KnowledgeBaseListResponse(
        items=[_kb_to_response(kb) for kb in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    kb_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    kb = await _get_kb(db, user.id, kb_id)
    return _kb_to_response(kb)


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    kb_id: uuid.UUID,
    body: KnowledgeBaseUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> KnowledgeBaseResponse:
    kb = await _get_kb(db, user.id, kb_id)
    data = body.model_dump(exclude_none=True)
    if not data:
        raise AppError(400, "validation error", "empty_update")

    if "name" in data and data["name"] != kb.name:
        existing = await db.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.owner_id == user.id,
                KnowledgeBase.name == data["name"],
                KnowledgeBase.id != kb_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise AppError(409, "conflict", "knowledge_base_name_exists")

    if "name" in data:
        kb.name = data["name"]
    if "description" in data:
        kb.description = data["description"]
    if "chunkSize" in data:
        kb.chunk_size = data["chunkSize"]
    if "chunkOverlap" in data:
        kb.chunk_overlap = data["chunkOverlap"]
    if "topK" in data:
        kb.top_k = data["topK"]
    if "similarityThreshold" in data:
        kb.similarity_threshold = data["similarityThreshold"]

    await db.commit()
    await db.refresh(kb)
    return _kb_to_response(kb)


@router.delete("/{kb_id}", status_code=204)
async def delete_knowledge_base(
    kb_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    kb = await _get_kb(db, user.id, kb_id)
    storage = _get_storage()

    # Remove arquivos originais + vetores + documentos.
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
            pass  # arquivo pode não existir; segue com a limpeza no Postgres.

    # Vetores + documentos caem por cascade (delete-orphan) ao remover a KB.
    await db.delete(kb)
    await db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Routes: upload + documentos
# ---------------------------------------------------------------------------


@router.post("/{kb_id}/upload")
async def upload_document(
    kb_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
    replace: Annotated[uuid.UUID | None, Query()] = None,
) -> dict[str, Any]:
    kb = await _get_kb(db, user.id, kb_id)

    # Rate limit: 10/min por KB (spec 14.1). Fica antes de ler/hashear o arquivo de
    # propósito: o limite protege exatamente esse trabalho, então um 409 também conta.
    allowed, retry_after = _upload_rate_limiter.is_allowed(str(kb.id))
    if not allowed:
        raise AppError(
            429, "rate_limited", "rate_limited", {"retryAfter": retry_after}
        )

    # Validação de tipo.
    ext = _ext_from_name(file.filename or "")
    if ext not in ALLOWED_EXTENSIONS:
        raise AppError(400, "validation error", "invalid_file_type")

    # Lê o conteúdo e valida o tamanho.
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise AppError(400, "validation error", "file_too_large")
    content_hash = hashlib.sha256(data).hexdigest()

    duplicate_result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.knowledge_base_id == kb.id,
            KnowledgeDocument.content_hash == content_hash,
        )
    )
    duplicate = duplicate_result.scalar_one_or_none()
    replaced_doc = None
    if duplicate is not None and replace is None:
        raise AppError(
            409,
            "conflict",
            "duplicate_document",
            {"documentId": str(duplicate.id), "name": duplicate.name},
        )
    if replace is not None:
        replace_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.id == replace, KnowledgeDocument.knowledge_base_id == kb.id
            )
        )
        replaced_doc = replace_result.scalar_one_or_none()
        if replaced_doc is None:
            raise AppError(404, "not_found", "document_not_found")
        if duplicate is not None and duplicate.id != replaced_doc.id:
            raise AppError(
                409, "conflict", "duplicate_document",
                {"documentId": str(duplicate.id), "name": duplicate.name},
            )
    try:
        content = extract_text(data, ext)
    except UnreadableDocumentError:
        raise AppError(
            400, "validation error", "invalid_file_type", {"errors": ["PDF ilegível"]}
        ) from None

    storage = _get_storage()
    rag = _get_rag_service()

    # Cria o documento (status processing) e salva o arquivo original.
    doc = KnowledgeDocument(
        id=uuid.uuid4(),
        owner_id=user.id,
        knowledge_base_id=kb.id,
        name=file.filename or "document",
        source="upload",
        url=None,
        size=len(data),
        content_hash=content_hash,
        chunk_count=0,
        status="processing",
    )
    db.add(doc)
    if replaced_doc is not None:
        replaced_doc.content_hash = None

    doc_id = doc.id
    kb_uuid = kb.id
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        duplicate_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == kb_uuid,
                KnowledgeDocument.content_hash == content_hash,
            )
        )
        duplicate = duplicate_result.scalar_one_or_none()
        if duplicate is not None:
            raise AppError(
                409,
                "conflict",
                "duplicate_document",
                {"documentId": str(duplicate.id), "name": duplicate.name},
            ) from None
        raise AppError(500, "internal error", "ingest_error") from exc

    try:
        await storage.save_document(str(kb.id), str(doc.id), data, ext)
    except Exception as e:
        await db.rollback()
        try:
            await storage.delete_document(str(kb_uuid), str(doc_id), ext)
        except Exception:
            pass
        raise AppError(500, "internal error", "storage_error") from e

    # Indexação, remoção substituída e metadados ficam na mesma transação.
    old_doc_id = replaced_doc.id if replaced_doc is not None else None
    old_doc_name = replaced_doc.name if replaced_doc is not None else None
    try:
        await rag.ingest_document(db, kb, doc, content=content, commit=False)
        if replaced_doc is not None:
            await db.execute(
                sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == old_doc_id)
            )
            await db.delete(replaced_doc)
            kb.document_count = max(0, (kb.document_count or 0) - 1)
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        duplicate_result = await db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.knowledge_base_id == kb_uuid,
                KnowledgeDocument.content_hash == content_hash,
            )
        )
        duplicate = duplicate_result.scalar_one_or_none()
        try:
            await storage.delete_document(str(kb_uuid), str(doc_id), ext)
        except Exception:
            pass
        if duplicate is not None:
            raise AppError(
                409, "conflict", "duplicate_document",
                {"documentId": str(duplicate.id), "name": duplicate.name},
            ) from None
        raise AppError(500, "internal error", "ingest_error") from e
    except Exception as e:
        await db.rollback()
        try:
            await storage.delete_document(str(kb_uuid), str(doc_id), ext)
        except Exception:
            pass
        raise AppError(500, "internal error", "ingest_error") from e

    if replaced_doc is not None:
        try:
            await storage.delete_document(
                str(kb_uuid), str(old_doc_id), _ext_from_name(old_doc_name)
            )
        except Exception:
            pass

    return {
        "documentId": str(doc.id),
        "name": doc.name,
        "status": doc.status,
        "chunkCount": doc.chunk_count,
        "size": doc.size,
    }


@router.get("/{kb_id}/documents", response_model=KnowledgeDocumentListResponse)
async def list_documents(
    kb_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> KnowledgeDocumentListResponse:
    kb = await _get_kb(db, user.id, kb_id)
    base = KnowledgeDocument.knowledge_base_id == kb.id
    total = (
        await db.execute(select(func.count()).select_from(KnowledgeDocument).where(base))
    ).scalar() or 0
    query = (
        select(KnowledgeDocument)
        .where(base)
        .order_by(KnowledgeDocument.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    items = list((await db.execute(query)).scalars().all())
    return KnowledgeDocumentListResponse(
        items=[_doc_to_response(d) for d in items], total=total, page=page, limit=limit
    )


@router.delete("/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(
    kb_id: uuid.UUID,
    doc_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    kb = await _get_kb(db, user.id, kb_id)
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == doc_id,
            KnowledgeDocument.knowledge_base_id == kb.id,
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise AppError(404, "not_found", "document_not_found")

    storage = _get_storage()
    try:
        await storage.delete_document(str(kb.id), str(doc.id), _ext_from_name(doc.name))
    except Exception:
        pass

    # Remove vetores do documento.
    await db.execute(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
    )
    await db.execute(
        sa_delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
    )
    await db.delete(doc)
    kb.document_count = max(0, (kb.document_count or 0) - 1)
    await db.commit()
    return Response(status_code=204)


async def _get_conversation(
    db: AsyncSession,
    owner_id: uuid.UUID,
    kb_id: uuid.UUID,
    conversation_id: uuid.UUID,
    *,
    for_update: bool = False,
) -> KnowledgeConversation:
    statement = select(KnowledgeConversation).where(
        KnowledgeConversation.id == conversation_id,
        KnowledgeConversation.knowledge_base_id == kb_id,
        KnowledgeConversation.owner_id == owner_id,
    )
    if for_update:
        statement = statement.with_for_update()
    result = await db.execute(statement)
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise AppError(404, "not_found", "conversation_not_found")
    return conversation


@router.get("/{kb_id}/conversations")
async def list_conversations(
    kb_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    kb = await _get_kb(db, user.id, kb_id)
    conversations = list(
        (
            await db.execute(
                select(KnowledgeConversation)
                .where(KnowledgeConversation.knowledge_base_id == kb.id)
                .order_by(KnowledgeConversation.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    items = []
    for conversation in conversations:
        count = (
            await db.execute(
                select(func.count()).select_from(KnowledgeMessage).where(
                    KnowledgeMessage.conversation_id == conversation.id
                )
            )
        ).scalar() or 0
        items.append(
            {
                "id": str(conversation.id),
                "title": conversation.title or UNTITLED_CONVERSATION,
                "updatedAt": conversation.updated_at.isoformat(),
                "messageCount": count,
            }
        )
    return {"items": items}


@router.post("/{kb_id}/conversations", status_code=201)
async def create_conversation(
    kb_id: uuid.UUID,
    body: ConversationCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    kb = await _get_kb(db, user.id, kb_id)
    conversation = KnowledgeConversation(
        id=uuid.uuid4(), owner_id=user.id, knowledge_base_id=kb.id, title=body.title or ""
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return {"id": str(conversation.id), "title": conversation.title or UNTITLED_CONVERSATION}


@router.get("/{kb_id}/conversations/{conversation_id}")
async def get_conversation(
    kb_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    kb = await _get_kb(db, user.id, kb_id)
    conversation = await _get_conversation(db, user.id, kb.id, conversation_id)
    messages = list(
        (
            await db.execute(
                select(KnowledgeMessage)
                .where(KnowledgeMessage.conversation_id == conversation.id)
                .order_by(KnowledgeMessage.created_at, KnowledgeMessage.id)
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": str(conversation.id),
        "title": conversation.title or UNTITLED_CONVERSATION,
        "messages": [
            {
                "id": str(message.id),
                "role": message.role,
                "content": message.content,
                "sources": message.sources,
                "createdAt": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }


@router.delete("/{kb_id}/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    kb_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    kb = await _get_kb(db, user.id, kb_id)
    conversation = await _get_conversation(db, user.id, kb.id, conversation_id)
    await db.delete(conversation)
    await db.commit()
    return Response(status_code=204)


@router.post("/{kb_id}/conversations/{conversation_id}/messages")
async def send_conversation_message(
    kb_id: uuid.UUID,
    conversation_id: uuid.UUID,
    body: MessageCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    kb = await _get_kb(db, user.id, kb_id)
    conversation = await _get_conversation(
        db, user.id, kb.id, conversation_id, for_update=True
    )
    latest_timestamp = (
        await db.execute(
            select(KnowledgeMessage.created_at)
            .where(KnowledgeMessage.conversation_id == conversation.id)
            .order_by(KnowledgeMessage.created_at.desc(), KnowledgeMessage.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    question_timestamp = datetime.now(UTC)
    if latest_timestamp is not None and question_timestamp <= latest_timestamp:
        question_timestamp = latest_timestamp + timedelta(microseconds=1)
    question = KnowledgeMessage(
        id=uuid.uuid4(),
        conversation_id=conversation.id,
        role="user",
        content=body.content,
        sources=[],
        created_at=question_timestamp,
    )
    db.add(question)
    conversation.updated_at = question_timestamp
    if not conversation.title:
        conversation.title = body.content[:60]
    # Commit libera o lock e a transação antes do RAG/LLM; a pergunta fica salva.
    await db.commit()

    from app.knowledge.chat import answer

    response = await answer(db, user.id, kb, conversation, body.content)
    return {
        "id": str(response.id),
        "role": response.role,
        "content": response.content,
        "sources": response.sources,
    }


# ---------------------------------------------------------------------------
# Routes: query semântica
# ---------------------------------------------------------------------------


@router.post("/query", response_model=QueryResponse)
async def query_knowledge(
    body: QueryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[User, Depends(get_current_user)],
) -> QueryResponse:
    rag = _get_rag_service()
    kb_ids = [uuid.UUID(k) for k in body.knowledgeBaseIds]
    chunks = await rag.query(
        db, user.id, body.query, kb_ids, top_k=body.topK
    )
    return QueryResponse(chunks=chunks)
