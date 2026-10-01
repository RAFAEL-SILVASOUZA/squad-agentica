"""Resolução central de LLM e embeddings a partir das integrações (adendo 9).

Dono: be-integrations (adendo 9). Antes deste módulo, cada caminho de LLM
(chat de construção, chat de conhecimento, classe base de agente) e todo o
RAG (ingestão + query) chamavam ``get_llm_client()`` / ``get_embedder()``,
que leem **apenas** as variáveis de ambiente. A partir daqui, esses caminhos
resolvem o provedor a partir das **integrações cadastradas** do usuário
(tipo ``llm``), que carregam tanto o config de chat quanto o de embedding
(aninhado em ``config["embedding"]``).

Precedência (adendo 9):
- LLM: 1) escolha no agente (``agent_llm = {integrationId, model}``);
  2) padrão do usuário (``users.preferences['default_llm_integration_id']``);
  3) a primeira integração ``llm`` cadastrada (fallback); 4) **erro claro**
  (``llm_not_configured``) — sem fallback para o ambiente.
- Embedding: 1) padrão do usuário
  (``users.preferences['default_embedding_integration_id']``);
  2) a primeira integração ``llm`` com modelo de embeddings configurado
  (fallback); 3) **erro claro** (``embedding_not_configured``).

A decisão de "erro claro em vez de fallback para o ambiente" é do produto
(adendo 9): o sistema NÃO deve usar a LLM da env quando o usuário tem
integrações; sem integração configurada, o usuário é avisado para
configurar. O pipeline (worker) mantém o próprio fallback para o ambiente,
que é resolvido em ``app.runtime.executor.resolve_node_llm_block``.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embeddings import Embedder, OpenAIEmbedder
from app.core.errors import AppError
from app.core.llm import LLMClient
from app.core.llm_providers import build_llm_client, connection_from_config
from app.core.secrets import SecretError, decrypt_secret
from app.db.models import Integration, User
from app.db.session import async_session_factory

# Erro claro quando o usuário não tem integração configurada (adendo 9).
_LLM_NOT_CONFIGURED = AppError(
    400,
    "validation error",
    "llm_not_configured",
    {
        "message": (
            "Nenhuma integração de LLM configurada. Cadastre uma conexão LLM "
            "em Integrações e defina-a como padrão."
        )
    },
)
_EMBEDDING_NOT_CONFIGURED = AppError(
    400,
    "validation error",
    "embedding_not_configured",
    {
        "message": (
            "Nenhum provedor de embeddings configurado. Cadastre uma conexão "
            "LLM com modelo de embeddings em Integrações e defina-a como padrão."
        )
    },
)


async def _load_llm_integrations(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Carrega as integrações ``llm`` do dono, com a chave já descriptografada.

    Mapeia ``str(integration.id) -> config`` (com ``api_key`` em claro quando
    há ``api_key_encrypted``). Integrações desativadas também são carregadas:
    a seleção por id (agente/padrão) é explícita do usuário.
    """
    result = await session.execute(
        select(Integration).where(
            Integration.owner_id == owner_id,
            Integration.type == "llm",
        )
    )
    configs: dict[str, dict[str, Any]] = {}
    for integ in result.scalars().all():
        cfg = dict(integ.config or {})
        if cfg.get("api_key_encrypted"):
            try:
                cfg["api_key"] = decrypt_secret(cfg["api_key_encrypted"])
            except SecretError:
                cfg["api_key"] = ""
        # O embedding pode ter a própria chave (criptografada em
        # embedding.api_key_encrypted); descriptografa para embedding.api_key.
        emb = cfg.get("embedding")
        if isinstance(emb, dict) and emb.get("api_key_encrypted"):
            emb = dict(emb)
            try:
                emb["api_key"] = decrypt_secret(emb["api_key_encrypted"])
            except SecretError:
                emb["api_key"] = ""
            cfg["embedding"] = emb
        configs[str(integ.id)] = cfg
    return configs


