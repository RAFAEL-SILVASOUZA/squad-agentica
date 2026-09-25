"""Skill content storage: S3-compatible client for Garage (bucket `skills`).

Dono: be-skills (FASE 4). O conteudo .md da skill e persistido no bucket
`skills` do Garage (servico `garage`, endpoint S3 `http://garage:3900`).
A biblioteca Python `minio` e mantida por compatibilidade com a API S3.

Estrategia de consistencia (mesma estrategia do be-agents):
- Create: PUT no Garage ANTES do INSERT no Postgres.
- Update: PUT no Garage ANTES do UPDATE no Postgres.
- Delete: DELETE no Garage ANTES do DELETE no Postgres.
"""

from __future__ import annotations

import io
import logging
from typing import Protocol

from minio import Minio

from app.core.config import settings

logger = logging.getLogger(__name__)


class SkillStorage(Protocol):
    """Interface de storage para conteudo de skills."""

    async def save_skill(self, skill_id: str, content_md: str) -> None:
        """PUT skills/{skill_id}.md no bucket."""
        ...

    async def get_skill(self, skill_id: str) -> str:
        """GET skills/{skill_id}.md do bucket. Retorna o conteudo markdown."""
        ...

    async def delete_skill(self, skill_id: str) -> None:
        """DELETE skills/{skill_id}.md do bucket."""
        ...


class GarageSkillStorage:
    """Implementacao real usando o client Minio (S3-compatible) contra o Garage."""

    def __init__(self) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        )
        self._bucket = settings.minio_bucket_skills

    def _ensure_bucket(self) -> None:
        """Cria o bucket se nao existir (idempotente)."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def save_skill(self, skill_id: str, content_md: str) -> None:
        """PUT skills/{skill_id}.md no bucket."""
        self._ensure_bucket()
        data = content_md.encode("utf-8")
        self._client.put_object(
            self._bucket,
            f"{skill_id}.md",
            io.BytesIO(data),
            length=len(data),
            content_type="text/markdown",
        )
        logger.debug("Saved skill content: skills/%s.md", skill_id)

    async def get_skill(self, skill_id: str) -> str:
        """GET skills/{skill_id}.md do bucket."""
        response = self._client.get_object(self._bucket, f"{skill_id}.md")
        try:
            content = response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()
        return content

    async def delete_skill(self, skill_id: str) -> None:
        """DELETE skills/{skill_id}.md do bucket."""
        self._client.remove_object(self._bucket, f"{skill_id}.md")
        logger.debug("Deleted skill content: skills/%s.md", skill_id)


def get_skill_storage() -> SkillStorage:
    """Fabrica: retorna a instancia de storage configurada."""
    return GarageSkillStorage()
