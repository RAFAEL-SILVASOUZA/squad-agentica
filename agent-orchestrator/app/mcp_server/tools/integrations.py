"""Ferramentas MCP de integrações (CRUD + teste de conexão).

Registra as ferramentas de gerenciamento de integrações no servidor MCP.
Cada ferramenta lê o usuário autenticado via ``get_current_mcp_user`` e
delega a operação ao ``IntegrationRegistry``.

Erros do registry (``AppError``) e de parsing de UUID são convertidos em
``ToolError`` com mensagem amigável em pt-BR para o cliente MCP.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import Any

from app.core.errors import AppError
from app.core.secrets import SecretError, decrypt_secret, encrypt_secret
from app.db.models import Integration
from app.db.session import async_session_factory
from app.integrations.git_providers import GitProviderError, provider_for
from app.integrations.registry import IntegrationRegistry
from app.mcp_server.context import get_current_mcp_user
from app.mcp_server.server import mcp
from app.mcp_server.tools import ToolError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MASKED = "***"

# Chaves de config que são segredo (F12/contrato §8: nunca devolvidas).
_SECRET_KEYS = ("token", "secret", "password", "key", "credentials", "auth")


def _parse_uuid(value: str) -> uuid.UUID:
    """Converte string para UUID, lançando ToolError amigável se inválido."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ToolError("ID inválido.") from None


def _key_hint(api_key: str) -> str:
    """Últimos 4 caracteres da chave de API, no formato '…a1b2'."""
    if len(api_key) < 4:
        return "…"
    return f"…{api_key[-4:]}"


def _seal_config(config: dict[str, Any]) -> dict[str, Any]:
    """Troca segredos em claro por suas versões criptografadas (Fernet).

    - ``token`` (Git) -> ``token_encrypted``.
    - ``api_key`` (LLM) -> ``api_key_encrypted`` + ``api_key_hint``.
    - ``embedding.api_key`` -> ``embedding.api_key_encrypted``.
    """
    sealed = dict(config)
    token = sealed.pop("token", None)
    if token and token != _MASKED:
        try:
            sealed["token_encrypted"] = encrypt_secret(str(token))
        except SecretError as exc:
            raise AppError(500, "internal error", "secret_key_missing") from exc
    api_key = sealed.pop("api_key", None)
    if api_key and api_key != _MASKED:
        try:
            sealed["api_key_encrypted"] = encrypt_secret(str(api_key))
            sealed["api_key_hint"] = _key_hint(str(api_key))
        except SecretError as exc:
            raise AppError(500, "internal error", "secret_key_missing") from exc
    # O embedding pode ter a própria chave: criptografa embedding.api_key.
    emb = sealed.get("embedding")
    if isinstance(emb, dict):
        emb_api_key = emb.pop("api_key", None)
        if emb_api_key and emb_api_key != _MASKED:
            try:
                emb["api_key_encrypted"] = encrypt_secret(str(emb_api_key))
            except SecretError as exc:
                raise AppError(500, "internal error", "secret_key_missing") from exc
        sealed["embedding"] = emb
    return sealed


def _mask_embedding(emb: dict[str, Any]) -> dict[str, Any]:
    """Mascara a chave de API aninhada no objeto de embedding."""
    out: dict[str, Any] = {}
    for ek, ev in emb.items():
        if ek == "api_key_encrypted":
            if ev:
                out["api_key"] = _MASKED
            continue
        if ek == "api_key":
            out[ek] = _MASKED
            continue
        out[ek] = ev
    return out


