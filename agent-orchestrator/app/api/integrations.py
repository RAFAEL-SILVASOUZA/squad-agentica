"""Integrations API router.

Dono: be-integrations (FASE 4). Rotas (prefixo /api):
- GET /api/integrations → 200 {items, total, page, limit}
- POST /api/integrations → 201 Integration
- GET /api/integrations/{id} → 200 Integration / 404
- PUT /api/integrations/{id} → 200 Integration / 404
- DELETE /api/integrations/{id} → 204 / 404
- GET /api/integrations/github/repos → 200 {repos} / 404 / 502
- GET /api/integrations/github/repos/{owner}/{repo}/pulls → 200 {pulls}
- GET /api/integrations/github/repos/{owner}/{repo}/issues → 200 {issues}
- GET /api/integrations/rivvn/authorize → 307 / 403
- GET /api/integrations/rivvn/callback → 200 / 400 / 403
- GET /api/integrations/rivvn/status → 200 / 403
- DELETE /api/integrations/rivvn → 204 / 404
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.errors import AppError
from app.core.secrets import SecretError, decrypt_secret, encrypt_secret
from app.db.models import Integration, User
from app.db.session import get_db
from app.integrations import github as github_client
from app.integrations.registry import IntegrationRegistry

router = APIRouter(prefix="/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class IntegrationCreateRequest(BaseModel):
    """Body para POST /api/integrations."""

    type: str = Field(..., pattern="^(github|azure|gitlab)$")
    name: str = Field(..., min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)
    status: str = Field(default="active", pattern="^(active|disabled)$")


class IntegrationUpdateRequest(BaseModel):
    """Body para PUT /api/integrations/{id}. Todos os campos opcionais."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    config: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class IntegrationResponse(BaseModel):
    """Response para uma integração."""

    id: uuid.UUID
    ownerId: str
    type: str
    name: str
    config: dict[str, Any]
    status: str
    createdAt: str
    updatedAt: str


class IntegrationListResponse(BaseModel):
    """Response para listagem de integrações."""

    items: list[IntegrationResponse]
    total: int
    page: int
    limit: int


class GithubReposResponse(BaseModel):
    """Response para listagem de repos."""

    repos: list[dict[str, Any]]


class GithubPullsResponse(BaseModel):
    """Response para listagem de PRs."""

    pulls: list[dict[str, Any]]


class GithubIssuesResponse(BaseModel):
    """Response para listagem de issues."""

    issues: list[dict[str, Any]]


class RivvnStatusResponse(BaseModel):
    """Response para status do Rivvn."""

    connected: bool
    contractStatus: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_MASKED = "***"

# Chaves de config que são segredo (F12/contrato §8: nunca devolvidas).
_SECRET_KEYS = {"token", "secret", "password", "api_key", "apikey", "credentials", "auth"}


def _mask_config(config: dict[str, Any] | None) -> dict[str, Any]:
    """Mascara os valores de segredo no config (F12).

    Regra: qualquer chave que contenha ``token``/``secret``/``password``/
    ``key``/``credentials``/``auth`` (case-insensitive) vira ``***``; o resto
    do config (ex.: ``owner``) permanece legível. ``token_encrypted`` nunca
    sai da API: aparece para o cliente como ``token: "***"``.
    """
    masked: dict[str, Any] = {}
    for k, v in (config or {}).items():
        if k == "token_encrypted":
            if v:
                masked["token"] = _MASKED
            continue
        lower = k.lower()
        if any(s in lower for s in _SECRET_KEYS):
            masked[k] = _MASKED
        else:
            masked[k] = v
    return masked


def _seal_config(config: dict[str, Any]) -> dict[str, Any]:
    """Troca ``token`` em claro por ``token_encrypted`` (Fernet)."""
    sealed = dict(config)
    token = sealed.pop("token", None)
    if token and token != _MASKED:
        try:
            sealed["token_encrypted"] = encrypt_secret(str(token))
        except SecretError as exc:
            raise AppError(500, "internal error", "secret_key_missing") from exc
    return sealed


def get_integration_token(integration: Integration) -> str:
    """Token em claro para uso interno (nunca devolver ao cliente)."""
    cfg = integration.config or {}
    if cfg.get("token_encrypted"):
        try:
            return decrypt_secret(cfg["token_encrypted"])
        except SecretError as exc:
            raise AppError(500, "internal error", "secret_key_missing") from exc
    return str(cfg.get("token", ""))


