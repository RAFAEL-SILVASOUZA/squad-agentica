"""S3-compatible client for Garage (worker side).

Dono: rt-worker (FASE 6). O worker baixa artefatos do Garage:
- ``agents/{agent_id}.yml``: definicao do agente (snapshot).
- ``skills/{skill_id}.md``: conteudo de skills associadas.

A biblioteca Python ``minio`` e mantida por compatibilidade com a API S3
do Garage (servico ``garage``, endpoint ``http://garage:3900``).

Cache local com TTL: evita N downloads do Garage a cada execucao.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Protocol

from minio import Minio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings (lidas do ambiente, sem dependencia do app.core.config do
# orchestrator; o worker tem seu proprio ambiente)
# ---------------------------------------------------------------------------

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://garage:3900")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "admin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "change-me-in-prod")
MINIO_BUCKET_AGENTS = os.environ.get("MINIO_BUCKET_AGENTS", "agents")
MINIO_BUCKET_SKILLS = os.environ.get("MINIO_BUCKET_SKILLS", "skills")

# TTL em segundos para o cache local de artefatos.
CACHE_TTL_SECONDS = 300.0


# ---------------------------------------------------------------------------
# Cache local (em memoria) com TTL
# ---------------------------------------------------------------------------


@dataclass
class _CacheEntry:
    content: str
    fetched_at: float


class LocalCache:
    """Cache local (em memoria) de conteudo de artefatos, com TTL.

    Chave: ``bucket/object_name``. Evita N downloads do Garage por execucao.
    """

    def __init__(self, ttl_seconds: float = CACHE_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> str | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if (time.monotonic() - entry.fetched_at) > self._ttl:
            del self._entries[key]
            return None
        return entry.content

    def put(self, key: str, content: str) -> None:
        self._entries[key] = _CacheEntry(content=content, fetched_at=time.monotonic())

    def clear(self) -> None:
        self._entries.clear()


# ---------------------------------------------------------------------------
# Protocol (injetavel para testes)
# ---------------------------------------------------------------------------


class AgentArtifactClient(Protocol):
    """Interface para download de artefatos do agente."""

    async def get_agent_yaml(self, agent_id: str) -> str:
        """GET agents/{agent_id}.yml do bucket. Retorna o conteudo YAML."""
        ...

    async def get_skill_md(self, skill_id: str) -> str:
        """GET skills/{skill_id}.md do bucket. Retorna o conteudo markdown."""
        ...


# ---------------------------------------------------------------------------
# Implementacao real (Garage via minio)
# ---------------------------------------------------------------------------


class GarageClient:
    """Cliente S3 (Garage) para download de artefatos do worker."""

    def __init__(
        self,
        endpoint: str = MINIO_ENDPOINT,
        access_key: str = MINIO_ROOT_USER,
        secret_key: str = MINIO_ROOT_PASSWORD,
        bucket_agents: str = MINIO_BUCKET_AGENTS,
        bucket_skills: str = MINIO_BUCKET_SKILLS,
        cache: LocalCache | None = None,
    ) -> None:
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )
        self._bucket_agents = bucket_agents
        self._bucket_skills = bucket_skills
        self._cache = cache or LocalCache()

    def _get_object(self, bucket: str, object_name: str) -> str:
        """Baixa um objeto do bucket (com cache local)."""
        cache_key = f"{bucket}/{object_name}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        response = self._client.get_object(bucket, object_name)
        try:
            content = response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()

        self._cache.put(cache_key, content)
        return content

    async def get_agent_yaml(self, agent_id: str) -> str:
        """GET agents/{agent_id}.yml do bucket."""
        return self._get_object(self._bucket_agents, f"{agent_id}.yml")

    async def get_skill_md(self, skill_id: str) -> str:
        """GET skills/{skill_id}.md do bucket."""
        return self._get_object(self._bucket_skills, f"{skill_id}.md")


# ---------------------------------------------------------------------------
# Fabrica
# ---------------------------------------------------------------------------

_client_instance: GarageClient | None = None


def get_artifact_client() -> GarageClient:
    """Fabrica singleton: retorna a instancia de client configurada."""
    global _client_instance
    if _client_instance is None:
        _client_instance = GarageClient()
    return _client_instance
