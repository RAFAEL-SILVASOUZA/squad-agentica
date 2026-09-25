"""Storage de documentos de knowledge no Garage (S3-compatible).

Dono: be-knowledge (FASE 4). O arquivo original do documento (PDF/MD/TXT) é
persistido no bucket ``knowledge`` do Garage (serviço ``garage``, endpoint S3
``http://garage:3900``). A lib Python ``minio`` é mantida por compatibilidade
com a API S3 do Garage.

Key: ``{kb_id}/{doc_id}.{ext}`` (o ext vem do nome original do arquivo).
Metadados (nome, tamanho, status, chunk_count) ficam no Postgres.

Estratégia de consistência (mesma do be-agents):
- Create: PUT no Garage ANTES do INSERT no Postgres.
- Delete: DELETE no Garage ANTES do DELETE no Postgres.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol

from minio import Minio

from app.core.config import settings

logger = logging.getLogger(__name__)


class KnowledgeStorage(Protocol):
    """Interface de storage para documentos de knowledge."""

    async def save_document(self, kb_id: str, doc_id: str, data: bytes, ext: str = "") -> str:
        """PUT knowledge/{kb_id}/{doc_id}.{ext}. Retorna a key."""
        ...

    async def get_document(self, kb_id: str, doc_id: str, ext: str = "") -> bytes:
        """GET knowledge/{kb_id}/{doc_id}.{ext}."""
        ...

    async def delete_document(self, kb_id: str, doc_id: str, ext: str = "") -> None:
        """DELETE knowledge/{kb_id}/{doc_id}.{ext}."""
        ...


class GarageKnowledgeStorage:
    """Implementação real contra o Garage (client Minio, S3-compatible)."""

    def __init__(self, bucket: str | None = None) -> None:
        # Bucket de knowledge (default "knowledge"). Não vem de settings porque
        # o config é de outro dono; registrado como decisão na resposta final.
        self._bucket = bucket or "knowledge"
        self._client: Minio | None = None

    def _get_client(self) -> Minio:
        # Client lazy: a validação do endpoint (sem path) só acontece no uso,
        # não na construção (permite instanciar em teste sem rede).
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_root_user,
                secret_key=settings.minio_root_password,
                secure=False,
            )
        return self._client

    def _key(self, kb_id: str, doc_id: str, ext: str) -> str:
        return f"{kb_id}/{doc_id}.{ext}" if ext else f"{kb_id}/{doc_id}"

    def _ensure_bucket(self) -> None:
        client = self._get_client()
        if not client.bucket_exists(self._bucket):
            client.make_bucket(self._bucket)

    async def save_document(self, kb_id: str, doc_id: str, data: bytes, ext: str = "") -> str:
        self._ensure_bucket()
        client = self._get_client()
        key = self._key(kb_id, doc_id, ext)
        client.put_object(
            self._bucket,
            key,
            io.BytesIO(data),
            length=len(data),
        )
        logger.debug("Saved knowledge document: %s/%s", self._bucket, key)
        return key

    async def get_document(self, kb_id: str, doc_id: str, ext: str = "") -> bytes:
        client = self._get_client()
        key = self._key(kb_id, doc_id, ext)
        response = client.get_object(self._bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    async def delete_document(self, kb_id: str, doc_id: str, ext: str = "") -> None:
        client = self._get_client()
        key = self._key(kb_id, doc_id, ext)
        client.remove_object(self._bucket, key)
        logger.debug("Deleted knowledge document: %s/%s", self._bucket, key)


def get_knowledge_storage() -> KnowledgeStorage:
    """Fábrica: retorna a instância de storage configurada."""
    return GarageKnowledgeStorage()
