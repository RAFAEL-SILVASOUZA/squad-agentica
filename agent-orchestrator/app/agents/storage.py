"""Agent artifact storage: S3-compatible client for Garage (bucket `agents`).

Dono: be-agents (FASE 4). O artefato .yml do agente é persistido no bucket
`agents` do Garage (serviço `garage`, endpoint S3 `http://garage:3900`).
A biblioteca Python `minio` é mantida por compatibilidade com a API S3.

Estratégia de consistência (documentada no D4):
- Create: PUT no Garage ANTES do INSERT no Postgres. Se o Garage falhar,
  não há INSERT (nada a compensar). Se o INSERT falhar após o PUT, o
  artefato órfão é removido (DELETE compensatório no Garage).
- Update: PUT no Garage ANTES do UPDATE no Postgres. Se o Garage falhar,
  o Postgres não é tocado. Se o UPDATE falhar após o PUT, o artefato
  antigo permanece válido (o PUT sobrescreveu, mas o Postgres ainda
  aponta para o mesmo id; na prática o conteúdo novo está no Garage
  mas o metadado antigo no Postgres; o próximo update corrige).
- Delete: DELETE no Garage ANTES do DELETE no Postgres. Se o Garage
  falhar, o Postgres não é tocado (agente continua existindo).
"""

from __future__ import annotations

import logging
from typing import Protocol

from minio import Minio

from app.core.config import settings

logger = logging.getLogger(__name__)


class AgentStorage(Protocol):
    """Interface de storage para artefatos de agentes."""

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        """PUT agents/{agent_id}.yml no bucket."""
        ...

    async def get_agent(self, agent_id: str) -> str:
        """GET agents/{agent_id}.yml do bucket. Retorna o conteúdo YAML."""
        ...

    async def delete_agent(self, agent_id: str) -> None:
        """DELETE agents/{agent_id}.yml do bucket."""
        ...


class GarageAgentStorage:
    """Implementação real usando o client Minio (S3-compatible) contra o Garage."""

    def __init__(self) -> None:
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_root_user,
            secret_key=settings.minio_root_password,
            secure=False,
        )
        self._bucket = settings.minio_bucket_agents

    def _ensure_bucket(self) -> None:
        """Cria o bucket se não existir (idempotente)."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        """PUT agents/{agent_id}.yml no bucket."""
        import io

        self._ensure_bucket()
        data = agent_yaml.encode("utf-8")
        self._client.put_object(
            self._bucket,
            f"{agent_id}.yml",
            io.BytesIO(data),
            length=len(data),
            content_type="text/yaml",
        )
        logger.debug("Saved agent artifact: agents/%s.yml", agent_id)

    async def get_agent(self, agent_id: str) -> str:
        """GET agents/{agent_id}.yml do bucket."""
        response = self._client.get_object(self._bucket, f"{agent_id}.yml")
        try:
            content = response.read().decode("utf-8")
        finally:
            response.close()
            response.release_conn()
        return content

    async def delete_agent(self, agent_id: str) -> None:
        """DELETE agents/{agent_id}.yml do bucket."""
        self._client.remove_object(self._bucket, f"{agent_id}.yml")
        logger.debug("Deleted agent artifact: agents/%s.yml", agent_id)


def get_agent_storage() -> AgentStorage:
    """Fábrica: retorna a instância de storage configurada."""
    return GarageAgentStorage()