def _mask_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Mascara os valores de segredo no config (F12).

    Regra: qualquer chave que contenha token/secret/password/key/credentials/
    auth (case-insensitive) vira ``***``; o resto permanece legível.
    ``token_encrypted`` aparece como ``token: "***"``.
    ``api_key_encrypted`` nunca sai da API.
    """
    masked: dict[str, Any] = {}
    for k, v in (config or {}).items():
        if k == "token_encrypted":
            if v:
                masked["token"] = _MASKED
            continue
        if k == "api_key_encrypted":
            continue
        if k == "embedding" and isinstance(v, dict):
            masked[k] = _mask_embedding(v)
            continue
        lower = k.lower()
        if any(s in lower for s in _SECRET_KEYS):
            masked[k] = _MASKED
        else:
            masked[k] = v
    return masked


def _token_hint(config: dict[str, Any] | None) -> str | None:
    """Últimos 4 caracteres do token, no formato '…a1b2'."""
    cfg = config or {}
    token_enc = cfg.get("token_encrypted")
    if not token_enc:
        return None
    try:
        token = decrypt_secret(token_enc)
    except SecretError:
        return None
    if len(token) < 4:
        return "…"
    return f"…{token[-4:]}"


def _api_key_hint(config: dict[str, Any] | None) -> str | None:
    """Últimos 4 caracteres da chave de API LLM."""
    cfg = config or {}
    if cfg.get("api_key_hint"):
        return str(cfg["api_key_hint"])
    if cfg.get("api_key_encrypted"):
        try:
            return _key_hint(decrypt_secret(cfg["api_key_encrypted"]))
        except SecretError:
            return None
    return None


def _integration_to_dict(integration: Integration) -> dict[str, Any]:
    """Converte o model Integration para dict (camelCase, como a API)."""
    type_val = (
        integration.type.value
        if hasattr(integration.type, "value")
        else str(integration.type)
    )
    status_val = (
        integration.status.value
        if hasattr(integration.status, "value")
        else str(integration.status)
    )
    cfg = integration.config or {}
    return {
        "id": str(integration.id),
        "type": type_val,
        "name": integration.name,
        "config": _mask_config(cfg),
        "status": status_val,
        "createdAt": integration.created_at.isoformat() if integration.created_at else "",
        "updatedAt": integration.updated_at.isoformat() if integration.updated_at else "",
        "tokenHint": _token_hint(cfg),
        "apiKeyHint": _api_key_hint(cfg),
        "lastTestStatus": cfg.get("last_test_status"),
        "lastTestedAt": cfg.get("last_tested_at"),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_integration(
    type: str,
    name: str,
    config: dict[str, Any] | None = None,
    status: str = "active",
) -> dict[str, Any]:
    """Cria uma nova integração.

    Tipos suportados: 'github', 'azure', 'llm', 'embedding'.
    Segredos no config (token, api_key) são criptografados antes de persistir.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    sealed_config = _seal_config(config or {})

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            integration = await registry.create(
                owner_id=user.id,
                type=type,
                name=name,
                config=sealed_config,
                status=status,
            )
        except AppError as e:
            raise ToolError(f"Erro ao criar integração: {e.error}") from e
        return _integration_to_dict(integration)


