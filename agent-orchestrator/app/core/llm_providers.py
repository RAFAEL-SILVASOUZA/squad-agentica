"""Adaptadores e fábrica de LLM por conexão (adendo 8).

Dono: be-integrations (adendo 8). Estende ``app.core.llm`` (fábrica por
ambiente) com a capacidade de construir um client a partir de uma **conexão
cadastrada** na tela Integrações (tipo ``llm``), e de montar o bloco ``llm``
que o orquestrador envia ao worker em ``POST /execute``.

Tipos de provedor (adendo 8.2):
- ``openai``: OpenAI real (``api.openai.com``).
- ``openai_compatible``: servidor compatível (LM Studio, Ollama, vLLM,
  OpenRouter, Azure OpenAI e similares), via ``base_url``.
- ``mock``: desenvolvimento/testes (respostas determinísticas, sem rede).

Segredos (adendo 8.2): a chave de API é criptografada em repouso (Fernet,
``api_key_encrypted``); nunca volta na API (só ``api_key_hint``), é mascarada
nos logs e nunca aparece em mensagens de erro. O bloco ``llm`` enviado ao
worker carrega a chave em claro (o worker não tem banco nem segredos), mas
NUNCA é persistido em run, checkpoint, log nem evento WebSocket.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.llm import (
    LOCAL_API_KEY_PLACEHOLDER,
    LLMClient,
    MockLLMClient,
    OpenAILLMClient,
)

# Tipos de provedor suportados (adendo 8.2).
PROVIDER_KINDS = ("openai", "openai_compatible", "mock")


@dataclass
class LLMConnection:
    """Conexão de LLM resolvida (chave já em claro, pronta para uso).

    ``provider_kind``: ``openai`` | ``openai_compatible`` | ``mock``.
    ``api_key``: chave em claro (vazia para ``mock`` e para servidores locais
    compatíveis que aceitam qualquer chave).
    """

    provider_kind: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""


def build_llm_client(connection: LLMConnection) -> LLMClient:
    """Constrói um ``LLMClient`` a partir de uma conexão resolvida.

    - ``mock`` -> ``MockLLMClient`` (sem rede).
    - ``openai`` / ``openai_compatible`` -> ``OpenAILLMClient`` (o SDK aceita
      qualquer chave; servidor local usa o placeholder).
    """
    if connection.provider_kind == "mock":
        return MockLLMClient()
    return OpenAILLMClient(
        api_key=connection.api_key or LOCAL_API_KEY_PLACEHOLDER,
        base_url=connection.base_url or None,
        model=connection.model,
    )


def build_worker_llm_block(connection: LLMConnection) -> dict[str, Any]:
    """Monta o bloco ``llm`` enviado ao worker em ``POST /execute``.

    Formato (adendo 8.2): ``{kind, baseUrl, apiKey, model}``. O worker usa este
    bloco no lugar das variáveis de ambiente (que permanecem como fallback).
    O bloco NUNCA é persistido em run, checkpoint, log nem evento WebSocket.
    """
    return {
        "kind": connection.provider_kind,
        "baseUrl": connection.base_url or "",
        "apiKey": connection.api_key or "",
        "model": connection.model or "",
    }


def connection_from_config(config: dict[str, Any], api_key: str = "") -> LLMConnection:
    """Monta um ``LLMConnection`` a partir do ``config`` de uma integração.

    ``api_key`` é a chave em claro (já descriptografada do
    ``api_key_encrypted``); quando ausente, usa o valor em claro do config
    (caso do teste sem salvar, em que o cliente acabou de digitar).
    """
    kind = str(config.get("provider_kind") or "mock")
    if kind not in PROVIDER_KINDS:
        kind = "mock"
    base_url = str(config.get("base_url") or "")
    key = api_key or str(config.get("api_key") or "")
    model = str(config.get("default_model") or config.get("model") or "")
    return LLMConnection(
        provider_kind=kind,
        base_url=base_url,
        api_key=key,
        model=model,
    )


def env_llm_connection() -> LLMConnection:
    """Conexão a partir das variáveis de ambiente (fallback do adendo 8).

    Espelha ``get_llm_client()``: provider real com ``LLM_PROVIDER=openai`` e
    chave ou URL configurada; senão ``mock``. O ``LLM_MODEL`` só vale quando
    não há escolha explícita (agente/usuário) — ver ``resolve_llm_connection``.
    """
    if settings.llm_provider == "openai" and (
        settings.openai_api_key or settings.openai_base_url
    ):
        return LLMConnection(
            provider_kind="openai",
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=settings.llm_model,
        )
    return LLMConnection(provider_kind="mock", model=settings.llm_model)


def resolve_llm_connection(
    agent_llm: dict[str, Any] | None,
    user_preferences: dict[str, Any] | None,
    llm_integrations: dict[str, dict[str, Any]],
) -> LLMConnection | None:
    """Resolve a conexão de LLM efetiva (precedência do adendo 8.2).

    1) escolha no agente (``agent_llm = {integrationId, model}``);
    2) padrão do usuário (``user_preferences['default_llm_integration_id']``);
    3) padrão do ambiente (``env_llm_connection``).

    ``llm_integrations`` mapeia ``str(integrationId) -> config`` (com a chave
    já descriptografada em ``api_key``). Retorna ``None`` quando não há
    conexão escolhida e o ambiente também não tem provider real (o caller usa
    o fallback ``get_llm_client()``).

    O ``LLM_MODEL`` do ambiente deixa de sobrescrever um modelo escolhido
    explicitamente: só vale quando não há escolha (regra 3).
    """
    # 1) escolha no agente.
    if agent_llm:
        integration_id = str(agent_llm.get("integrationId") or "")
        config = llm_integrations.get(integration_id)
        if config is not None:
            conn = connection_from_config(config)
            # O modelo escolhido no agente tem precedência sobre o padrão da
            # conexão (adendo 8.4: se o modelo some da conexão, usa o padrão).
            chosen_model = str(agent_llm.get("model") or "")
            if chosen_model:
                conn.model = chosen_model
            return conn

    # 2) padrão do usuário.
    if user_preferences:
        default_id = str(user_preferences.get("default_llm_integration_id") or "")
        config = llm_integrations.get(default_id)
        if config is not None:
            return connection_from_config(config)

    # 3) padrão do ambiente.
    return env_llm_connection()