async def _load_embedding_integrations(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Carrega as integrações ``embedding`` do dono, com a chave descriptografada.

    Formato canônico (adendo 9): integração tipo ``embedding`` com config flat
    ``{provider_kind, base_url, api_key, model, dim, query_prefix,
    document_prefix}``. Mapeia ``str(integration.id) -> config`` (com
    ``api_key`` em claro quando há ``api_key_encrypted``).
    """
    result = await session.execute(
        select(Integration).where(
            Integration.owner_id == owner_id,
            Integration.type == "embedding",
        )
    )
    configs: dict[str, dict[str, Any]] = {}
    for integ in result.scalars().all():
        cfg = dict(integ.config or {})
        if cfg.get("api_key_encrypted"):
            try:
                cfg["api_key"] = decrypt_secret(cfg["api_key_encrypted"])
            except SecretError:
                cfg["api_key"] = ""
        configs[str(integ.id)] = cfg
    return configs


async def _load_user_preferences(
    session: AsyncSession, owner_id: uuid.UUID
) -> dict[str, Any] | None:
    user = (
        await session.execute(select(User).where(User.id == owner_id))
    ).scalar_one_or_none()
    return user.preferences if user is not None else None


def _embedding_config(config: dict[str, Any]) -> dict[str, Any]:
    """Extrai o config de embedding de uma integração (adendo 9).

    Formato canônico: objeto ``config["embedding"] = {model, dim,
    query_prefix, document_prefix}``. Mantém compatibilidade com o campo
    legado ``config["embedding_model"]`` (string) salvo antes da unificação.
    """
    emb = config.get("embedding")
    if isinstance(emb, dict):
        return emb
    legacy = config.get("embedding_model")
    if isinstance(legacy, str) and legacy.strip():
        return {"model": legacy.strip()}
    return {}


async def resolve_llm_client(
    owner_id: uuid.UUID | str,
    agent_llm: dict[str, Any] | None = None,
) -> LLMClient:
    """Resolve o ``LLMClient`` a partir das integrações do usuário (adendo 9).

    Precedência: 1) escolha no agente; 2) padrão do usuário; 3) a primeira
    integração ``llm`` cadastrada; 4) erro claro (``llm_not_configured``).
    Nunca cai no ambiente.
    """
    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except (ValueError, TypeError):
        raise _LLM_NOT_CONFIGURED from None

    async with async_session_factory() as session:
        prefs = await _load_user_preferences(session, owner_uuid)
        llm_configs = await _load_llm_integrations(session, owner_uuid)

        # 1) escolha no agente.
        if agent_llm:
            integration_id = str(agent_llm.get("integrationId") or "")
            cfg = llm_configs.get(integration_id)
            if cfg is not None:
                conn = connection_from_config(cfg)
                chosen_model = str(agent_llm.get("model") or "")
                if chosen_model:
                    conn.model = chosen_model
                return build_llm_client(conn)

        # 2) padrão do usuário.
        if prefs:
            default_id = str(prefs.get("default_llm_integration_id") or "")
            cfg = llm_configs.get(default_id)
            if cfg is not None:
                return build_llm_client(connection_from_config(cfg))

        # 3) fallback: a primeira integração llm cadastrada.
        if llm_configs:
            first_cfg = next(iter(llm_configs.values()))
            return build_llm_client(connection_from_config(first_cfg))

    # 4) sem nenhuma integração: erro claro (sem fallback para o ambiente).
    raise _LLM_NOT_CONFIGURED


async def resolve_embedder(owner_id: uuid.UUID | str) -> Embedder:
    """Resolve o ``Embedder`` a partir das integrações do usuário (adendo 9).

    Precedência: 1) padrão do usuário (``default_embedding_integration_id``);
    2) a primeira integração ``embedding`` cadastrada; 3) legado: a primeira
    integração ``llm`` com modelo de embeddings configurado; 4) erro claro
    (``embedding_not_configured``). Nunca cai no ambiente.
    """
    try:
        owner_uuid = uuid.UUID(str(owner_id))
    except (ValueError, TypeError):
        raise _EMBEDDING_NOT_CONFIGURED from None

    async with async_session_factory() as session:
        prefs = await _load_user_preferences(session, owner_uuid)
        emb_integrations = await _load_embedding_integrations(session, owner_uuid)
        llm_configs = await _load_llm_integrations(session, owner_uuid)

        # 1) padrão do usuário: pode apontar p/ integração ``embedding`` (novo)
        #    ou p/ integração ``llm`` com embedding (legado).
        default_id = str((prefs or {}).get("default_embedding_integration_id") or "")
        if default_id:
            if default_id in emb_integrations:
                return _build_embedder_flat(emb_integrations[default_id])
            cfg = llm_configs.get(default_id)
            if cfg is not None:
                emb = _embedding_config(cfg)
                model = str(emb.get("model") or "").strip()
                if model:
                    return _build_embedder(cfg, emb, model)

        # 2) fallback: a primeira integração ``embedding`` cadastrada.
        for candidate in emb_integrations.values():
            model = str(candidate.get("model") or "").strip()
            if model:
                return _build_embedder_flat(candidate)

        # 3) legado: a primeira integração ``llm`` com modelo de embeddings.
        for candidate in llm_configs.values():
            emb = _embedding_config(candidate)
            model = str(emb.get("model") or "").strip()
            if model:
                return _build_embedder(candidate, emb, model)

    # 4) sem nenhuma integração com embeddings: erro claro.
    raise _EMBEDDING_NOT_CONFIGURED


def _build_embedder(
    cfg: dict[str, Any], emb: dict[str, Any], model: str
) -> Embedder:
    """Monta o ``OpenAIEmbedder`` a partir do config de uma integração.

    O embedding pode ter a própria ``base_url`` e ``api_key`` (ex.: servidor de
    embeddings em outra porta que o de chat); quando ausentes, herda os da
    conexão LLM.
    """
    base_url = str(emb.get("base_url") or cfg.get("base_url") or "")
    api_key = str(emb.get("api_key") or cfg.get("api_key") or "")
    dim = int(emb.get("dim") or settings.embedding_dim)
    return OpenAIEmbedder(
        api_key=api_key,
        dim=dim,
        base_url=base_url,
        model=model,
        query_prefix=str(emb.get("query_prefix") or ""),
        document_prefix=str(emb.get("document_prefix") or ""),
    )


def _build_embedder_flat(cfg: dict[str, Any]) -> Embedder:
    """Monta o ``OpenAIEmbedder`` a partir do config flat de uma integração
    tipo ``embedding`` (adendo 9).

    Formato: ``{provider_kind, base_url, api_key, model, dim, query_prefix,
    document_prefix}`` — todos os campos no top-level, sem aninhamento.
    """
    model = str(cfg.get("model") or "").strip()
    return OpenAIEmbedder(
        api_key=str(cfg.get("api_key") or ""),
        dim=int(cfg.get("dim") or settings.embedding_dim),
        base_url=str(cfg.get("base_url") or ""),
        model=model,
        query_prefix=str(cfg.get("query_prefix") or ""),
        document_prefix=str(cfg.get("document_prefix") or ""),
    )
