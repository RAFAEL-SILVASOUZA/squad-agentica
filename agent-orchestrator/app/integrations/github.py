"""GitHub integration client (V1: read-only).

Dono: be-integrations (FASE 4). Spec 8.1.

Operações expostas ao agente como tools:
- list_repos(owner)
- list_pulls(owner, repo, state?)
- list_issues(owner, repo, state?, labels?)
- get_pr_diff(owner, repo, number)

Segurança (spec 14.1):
- Token é lido de env GITHUB_TOKEN (PAT com escopo repo:read).
- Nunca retornado pela API, nunca logado.
- Conteúdo externo delimitado com marcadores EXTERNAL_DATA.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# Marcadores de dados externos (spec 14.1)
EXTERNAL_DATA_START = "<<<EXTERNAL_DATA>>>"
EXTERNAL_DATA_END = "<<<END_EXTERNAL_DATA>>>"


def wrap_external_data(content: str) -> str:
    """Delimita conteúdo externo com os marcadores da spec 14.1.

    O worker usa este helper para injetar conteúdo do GitHub no prompt
    do agente sem risco de prompt injection.
    """
    return f"{EXTERNAL_DATA_START}\n{content}\n{EXTERNAL_DATA_END}"


def _get_token() -> str:
    """Retorna o GITHUB_TOKEN do ambiente.

    Raises:
        AppError(502, "github_error"): se o token não está configurado.
    """
    from app.core.config import settings
    from app.core.errors import AppError

    token = settings.github_token
    if not token:
        raise AppError(
            502,
            "github error",
            "github_error",
            {"message": "GITHUB_TOKEN não configurado no ambiente."},
        )
    return token


def _headers(token: str) -> dict[str, str]:
    """Headers para a API do GitHub."""
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _raise_for_github_error(response: httpx.Response) -> None:
    """Converte erros da API do GitHub em AppError.

    - 401: token inválido
    - 403: rate limit ou sem permissão
    - 404: recurso não encontrado
    - 422: validação
    - outros: erro genérico
    """
    from app.core.errors import AppError

    if response.status_code == 401:
        raise AppError(
            502,
            "github error",
            "github_error",
            {"message": "Token GitHub inválido ou expirado."},
        )
    if response.status_code == 403:
        # Rate limit: o header X-RateLimit-Remaining será 0
        remaining = response.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            reset = response.headers.get("X-RateLimit-Reset", "")
            raise AppError(
                502,
                "github error",
                "github_error",
                {
                    "message": "Rate limit do GitHub atingido.",
                    "retryAfter": int(reset) if reset.isdigit() else None,
                },
            )
        raise AppError(
            502,
            "github error",
            "github_error",
            {"message": "Acesso negado pela API do GitHub (sem permissão)."},
        )
    if response.status_code == 404:
        raise AppError(
            404,
            "not found",
            "github_resource_not_found",
            {"message": "Recurso não encontrado no GitHub."},
        )
    if response.status_code >= 400:
        raise AppError(
            502,
            "github error",
            "github_error",
            {"message": f"Erro na API do GitHub (HTTP {response.status_code})."},
        )


async def list_repos(owner: str) -> list[dict[str, Any]]:
    """Lista repositórios do owner.

    Returns:
        [{id, name, full_name, private}]
    """
    token = _get_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/users/{owner}/repos",
            headers=_headers(token),
            params={"per_page": 100},
        )
    _raise_for_github_error(response)
    data = response.json()
    return [
        {
            "id": repo["id"],
            "name": repo["name"],
            "full_name": repo["full_name"],
            "private": repo["private"],
        }
        for repo in data
    ]


async def list_pulls(
    owner: str, repo: str, state: str | None = None
) -> list[dict[str, Any]]:
    """Lista pull requests de um repositório.

    Args:
        owner: nome do owner/organização.
        repo: nome do repositório.
        state: filtro de estado (open, closed, all). Default: open.

    Returns:
        [{number, title, state, author, url}]
    """
    token = _get_token()
    params: dict[str, str] = {"per_page": 100}
    if state:
        params["state"] = state

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
            headers=_headers(token),
            params=params,
        )
    _raise_for_github_error(response)
    data = response.json()
    return [
        {
            "number": pr["number"],
            "title": pr["title"],
            "state": pr["state"],
            "author": pr["user"]["login"],
            "url": pr["html_url"],
        }
        for pr in data
    ]


async def list_issues(
    owner: str,
    repo: str,
    state: str | None = None,
    labels: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Lista issues de um repositório.

    Args:
        owner: nome do owner/organização.
        repo: nome do repositório.
        state: filtro de estado (open, closed, all). Default: open.
        labels: filtro por labels.

    Returns:
        [{number, title, state, labels, author, url}]
    """
    token = _get_token()
    params: dict[str, str] = {"per_page": 100}
    if state:
        params["state"] = state
    if labels:
        params["labels"] = ",".join(labels)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
            headers=_headers(token),
            params=params,
        )
    _raise_for_github_error(response)
    data = response.json()
    return [
        {
            "number": issue["number"],
            "title": issue["title"],
            "state": issue["state"],
            "labels": [label["name"] for label in issue.get("labels", [])],
            "author": issue["user"]["login"],
            "url": issue["html_url"],
        }
        for issue in data
    ]


async def get_pr_diff(owner: str, repo: str, number: int) -> dict[str, Any]:
    """Obtém o diff de uma pull request.

    Args:
        owner: nome do owner/organização.
        repo: nome do repositório.
        number: número da PR.

    Returns:
        {diff: str, files: [{path, additions, deletions}]}
    """
    token = _get_token()
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Obter o diff
        response = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{number}",
            headers={**_headers(token), "Accept": "application/vnd.github.diff"},
        )
    _raise_for_github_error(response)
    diff_text = response.text

    # Obter os arquivos da PR
    async with httpx.AsyncClient(timeout=30.0) as client:
        response_files = await client.get(
            f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{number}/files",
            headers=_headers(token),
            params={"per_page": 100},
        )
    _raise_for_github_error(response_files)
    files_data = response_files.json()

    files = [
        {
            "path": f["filename"],
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
        }
        for f in files_data
    ]

    return {"diff": diff_text, "files": files}
