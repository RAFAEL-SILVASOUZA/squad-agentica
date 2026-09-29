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

    async def list_repos(self) -> list[Repo]:
        async with self._client() as c:
            r = await c.get("/user/repos", params={"per_page": 100, "sort": "updated"})
        _raise_for(r, "Listar repositórios")
        return [Repo(x["full_name"], x.get("default_branch") or "main") for x in r.json()]

    async def list_branches(self, repo: str) -> list[str]:
        async with self._client() as c:
            r = await c.get(f"/repos/{repo}/branches", params={"per_page": 100})
        _raise_for(r, "Listar branches")
        return [b["name"] for b in r.json()]

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
        async with self._client() as c:
            r = await c.get(f"/{self._org}/{project}/_apis/git/repositories/{name}/refs",
                            params={"filter": "heads/", "api-version": self.API_VERSION})
        _raise_for(r, "Listar branches")
        return [x["name"].removeprefix("refs/heads/") for x in r.json().get("value", [])]

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


def provider_for(
    integration: Any,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GitProvider:
    from app.api.integrations import get_integration_token
    from app.core.config import settings

    token = get_integration_token(integration)
    kind = (
        integration.type.value
        if hasattr(integration.type, "value")
        else integration.type
    )
    if kind == "github":
        return GitHubProvider(
            token, settings.github_api_base, transport,
            clone_base=settings.git_clone_base_override,
        )
    if kind == "azure":
        org = (integration.config or {}).get("organization", "")
        if not org:
            raise GitProviderError("Conexão Azure DevOps sem organização")
        return AzureDevOpsProvider(token, org, transport)
    raise GitProviderError(f"Integração '{kind}' não é um provedor Git")