async def seal_legacy_token(db: AsyncSession, integration: Integration) -> None:
    """Spec §3: token antigo em claro passa a ser criptografado na primeira leitura."""
    cfg = integration.config or {}
    if cfg.get("token") and not cfg.get("token_encrypted"):
        integration.config = _seal_config(cfg)
        await db.commit()
        await db.refresh(integration)


def _to_response(integration: Any) -> IntegrationResponse:
    """Converte um model Integration em IntegrationResponse (camelCase)."""
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
    return IntegrationResponse(
        id=integration.id,
        ownerId=str(integration.owner_id),
        type=type_val,
        name=integration.name,
        config=_mask_config(integration.config),
        status=status_val,
        createdAt=integration.created_at.isoformat() if integration.created_at else "",
        updatedAt=integration.updated_at.isoformat() if integration.updated_at else "",
    )


# ---------------------------------------------------------------------------
# CRUD Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=IntegrationListResponse)
async def list_integrations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    type: str | None = Query(default=None, alias="type"),
) -> IntegrationListResponse:
    """Lista integrações do usuário."""
    registry = IntegrationRegistry(db)
    items, total = await registry.list(
        user.id, page=page, limit=limit, type_filter=type
    )
    for item in items:
        await seal_legacy_token(db, item)
    return IntegrationListResponse(
        items=[_to_response(i) for i in items],
        total=total,
        page=page,
        limit=limit,
    )


