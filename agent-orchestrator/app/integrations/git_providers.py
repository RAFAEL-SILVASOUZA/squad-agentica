"""Provedores Git (GitHub e Azure DevOps) para clonar, publicar e abrir PR.

O token só existe aqui e em URLs de clone montadas para o subprocesso git;
mensagens de erro nunca o incluem.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import quote

import httpx

# Teto de páginas seguidas nas listagens (100 itens por página no GitHub).
MAX_PAGES = 10


class GitProviderError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class Repo:
    full_name: str
    default_branch: str


@dataclass
class PullRequest:
    number: int
    url: str


class GitProvider(Protocol):
    async def list_repos(self) -> list[Repo]: ...
    async def list_branches(self, repo: str) -> list[str]: ...
    def clone_url(self, repo: str) -> str: ...
    def public_url(self, repo: str) -> str: ...
    async def create_pull_request(
        self, repo: str, head: str, base: str, title: str, body: str
    ) -> PullRequest: ...
    async def find_open_pull_request(self, repo: str, head: str) -> PullRequest | None: ...


def _raise_for(resp: httpx.Response, what: str) -> None:
    if resp.status_code in (401, 403):
        raise GitProviderError(f"{what}: token inválido ou sem acesso")
    if resp.status_code == 404:
        raise GitProviderError(f"{what}: não encontrado (repositório, projeto ou organização)")
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = str(resp.json().get("message", ""))[:200]
        except Exception:  # noqa: BLE001
            pass
        raise GitProviderError(f"{what}: erro {resp.status_code} do provedor {detail}".strip())


class GitHubProvider:
    def __init__(
        self,
        token: str,
        api_base: str = "https://api.github.com",
        transport: httpx.AsyncBaseTransport | None = None,
        clone_base: str = "",
    ) -> None:
        self._token = token
        self._api = api_base.rstrip("/")
        self._transport = transport
        # Remoto local de teste (GIT_CLONE_BASE_OVERRIDE); vazio = GitHub real.
        self._clone_base = clone_base.rstrip("/")
        if "api.github.com" in self._api:
            web = "https://github.com"
        else:
            web = self._api.replace("/api/v3", "")
        self._web = web.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._api,
            transport=self._transport,
            timeout=30,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            },
        )

    async def _get_paginated(
        self, path: str, params: dict[str, Any], what: str
    ) -> list[dict[str, Any]]:
        """GET seguindo o cabeçalho ``Link: <...>; rel="next"`` do GitHub, até
        ``MAX_PAGES`` páginas de 100 (revisão final I5). Só segue links do
        mesmo host da API — o token nunca vai para outro servidor."""
        items: list[dict[str, Any]] = []
        async with self._client() as c:
            url: str | None = path
            query: dict[str, Any] | None = params
            for _ in range(MAX_PAGES):
                r = await c.get(url, params=query)
                _raise_for(r, what)
                data = r.json()
                if isinstance(data, list):
                    items.extend(data)
                nxt = r.links.get("next", {}).get("url")
                if not nxt or not nxt.startswith(self._api + "/"):
                    break
                url, query = nxt, None
        return items

    async def list_repos(self) -> list[Repo]:
        data = await self._get_paginated(
            "/user/repos", {"per_page": 100, "sort": "updated"}, "Listar repositórios"
        )
        return [Repo(x["full_name"], x.get("default_branch") or "main") for x in data]

    async def list_branches(self, repo: str) -> list[str]:
        data = await self._get_paginated(
            f"/repos/{repo}/branches", {"per_page": 100}, "Listar branches"
        )
        return [b["name"] for b in data]

    def clone_url(self, repo: str) -> str:
        if self._clone_base:
            return f"{self._clone_base}/{repo}.git"
        host = self._web.split("://", 1)[1]
        return f"https://x-access-token:{quote(self._token, safe='')}@{host}/{repo}.git"

    def public_url(self, repo: str) -> str:
        return f"{self._web}/{repo}"

    async def create_pull_request(self, repo, head, base, title, body) -> PullRequest:
        async with self._client() as c:
            r = await c.post(f"/repos/{repo}/pulls",
                             json={"title": title, "head": head, "base": base, "body": body})
        _raise_for(r, "Abrir Pull Request")
        d = r.json()
        return PullRequest(int(d["number"]), d["html_url"])

    async def find_open_pull_request(self, repo, head) -> PullRequest | None:
        owner = repo.split("/", 1)[0]
        async with self._client() as c:
            r = await c.get(
                f"/repos/{repo}/pulls",
                params={"head": f"{owner}:{head}", "state": "open"},
            )
        _raise_for(r, "Consultar Pull Request")
        items = r.json()
        return (
            PullRequest(int(items[0]["number"]), items[0]["html_url"])
            if items
            else None
        )


class AzureDevOpsProvider:
    API_VERSION = "7.1"

    def __init__(self, token: str, organization: str,
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._org = organization
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        basic = base64.b64encode(f":{self._token}".encode()).decode()
        return httpx.AsyncClient(base_url="https://dev.azure.com", transport=self._transport,
                                 timeout=30, headers={"Authorization": f"Basic {basic}"})

    @staticmethod
    def _split(repo: str) -> tuple[str, str]:
        project, name = repo.split("/", 1)
        return project, name

    async def list_repos(self) -> list[Repo]:
        async with self._client() as c:
            r = await c.get(f"/{self._org}/_apis/git/repositories",
                            params={"api-version": self.API_VERSION})
        _raise_for(r, "Listar repositórios")
        out = []
        for x in r.json().get("value", []):
            branch = (x.get("defaultBranch") or "refs/heads/main").removeprefix("refs/heads/")
            out.append(Repo(f"{x['project']['name']}/{x['name']}", branch))
        return out

    async def list_branches(self, repo: str) -> list[str]:
        project, name = self._split(repo)
        out: list[str] = []
        token: str | None = None
        async with self._client() as c:
            # Refs paginadas por ``x-ms-continuationtoken`` (revisão final I5).
            for _ in range(MAX_PAGES):
                params = {"filter": "heads/", "api-version": self.API_VERSION, "$top": 1000}
                if token:
                    params["continuationToken"] = token
                r = await c.get(f"/{self._org}/{project}/_apis/git/repositories/{name}/refs",
                                params=params)
                _raise_for(r, "Listar branches")
                out += [
                    x["name"].removeprefix("refs/heads/") for x in r.json().get("value", [])
                ]
                token = r.headers.get("x-ms-continuationtoken")
                if not token:
                    break
        return out

    def clone_url(self, repo: str) -> str:
        project, name = self._split(repo)
        return (f"https://pat:{quote(self._token, safe='')}@dev.azure.com/"
                f"{self._org}/{quote(project)}/_git/{quote(name)}")

    def public_url(self, repo: str) -> str:
        project, name = self._split(repo)
        return f"https://dev.azure.com/{self._org}/{quote(project)}/_git/{quote(name)}"

    async def create_pull_request(self, repo, head, base, title, body) -> PullRequest:
        project, name = self._split(repo)
        async with self._client() as c:
            r = await c.post(
                f"/{self._org}/{project}/_apis/git/repositories/{name}/pullrequests",
                params={"api-version": self.API_VERSION},
                json={"sourceRefName": f"refs/heads/{head}", "targetRefName": f"refs/heads/{base}",
                      "title": title, "description": body[:4000]})
        _raise_for(r, "Abrir Pull Request")
        number = int(r.json()["pullRequestId"])
        return PullRequest(number, f"{self.public_url(repo)}/pullrequest/{number}")

    async def find_open_pull_request(self, repo, head) -> PullRequest | None:
        project, name = self._split(repo)
        async with self._client() as c:
            r = await c.get(
                f"/{self._org}/{project}/_apis/git/repositories/{name}/pullrequests",
                params={"searchCriteria.sourceRefName": f"refs/heads/{head}",
                        "searchCriteria.status": "active", "api-version": self.API_VERSION})
        _raise_for(r, "Consultar Pull Request")
        items = r.json().get("value", [])
        if not items:
            return None
        number = int(items[0]["pullRequestId"])
        return PullRequest(number, f"{self.public_url(repo)}/pullrequest/{number}")


def provider_from_config(
    type_: str,
    config: dict[str, Any],
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GitProvider:
    """Monta um GitProvider a partir de tipo e config (sem registro salvo).

    Usado pelo endpoint de teste antes de salvar. O token vem em claro
    do config (o cliente acabou de digitar).
    """
    from app.core.config import settings

    token = str(config.get("token", ""))
    if type_ == "github":
        return GitHubProvider(
            token, settings.github_api_base, transport,
            clone_base=settings.git_clone_base_override,
        )
    if type_ == "azure":
        org = str(config.get("organization", ""))
        if not org:
            raise GitProviderError("Conexão Azure DevOps sem organização")
        return AzureDevOpsProvider(token, org, transport)
    raise GitProviderError(f"Integração '{type_}' não é um provedor Git")


def provider_for(
    integration: Any,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GitProvider:
    from app.api.integrations import get_integration_token

    token = get_integration_token(integration)
    kind = (
        integration.type.value
        if hasattr(integration.type, "value")
        else integration.type
    )
    config = integration.config or {}
    return provider_from_config(kind, {**config, "token": token}, transport=transport)