@mcp.tool()
async def list_integrations(
    page: int = 1,
    limit: int = 50,
    type: str | None = None,
) -> dict[str, Any]:
    """Lista as integrações do usuário autenticado, com paginação e filtro opcional por tipo."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            items, total = await registry.list(
                owner_id=user.id,
                page=page,
                limit=limit,
                type_filter=type,
            )
        except AppError as e:
            raise ToolError(f"Erro ao listar integrações: {e.error}") from e
        return {
            "items": [_integration_to_dict(i) for i in items],
            "total": total,
            "page": page,
            "limit": limit,
        }


@mcp.tool()
async def get_integration(integration_id: str) -> dict[str, Any]:
    """Obtém uma integração por id (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(integration_id)

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            integration = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Integração não encontrada: {e.error}") from e
        return _integration_to_dict(integration)


@mcp.tool()
async def update_integration(
    integration_id: str,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Atualiza uma integração (partial update: só os campos informados são alterados).

    Se config for fornecido, faz merge com o config existente. Chaves com
    valor '***' mantêm o valor real gravado. O embedding é mergeado
    preservando a api_key_encrypted existente.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(integration_id)

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            existing = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Integração não encontrada: {e.error}") from e

        config_to_save = None
        if config is not None:
            existing_config = existing.config or {}
            merged = dict(existing_config)
            for k, v in config.items():
                # token/api_key mascarados significam "manter o valor atual"
                if k in ("token", "api_key") and v == _MASKED:
                    continue
                if k == "embedding" and isinstance(v, dict):
                    existing_emb = existing_config.get("embedding") or {}
                    emb_merged = dict(existing_emb)
                    emb_merged.update(v)
                    if "api_key" not in v or v.get("api_key") == _MASKED:
                        emb_merged.pop("api_key", None)
                        if existing_emb.get("api_key_encrypted"):
                            emb_merged["api_key_encrypted"] = existing_emb["api_key_encrypted"]
                    merged[k] = emb_merged
                    continue
                if v == _MASKED and k in existing_config:
                    merged[k] = existing_config[k]
                else:
                    merged[k] = v
            config_to_save = _seal_config(merged)

        try:
            integration = await registry.update(
                integration_id=parsed_id,
                owner_id=user.id,
                name=name,
                config=config_to_save,
                status=status,
            )
        except AppError as e:
            raise ToolError(f"Erro ao atualizar integração: {e.error}") from e
        return _integration_to_dict(integration)


@mcp.tool()
async def delete_integration(integration_id: str) -> dict[str, Any]:
    """Remove uma integração (somente se pertencer ao usuário autenticado)."""
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(integration_id)

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            await registry.delete(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Integração não encontrada: {e.error}") from e
        return {"deleted": True, "id": integration_id}


@mcp.tool()
async def test_integration(integration_id: str) -> dict[str, Any]:
    """Testa a conexão de uma integração e grava last_test_status.

    - github/azure: lista repositórios via provider.
    - llm: faz uma chamada mínima de chat.
    - embedding: faz uma chamada mínima de embedding.
    """
    user = get_current_mcp_user()
    if user is None:
        raise ToolError("Não autenticado.")

    parsed_id = _parse_uuid(integration_id)

    async with async_session_factory() as db:
        registry = IntegrationRegistry(db)
        try:
            integration = await registry.get(parsed_id, user.id)
        except AppError as e:
            raise ToolError(f"Integração não encontrada: {e.error}") from e

        type_val = (
            integration.type.value
            if hasattr(integration.type, "value")
            else str(integration.type)
        )
        cfg = integration.config or {}

        try:
            if type_val in ("github", "azure"):
                provider = provider_for(integration)
                repos = await provider.list_repos()
                result: dict[str, Any] = {"ok": True, "repositories": len(repos)}

            elif type_val == "llm":
                from app.core.llm_providers import (
                    PROVIDER_KINDS,
                    build_llm_client,
                    connection_from_config,
                )

                kind = str(cfg.get("provider_kind") or "mock")
                if kind not in PROVIDER_KINDS:
                    result = {"ok": False, "error": "provider_kind inválido"}
                else:
                    # Descriptografa a chave se necessário.
                    api_key = ""
                    if cfg.get("api_key_encrypted"):
                        try:
                            api_key = decrypt_secret(cfg["api_key_encrypted"])
                        except SecretError:
                            pass
                    connection = connection_from_config(cfg, api_key=api_key)
                    client = build_llm_client(connection)
                    model = str(cfg.get("default_model") or cfg.get("model") or connection.model or "")
                    start = time.monotonic()
                    await client.chat([{"role": "user", "content": "ping"}], model=model or None)
                    latency_ms = int((time.monotonic() - start) * 1000)
                    result = {"ok": True, "latencyMs": latency_ms, "model": model or None}

            elif type_val == "embedding":
                from app.core.embeddings import OpenAIEmbedder
                from app.core.llm import LOCAL_API_KEY_PLACEHOLDER

                model = str(cfg.get("model") or "")
                if not model:
                    result = {"ok": False, "error": "informe o modelo de embedding"}
                else:
                    api_key = ""
                    if cfg.get("api_key_encrypted"):
                        try:
                            api_key = decrypt_secret(cfg["api_key_encrypted"])
                        except SecretError:
                            pass
                    embedder = OpenAIEmbedder(
                        api_key=api_key or LOCAL_API_KEY_PLACEHOLDER,
                        dim=int(cfg.get("dim") or 1536),
                        base_url=str(cfg.get("base_url") or ""),
                        model=model,
                        query_prefix=str(cfg.get("query_prefix") or ""),
                        document_prefix=str(cfg.get("document_prefix") or ""),
                    )
                    start = time.monotonic()
                    vec = embedder.embed("ping")
                    latency_ms = int((time.monotonic() - start) * 1000)
                    result = {
                        "ok": True,
                        "latencyMs": latency_ms,
                        "model": model,
                        "embeddingDim": len(vec),
                    }

            else:
                result = {"ok": False, "error": f"Tipo '{type_val}' não suporta teste de conexão"}

        except GitProviderError as e:
            result = {"ok": False, "error": e.message}
        except Exception as e:
            result = {"ok": False, "error": str(e)}

        # Grava o resultado do teste no config.
        cfg = dict(integration.config or {})
        cfg["last_test_status"] = "ok" if result.get("ok") else "failed"
        cfg["last_tested_at"] = datetime.now(UTC).isoformat()
        integration.config = cfg
        await db.commit()

        return result