@router.post("", response_model=IntegrationResponse, status_code=201)
async def create_integration(
    body: IntegrationCreateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationResponse:
    """Cria uma integração."""
    registry = IntegrationRegistry(db)
    integration = await registry.create(
        owner_id=user.id,
        type=body.type,
        name=body.name,
        config=_seal_config(body.config),
        status=body.status,
    )
    return _to_response(integration)


@router.get("/{integration_id}", response_model=IntegrationResponse)
async def get_integration(
    integration_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationResponse:
    """Obtém uma integração por id."""
    registry = IntegrationRegistry(db)
    integration = await registry.get(integration_id, user.id)
    await seal_legacy_token(db, integration)
    return _to_response(integration)


@router.put("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(
    integration_id: uuid.UUID,
    body: IntegrationUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IntegrationResponse:
    """Atualiza uma integração."""
    registry = IntegrationRegistry(db)
    # F12: o valor mascarado (``***``) devolvido por uma chave existente
    # significa "não mexer" (o valor real nunca é exposto, então é assim que
    # o cliente expressa a inalteração). ``token`` é tratado à parte: o valor
    # real vive em ``token_encrypted`` (nunca em ``token``), então
    # ``token: "***"`` significa "manter o token_encrypted atual".
    config_to_save = body.config
    if body.config is not None:
        existing = await registry.get(integration_id, user.id)
        existing_config = existing.config or {}
        merged = dict(existing_config)
        for k, v in body.config.items():
            if k == "token" and v == _MASKED:
                continue
            if v == _MASKED and k in existing_config:
                merged[k] = existing_config[k]
            else:
                merged[k] = v
        config_to_save = _seal_config(merged)
    integration = await registry.update(
        integration_id=integration_id,
        owner_id=user.id,
        name=body.name,
        config=config_to_save,
        status=body.status,
    )
    return _to_response(integration)


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove uma integração."""
    registry = IntegrationRegistry(db)
    await registry.delete(integration_id, user.id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# GitHub Routes
# ---------------------------------------------------------------------------


@router.get("/github/repos", response_model=GithubReposResponse)
async def github_list_repos(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GithubReposResponse:
    """Lista repos do owner configurado na integração GitHub."""
    registry = IntegrationRegistry(db)
    integration = await registry.get_github_integration(user.id)
    owner = integration.config.get("owner", "")
    if not owner:
        raise AppError(
            400,
            "validation error",
            "invalid_config",
            {"message": "Integração GitHub sem 'owner' configurado."},
        )
    repos = await github_client.list_repos(owner)
    return GithubReposResponse(repos=repos)


@router.get("/github/repos/{owner}/{repo}/pulls", response_model=GithubPullsResponse)
async def github_list_pulls(
    owner: str,
    repo: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    state: str | None = Query(default=None, pattern="^(open|closed|all)$"),
) -> GithubPullsResponse:
    """Lista PRs de um repositório."""
    registry = IntegrationRegistry(db)
    await registry.get_github_integration(user.id)
    pulls = await github_client.list_pulls(owner, repo, state=state)
    return GithubPullsResponse(pulls=pulls)


@router.get("/github/repos/{owner}/{repo}/issues", response_model=GithubIssuesResponse)
async def github_list_issues(
    owner: str,
    repo: str,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    state: str | None = Query(default=None, pattern="^(open|closed|all)$"),
    labels: str | None = Query(default=None, description="Comma-separated labels"),
) -> GithubIssuesResponse:
    """Lista issues de um repositório."""
    registry = IntegrationRegistry(db)
    await registry.get_github_integration(user.id)
    label_list = (
        [item.strip() for item in labels.split(",") if item.strip()]
        if labels
        else None
    )
    issues = await github_client.list_issues(owner, repo, state=state, labels=label_list)
    return GithubIssuesResponse(issues=issues)


# ---------------------------------------------------------------------------
# Rivvn Routes (V1: gate comercial, fora do caminho crítico)
# ---------------------------------------------------------------------------


@router.get("/rivvn/authorize")
async def rivvn_authorize(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Inicia o fluxo OAuth do Rivvn.

    V1: sempre retorna 403 (contrato comercial não ativo).
    """
    from sqlalchemy import select

    from app.db.models import RivvnConnection

    result = await db.execute(
        select(RivvnConnection).where(RivvnConnection.owner_id == user.id)
    )
    connection = result.scalar_one_or_none()

    if connection is None or connection.contract_status != "active":
        raise AppError(
            403,
            "forbidden",
            "rivvn_contract_inactive",
            {
                "message": (
                    "Rivvn não está disponível na V1 (requer contrato comercial ativo). "
                    "Entre em contato com o time comercial."
                )
            },
        )

    # Se chegar aqui (V2), redireciona para o OAuth do Rivvn.
    from app.core.config import settings

    auth_url = (
        f"{settings.rivvn_base_url}/oauth/authorize"
        f"?client_id={settings.rivvn_client_id}"
        f"&redirect_uri={settings.rivvn_redirect_uri}"
        f"&response_type=code"
    )
    return Response(status_code=307, headers={"Location": auth_url})


@router.get("/rivvn/callback")
async def rivvn_callback(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    code: str | None = Query(default=None),
) -> dict[str, str]:
    """Callback do OAuth do Rivvn.

    V1: sempre retorna 403 (contrato comercial não ativo).
    """
    from sqlalchemy import select

    from app.db.models import RivvnConnection

    result = await db.execute(
        select(RivvnConnection).where(RivvnConnection.owner_id == user.id)
    )
    connection = result.scalar_one_or_none()

    if connection is None or connection.contract_status != "active":
        raise AppError(
            403,
            "forbidden",
            "rivvn_contract_inactive",
            {
                "message": (
                    "Rivvn não está disponível na V1 (requer contrato comercial ativo)."
                )
            },
        )

    if not code:
        raise AppError(400, "bad request", "invalid_code", {"message": "Code ausente."})

    # V2: trocar code por token via SDK do Rivvn.
    return {"status": "ok"}


@router.get("/rivvn/status", response_model=RivvnStatusResponse)
async def rivvn_status(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RivvnStatusResponse:
    """Status da conexão Rivvn do usuário."""
    from sqlalchemy import select

    from app.db.models import RivvnConnection

    result = await db.execute(
        select(RivvnConnection).where(RivvnConnection.owner_id == user.id)
    )
    connection = result.scalar_one_or_none()

    if connection is None:
        return RivvnStatusResponse(connected=False, contractStatus="inactive")

    contract_status = str(connection.contract_status)
    connected = connection.status == "connected"

    return RivvnStatusResponse(connected=connected, contractStatus=contract_status)


@router.delete("/rivvn", status_code=204)
async def rivvn_disconnect(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Desconecta o Rivvn (remove a conexão)."""
    from sqlalchemy import select

    from app.db.models import RivvnConnection

    result = await db.execute(
        select(RivvnConnection).where(RivvnConnection.owner_id == user.id)
    )
    connection = result.scalar_one_or_none()

    if connection is None:
        raise AppError(404, "not found", "integration_not_found")

    await db.delete(connection)
    await db.commit()
    return Response(status_code=204)
