# Projeto dos agentes, integração Git e usabilidade — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fazer um pipeline de agentes construir um projeto real num workspace compartilhado, publicá-lo como branch + Pull Request no GitHub ou Azure DevOps, e deixar o resultado legível no portal.

**Architecture:** Volume Docker `project-workspaces` montado em `/workspaces` no orchestrator e nas réplicas do worker. O orchestrator clona o repositório do pipeline em `/workspaces/<runId>` e passa o caminho ao worker em cada execução. O worker confina as ferramentas de arquivo a esse diretório. Ao final, o orchestrator faz commit, push e abre o PR pela API do provedor. O portal ganha uma tela de Integrações com abas, um bloco de repositório no editor e um monitor com abas (Resultado, Arquivos, Logs, Histórico).

**Tech Stack:** FastAPI, SQLAlchemy 2 + Alembic, httpx, `cryptography` (Fernet, já instalada), binário `git`; Next.js 14, React 18, `react-markdown` + `remark-gfm`; pytest, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-28-projeto-git-e-usabilidade-design.md`

## Global Constraints

- Destino no Git: branch nova `agent-portal/<slug-do-pipeline>-<runId-8>` + Pull Request; nunca push na branch base.
- Provedores: GitHub (`api.github.com`, respeitando `GITHUB_API_BASE`) e Azure DevOps (`dev.azure.com/<org>`), token PAT.
- O token nunca volta pela API (mostra `***`), nunca vai ao worker nem aos logs, e fica criptografado com Fernet (`INTEGRATIONS_SECRET_KEY`).
- Workspace: `WORKSPACES_DIR` (padrão `/workspaces`), um diretório por run, retenção `WORKSPACE_RETENTION_DAYS` (padrão 7).
- Autor dos commits: `GIT_AUTHOR_NAME` / `GIT_AUTHOR_EMAIL` (padrão `Agent Portal` / `agent-portal@localhost`).
- Nenhuma ferramenta do agente acessa caminho fora do workspace do run (absoluto, `..` ou symlink).
- Textos da UI em pt-BR com acentos. Markdown renderizado sem HTML cru.
- Testes backend dentro do container: `docker compose -p squad-agentica exec -T orchestrator sh -c "LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock pytest -q -p no:cacheprovider <alvo>"`; worker: `docker compose -p squad-agentica run --rm --no-deps --entrypoint "" agent-worker python -m pytest -q -p no:cacheprovider <alvo>`; portal: `npx vitest run <alvo>` em `agent-portal/`.
- Arquivos `.py`/`.ts`/`.tsx`/`.sh`/`.yml` com fim de linha LF (`.gitattributes`).
- O portal roda `next dev` num bind mount do Windows sem hot reload: reiniciar o container `portal` depois de editar, antes de testar no navegador.

## Review Focus

1. **Repositório vazio (sem commits) ou branch base inexistente:** o clone deve falhar com mensagem clara ("branch 'main' não existe no repositório"), não com o stderr cru do git. Teste na Task 5.
2. **Arquivos binários e grandes no workspace** (imagem, zip, >1 MB): a aba Arquivos não pode travar nem tentar exibir como texto; mostrar "arquivo binário/grande, baixe o zip". Teste na Task 8.
3. **Nome de pipeline com acentos, espaços ou símbolos** gerando a branch: o slug precisa ser ASCII válido para o git (`Especificação & Código` → `especificacao-codigo`). Teste na Task 5.
4. **Dois runs do mesmo pipeline publicando ao mesmo tempo, ou republicar depois do sucesso:** a branch já existe; sufixo `-2`, `-3` e "publicar de novo" idempotente (não abre um segundo PR). Teste na Task 7.
5. **Token revogado depois de cadastrado:** o clone falha com "token inválido ou sem acesso ao repositório", sem vazar o token na mensagem (a URL autenticada nunca aparece em erro ou log). Teste na Task 5.

---

## Estrutura de arquivos

**Orchestrator**
- `app/core/secrets.py` (novo): `encrypt_secret`, `decrypt_secret`.
- `app/integrations/git_providers.py` (novo): `GitProvider`, `GitHubProvider`, `AzureDevOpsProvider`, `provider_for(integration)`, `GitProviderError`.
- `app/runtime/workspace.py` (novo): `WorkspaceManager`, `WorkspaceError`, `slugify_branch`.
- `app/api/workspaces.py` (novo): árvore, conteúdo, diff, zip e publicar.
- `app/api/integrations.py`: criptografia do token, testar conexão, listar repositórios e branches.
- `app/api/pipelines.py`: campos git, `DELETE` e `POST .../duplicate`.
- `app/api/pipeline_runs.py`: cria o workspace no execute; campos de PR no run.
- `app/runtime/executor.py`: passa o workspace ao worker; publica ao concluir.
- `app/runtime/worker_client.py` e `app/compiler/graph_builder.py`: `workspace_dir` na chamada ao worker.
- `app/db/models.py` + `alembic/versions/<rev>_git_workspace.py`: colunas novas.
- `Dockerfile`: instala `git`.

**Worker**
- `app/workspace_guard.py` (novo): `current_workspace` (ContextVar), `resolve_in_workspace`.
- `app/main.py`: `ExecuteRequest.workspaceDir`.
- `app/worker.py`: ferramentas usam `resolve_in_workspace` e `cwd` do run.

**Portal**
- `app/(dashboard)/integrations/page.tsx` (novo) + `components/integrations/*` (abas, lista e formulário por provedor).
- `components/layout/app-topbar.tsx`: engrenagem.
- `components/pipelines/pipeline-header.tsx` (novo): nome e descrição editáveis, repositório, excluir e duplicar.
- `components/pipelines/repository-picker.tsx` (novo).
- `components/monitor/*`: `run-header.tsx`, `stage-strip.tsx`, `results-tab.tsx`, `files-tab.tsx`, `logs-tab.tsx`, `history-tab.tsx`; `pipeline-monitor.tsx` vira o contêiner das abas.
- `components/ui/markdown.tsx` (novo): `react-markdown` + `remark-gfm` sem HTML.
- `lib/types.ts`, `lib/api.ts` (tipos e chamadas novas).

**Infra**
- `docker-compose.yml`: volume `project-workspaces` e variáveis novas; serviço `git-test` (perfil `test`) com `git daemon` para a integração.

---

### Task 1: Criptografia de segredos e token das integrações

**Files:**
- Create: `agent-orchestrator/app/core/secrets.py`
- Modify: `agent-orchestrator/app/core/config.py` (campo `integrations_secret_key`)
- Modify: `agent-orchestrator/app/api/integrations.py` (create/update gravam `token_encrypted`; resposta mascara)
- Modify: `.env.example`, `docker-compose.yml` (`INTEGRATIONS_SECRET_KEY`)
- Test: `agent-orchestrator/tests/test_core_secrets.py`, `agent-orchestrator/tests/test_integrations_crud.py` (novo caso)

**Interfaces:**
- Produces: `encrypt_secret(plain: str) -> str`, `decrypt_secret(token: str) -> str` (lança `SecretError`); `get_integration_token(integration: Integration) -> str` em `app/api/integrations.py` (lê `token_encrypted` e migra `token` em claro).

- [ ] **Step 1: Write the failing test**

```python
# agent-orchestrator/tests/test_core_secrets.py
import pytest
from cryptography.fernet import Fernet

from app.core import secrets
from app.core.config import settings


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())


def test_roundtrip_and_ciphertext_differs():
    token = "ghp_example123"
    enc = secrets.encrypt_secret(token)
    assert enc != token and "ghp_" not in enc
    assert secrets.decrypt_secret(enc) == token


def test_tampered_ciphertext_raises():
    with pytest.raises(secrets.SecretError):
        secrets.decrypt_secret("not-a-valid-token")


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "integrations_secret_key", "")
    with pytest.raises(secrets.SecretError, match="INTEGRATIONS_SECRET_KEY"):
        secrets.encrypt_secret("x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `...pytest tests/test_core_secrets.py`
Expected: FAIL (`ModuleNotFoundError: app.core.secrets`)

- [ ] **Step 3: Write minimal implementation**

```python
# agent-orchestrator/app/core/secrets.py
"""Criptografia simétrica (Fernet) dos tokens das integrações Git."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretError(Exception):
    """Chave ausente ou segredo corrompido."""


def _fernet() -> Fernet:
    key = settings.integrations_secret_key
    if not key:
        raise SecretError("INTEGRATIONS_SECRET_KEY não configurada")
    return Fernet(key.encode())


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError) as e:
        raise SecretError("segredo inválido ou chave trocada") from e
```

Em `config.py`, junto das configurações de GitHub: `integrations_secret_key: str = ""`.

- [ ] **Step 4: Run test to verify it passes**

Run: `...pytest tests/test_core_secrets.py` → PASS

- [ ] **Step 5: Failing test — API não guarda token em claro**

```python
# acrescentar em agent-orchestrator/tests/test_integrations_crud.py
async def test_token_is_encrypted_at_rest(client, db_session, monkeypatch):
    from cryptography.fernet import Fernet
    from sqlalchemy import select
    from app.core.config import settings
    from app.db.models import Integration

    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
    r = await client.post("/api/integrations", json={
        "type": "github", "name": "gh-teste", "config": {"token": "ghp_segredo"}})
    assert r.status_code == 201
    assert r.json()["config"]["token"] == "***"
    row = (await db_session.execute(select(Integration).where(Integration.name == "gh-teste"))).scalar_one()
    assert "token" not in row.config and "ghp_segredo" not in str(row.config)
    assert row.config["token_encrypted"]
```

(Usar os fixtures `client`/`db_session` que o arquivo já define; se os nomes forem outros, adaptar só os nomes.)

- [ ] **Step 6: Implementation in `app/api/integrations.py`**

Na criação e na atualização, antes de gravar:

```python
from app.core.secrets import SecretError, decrypt_secret, encrypt_secret

def _seal_config(config: dict[str, Any]) -> dict[str, Any]:
    """Troca ``token`` em claro por ``token_encrypted``."""
    sealed = dict(config)
    token = sealed.pop("token", None)
    if token and token != _MASKED:
        sealed["token_encrypted"] = encrypt_secret(str(token))
    return sealed


def get_integration_token(integration: Integration) -> str:
    """Token em claro para uso interno (nunca devolver ao cliente)."""
    cfg = integration.config or {}
    if cfg.get("token_encrypted"):
        return decrypt_secret(cfg["token_encrypted"])
    return str(cfg.get("token", ""))


async def seal_legacy_token(db: AsyncSession, integration: Integration) -> None:
    """Spec §3: token antigo em claro passa a ser criptografado na primeira leitura."""
    cfg = integration.config or {}
    if cfg.get("token") and not cfg.get("token_encrypted"):
        integration.config = _seal_config(cfg)
        await db.commit()
```

`seal_legacy_token` é chamada no `GET /api/integrations` (para cada item) e no `GET /{id}`. Teste extra no mesmo arquivo:

```python
async def test_legacy_plain_token_is_sealed_on_read(client, db_session, owner_id):
    from app.db.models import Integration, IntegrationType
    row = Integration(owner_id=owner_id, type=IntegrationType.github, name="legado",
                      config={"token": "ghp_velho"})
    db_session.add(row)
    await db_session.commit()
    await client.get("/api/integrations")
    await db_session.refresh(row)
    assert "token" not in row.config and row.config["token_encrypted"]
```

Na resposta, mascarar `token_encrypted` como `token: "***"` (o `_to_response` já mascara chaves com "token"; garantir que `token_encrypted` não saia e que `token` apareça `***` quando houver segredo). No update, se o cliente mandar `token: "***"`, manter o `token_encrypted` atual. `SecretError` vira `AppError(500, "internal error", "secret_key_missing")`.

- [ ] **Step 7: Run tests** — `pytest tests/test_core_secrets.py tests/test_integrations*.py` → PASS; `ruff check app/core app/api/integrations.py`.

- [ ] **Step 8: Env + commit**

`.env.example`: `INTEGRATIONS_SECRET_KEY=   # python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"`. Gerar a chave e pôr no `.env` local. `docker-compose.yml` (orchestrator): `INTEGRATIONS_SECRET_KEY: ${INTEGRATIONS_SECRET_KEY:-}`.

```bash
git add agent-orchestrator/app/core/secrets.py agent-orchestrator/app/core/config.py agent-orchestrator/app/api/integrations.py agent-orchestrator/tests/test_core_secrets.py agent-orchestrator/tests/test_integrations_crud.py .env.example docker-compose.yml
git commit -m "feat(git): token das integracoes criptografado (Fernet)"
```

---

### Task 2: Provedores Git (GitHub e Azure DevOps)

**Files:**
- Create: `agent-orchestrator/app/integrations/git_providers.py`
- Test: `agent-orchestrator/tests/test_git_providers.py`

**Interfaces:**
- Consumes: `get_integration_token(integration)` (Task 1).
- Produces:
  - `class GitProviderError(Exception)` com `message: str` (pt-BR, sem token).
  - `@dataclass Repo(full_name: str, default_branch: str)`, `@dataclass PullRequest(number: int, url: str)`.
  - `class GitProvider(Protocol)`: `async list_repos() -> list[Repo]`, `async list_branches(repo: str) -> list[str]`, `clone_url(repo: str) -> str` (com credencial), `public_url(repo: str) -> str`, `async create_pull_request(repo, head, base, title, body) -> PullRequest`, `async find_open_pull_request(repo, head) -> PullRequest | None`.
  - `provider_for(integration: Integration, *, transport: httpx.AsyncBaseTransport | None = None) -> GitProvider`.

- [ ] **Step 1: Write the failing tests** (HTTP simulado com `httpx.MockTransport`)

```python
# agent-orchestrator/tests/test_git_providers.py
import json

import httpx
import pytest

from app.integrations.git_providers import (
    AzureDevOpsProvider, GitHubProvider, GitProviderError,
)


def _transport(routes):
    def handler(request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        if key not in routes:
            return httpx.Response(404, json={"message": "Not Found"})
        status, body = routes[key](request)
        return httpx.Response(status, json=body)
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_github_list_repos_and_create_pr():
    seen = {}
    def create(req):
        seen["body"] = json.loads(req.content)
        seen["auth"] = req.headers["authorization"]
        return 201, {"number": 7, "html_url": "https://github.com/o/r/pull/7"}
    gh = GitHubProvider(token="ghp_x", api_base="https://api.github.com", transport=_transport({
        ("GET", "/user/repos"): lambda r: (200, [{"full_name": "o/r", "default_branch": "main"}]),
        ("POST", "/repos/o/r/pulls"): create,
    }))
    repos = await gh.list_repos()
    assert repos[0].full_name == "o/r" and repos[0].default_branch == "main"
    pr = await gh.create_pull_request("o/r", "agent-portal/x-1", "main", "Título", "Corpo")
    assert (pr.number, pr.url) == (7, "https://github.com/o/r/pull/7")
    assert seen["body"] == {"title": "Título", "head": "agent-portal/x-1", "base": "main", "body": "Corpo"}
    assert seen["auth"] == "Bearer ghp_x"
    assert gh.clone_url("o/r") == "https://x-access-token:ghp_x@github.com/o/r.git"


@pytest.mark.asyncio
async def test_github_bad_token_message_has_no_secret():
    gh = GitHubProvider(token="ghp_secret", api_base="https://api.github.com", transport=_transport({
        ("GET", "/user/repos"): lambda r: (401, {"message": "Bad credentials"}),
    }))
    with pytest.raises(GitProviderError) as exc:
        await gh.list_repos()
    assert "token inválido" in exc.value.message and "ghp_secret" not in exc.value.message


@pytest.mark.asyncio
async def test_azure_list_repos_branches_and_pr():
    az = AzureDevOpsProvider(token="az_x", organization="org", transport=_transport({
        ("GET", "/org/_apis/git/repositories"): lambda r: (200, {"value": [
            {"name": "app", "project": {"name": "Proj"}, "defaultBranch": "refs/heads/main"}]}),
        ("GET", "/org/Proj/_apis/git/repositories/app/refs"): lambda r: (200, {"value": [
            {"name": "refs/heads/main"}, {"name": "refs/heads/dev"}]}),
        ("POST", "/org/Proj/_apis/git/repositories/app/pullrequests"): lambda r: (201, {
            "pullRequestId": 12}),
    }))
    repos = await az.list_repos()
    assert repos[0].full_name == "Proj/app" and repos[0].default_branch == "main"
    assert await az.list_branches("Proj/app") == ["main", "dev"]
    pr = await az.create_pull_request("Proj/app", "agent-portal/x-1", "main", "T", "B")
    assert pr.number == 12
    assert pr.url == "https://dev.azure.com/org/Proj/_git/app/pullrequest/12"
    assert az.clone_url("Proj/app") == "https://pat:az_x@dev.azure.com/org/Proj/_git/app"
```

- [ ] **Step 2: Run** → FAIL (módulo inexistente).

- [ ] **Step 3: Implementation**

```python
# agent-orchestrator/app/integrations/git_providers.py
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
    def __init__(self, token: str, api_base: str = "https://api.github.com",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._api = api_base.rstrip("/")
        self._transport = transport
        web = "https://github.com" if "api.github.com" in self._api else self._api.replace("/api/v3", "")
        self._web = web.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._api, transport=self._transport, timeout=30, headers={
            "Authorization": f"Bearer {self._token}", "Accept": "application/vnd.github+json"})

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
            r = await c.get(f"/repos/{repo}/pulls", params={"head": f"{owner}:{head}", "state": "open"})
        _raise_for(r, "Consultar Pull Request")
        items = r.json()
        return PullRequest(int(items[0]["number"]), items[0]["html_url"]) if items else None


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


def provider_for(integration: Any, *, transport: httpx.AsyncBaseTransport | None = None) -> GitProvider:
    from app.api.integrations import get_integration_token
    from app.core.config import settings

    token = get_integration_token(integration)
    kind = integration.type.value if hasattr(integration.type, "value") else integration.type
    if kind == "github":
        return GitHubProvider(token, settings.github_api_base, transport)
    if kind == "azure":
        org = (integration.config or {}).get("organization", "")
        if not org:
            raise GitProviderError("Conexão Azure DevOps sem organização")
        return AzureDevOpsProvider(token, org, transport)
    raise GitProviderError(f"Integração '{kind}' não é um provedor Git")
```

- [ ] **Step 4: Run** → PASS; `ruff check app/integrations/git_providers.py tests/test_git_providers.py`.

- [ ] **Step 5: Commit** — `git commit -m "feat(git): provedores GitHub e Azure DevOps (repos, branches, PR)"`

---

### Task 3: Endpoints de integração Git (testar, repositórios, branches)

**Files:**
- Modify: `agent-orchestrator/app/api/integrations.py`
- Test: `agent-orchestrator/tests/test_integrations_git_api.py`

**Interfaces:**
- Consumes: `provider_for`, `GitProviderError` (Task 2).
- Produces (REST):
  - `POST /api/integrations/{id}/test` → `200 {"ok": true, "repositories": <int>}` | `200 {"ok": false, "error": "<msg>"}`
  - `GET /api/integrations/{id}/repositories` → `200 {"items": [{"fullName", "defaultBranch"}]}` | `400 {code: "git_provider_error"}`
  - `GET /api/integrations/{id}/branches?repo=<fullName>` → `200 {"items": ["main", ...]}`

- [ ] **Step 1: Failing test** (mockando `provider_for` com um fake)

```python
# agent-orchestrator/tests/test_integrations_git_api.py
from unittest.mock import patch

from app.integrations.git_providers import GitProviderError, Repo


class FakeProvider:
    def __init__(self, fail=False):
        self.fail = fail
    async def list_repos(self):
        if self.fail:
            raise GitProviderError("Listar repositórios: token inválido ou sem acesso")
        return [Repo("o/r", "main")]
    async def list_branches(self, repo):
        return ["main", "dev"]


async def _create(client):
    r = await client.post("/api/integrations", json={
        "type": "github", "name": "gh", "config": {"token": "ghp_x"}})
    return r.json()["id"]


async def test_test_connection_ok_and_error(client):
    iid = await _create(client)
    with patch("app.api.integrations.provider_for", return_value=FakeProvider()):
        r = await client.post(f"/api/integrations/{iid}/test")
    assert r.json() == {"ok": True, "repositories": 1}
    with patch("app.api.integrations.provider_for", return_value=FakeProvider(fail=True)):
        r = await client.post(f"/api/integrations/{iid}/test")
    assert r.json()["ok"] is False and "token inválido" in r.json()["error"]


async def test_repositories_and_branches(client):
    iid = await _create(client)
    with patch("app.api.integrations.provider_for", return_value=FakeProvider()):
        repos = await client.get(f"/api/integrations/{iid}/repositories")
        branches = await client.get(f"/api/integrations/{iid}/branches", params={"repo": "o/r"})
    assert repos.json() == {"items": [{"fullName": "o/r", "defaultBranch": "main"}]}
    assert branches.json() == {"items": ["main", "dev"]}
```

(Com a chave Fernet fixada por um fixture `autouse` igual ao da Task 1.)

- [ ] **Step 2: Run** → FAIL (404).

- [ ] **Step 3: Implementation** — no router de integrações (antes das rotas `/{integration_id}` genéricas, para não conflitar com `/github/...`):

```python
from app.integrations.git_providers import GitProviderError, provider_for


async def _owned_git_integration(db, user, integration_id: uuid.UUID) -> Integration:
    integration = await _get_owned(db, user, integration_id)  # helper existente de 404 por dono
    kind = integration.type.value if hasattr(integration.type, "value") else integration.type
    if kind not in ("github", "azure"):
        raise AppError(400, "validation error", "not_a_git_integration")
    return integration


@router.post("/{integration_id}/test")
async def test_git_integration(integration_id: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    integration = await _owned_git_integration(db, user, integration_id)
    try:
        repos = await provider_for(integration).list_repos()
    except GitProviderError as e:
        return {"ok": False, "error": e.message}
    return {"ok": True, "repositories": len(repos)}


@router.get("/{integration_id}/repositories")
async def list_git_repositories(integration_id: uuid.UUID, db=Depends(get_db), user=Depends(get_current_user)):
    integration = await _owned_git_integration(db, user, integration_id)
    try:
        repos = await provider_for(integration).list_repos()
    except GitProviderError as e:
        raise AppError(400, "validation error", "git_provider_error", {"errors": [e.message]}) from None
    return {"items": [{"fullName": r.full_name, "defaultBranch": r.default_branch} for r in repos]}


@router.get("/{integration_id}/branches")
async def list_git_branches(integration_id: uuid.UUID, repo: str, db=Depends(get_db), user=Depends(get_current_user)):
    integration = await _owned_git_integration(db, user, integration_id)
    try:
        branches = await provider_for(integration).list_branches(repo)
    except GitProviderError as e:
        raise AppError(400, "validation error", "git_provider_error", {"errors": [e.message]}) from None
    return {"items": branches}
```

Usar o helper de "busca por dono" que o arquivo já tem (com os mesmos `Annotated[...]` dos outros handlers). Acrescentar `"git_provider_error"` e `"not_a_git_integration"` ao `CODE_MESSAGES` do portal na Task 10.

- [ ] **Step 4: Run** → PASS; rodar também `tests/test_integrations*.py`.

- [ ] **Step 5: Commit** — `git commit -m "feat(git): testar conexao e listar repositorios/branches"`

---

### Task 4: Modelo de dados (pipeline com repositório, run com PR) e API de pipelines

**Files:**
- Modify: `agent-orchestrator/app/db/models.py` (Pipeline: `git_integration_id`, `git_repository`, `git_base_branch`; PipelineRun: `pr_url`, `pr_number`, `publish_status`, `publish_error`)
- Create: `agent-orchestrator/alembic/versions/<nova_rev>_git_workspace.py` (`down_revision = "36713ee2fb69"` ou a head atual, conferir com `alembic heads`)
- Modify: `agent-orchestrator/app/api/pipelines.py` (ler/gravar campos git; `DELETE /pipelines/{id}`; `POST /pipelines/{id}/duplicate`)
- Modify: `agent-orchestrator/app/api/pipeline_runs.py` (`_run_to_dict` com `prUrl`, `prNumber`, `publishStatus`, `publishError`)
- Test: `tests/integration/test_04_pipeline.py` (novos casos) e `agent-orchestrator/tests/test_pipelines_git_fields.py`

**Interfaces:**
- Produces (JSON do pipeline): `"repository": {"integrationId": str, "fullName": str, "baseBranch": str} | null`.
- Produces (JSON do run): `prUrl: str | null`, `prNumber: int | null`, `publishStatus: "none"|"published"|"failed"|"no_changes"`, `publishError: str | null`.
- Produces: `DELETE /api/pipelines/{id}` → 204 (409 `graph_running` se há run ativo); `POST /api/pipelines/{id}/duplicate` → 201 com o novo pipeline (nome "`<nome> (cópia)`", sem runs).

- [ ] **Step 1: Failing test (unit, via API com o banco de teste do orchestrator)**

```python
# agent-orchestrator/tests/test_pipelines_git_fields.py
async def test_repository_roundtrip_delete_and_duplicate(client, make_agent, make_git_integration):
    agent = await make_agent("A")
    integ = await make_git_integration()
    body = {"name": "Projeto X", "nodes": [{"id": "11111111-1111-1111-1111-111111111111",
            "agentId": agent["id"], "position": {"x": 0, "y": 0}, "label": "A",
            "agentSnapshot": {"agentId": agent["id"], "name": "A", "inputs": [], "outputs": [], "actions": ["finalize"]}}],
            "edges": [], "repository": {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main"}}
    created = await client.post("/api/pipelines", json=body)
    assert created.status_code == 201
    pid = created.json()["id"]
    assert created.json()["repository"] == {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main"}

    cleared = await client.put(f"/api/pipelines/{pid}", json={"repository": None})
    assert cleared.json()["repository"] is None

    dup = await client.post(f"/api/pipelines/{pid}/duplicate")
    assert dup.status_code == 201 and dup.json()["name"] == "Projeto X (cópia)"
    assert len(dup.json()["nodes"]) == 1

    assert (await client.delete(f"/api/pipelines/{pid}")).status_code == 204
    assert (await client.get(f"/api/pipelines/{pid}")).status_code == 404
```

Criar em `tests/conftest.py` os fixtures `make_agent` (POST `/api/agents` mínimo) e `make_git_integration` (POST `/api/integrations` tipo github, com a chave Fernet fixada), se ainda não existirem.

- [ ] **Step 2: Run** → FAIL (campo `repository` ausente / 405 no DELETE).

- [ ] **Step 3: Model + migration**

```python
# models.py — Pipeline
git_integration_id: Mapped[uuid.UUID | None] = mapped_column(
    UUID(as_uuid=True), ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True)
git_repository: Mapped[str | None] = mapped_column(String(300), nullable=True)
git_base_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)

# models.py — PipelineRun
pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
publish_status: Mapped[str] = mapped_column(String(20), nullable=False, default="none", server_default="none")
publish_error: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# alembic/versions/<rev>_git_workspace.py
def upgrade() -> None:
    op.add_column("pipelines", sa.Column("git_integration_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("integrations.id", ondelete="SET NULL"), nullable=True))
    op.add_column("pipelines", sa.Column("git_repository", sa.String(300), nullable=True))
    op.add_column("pipelines", sa.Column("git_base_branch", sa.String(200), nullable=True))
    op.add_column("pipeline_runs", sa.Column("pr_url", sa.Text(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("pr_number", sa.Integer(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("publish_status", sa.String(20), nullable=False, server_default="none"))
    op.add_column("pipeline_runs", sa.Column("publish_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("publish_error", "publish_status", "pr_number", "pr_url"):
        op.drop_column("pipeline_runs", col)
    for col in ("git_base_branch", "git_repository", "git_integration_id"):
        op.drop_column("pipelines", col)
```

- [ ] **Step 4: API**

Em `pipelines.py`:
- `_build_pipeline_from_body` lê `body.get("repository")`: se for `dict`, valida que `integrationId` é UUID de uma integração do dono, de tipo `github`/`azure` (senão 400 `invalid_repository`), e que `fullName`/`baseBranch` são strings não vazias; se for `None`, zera os três campos. Se a chave não vier no corpo do PUT, mantém o valor atual.
- `_pipeline_to_dict` inclui `"repository"` (ou `None`).
- `DELETE /pipelines/{pipeline_id}`: `_load_owned` + `_assert_not_running`; apaga (cascade de nós, arestas e runs pelo modelo) e remove os workspaces dos runs (`WorkspaceManager.remove_many`, Task 5; até lá, um no-op).
- `POST /pipelines/{pipeline_id}/duplicate`: carrega, gera novos UUIDs de nós e arestas (mapa antigo→novo, inclusive `entryNodeId`), nome `"<nome> (cópia)"`, status `draft`.

Em `pipeline_runs.py`, `_run_to_dict` acrescenta os 4 campos.

- [ ] **Step 5: Run** — rebuild do orchestrator não é necessário (migração roda no start do dev override): `docker compose -p squad-agentica restart orchestrator` e depois `...pytest tests/test_pipelines_git_fields.py tests/test_pipeline*.py` → PASS; integração `tests/integration/test_04_pipeline.py` → PASS.

- [ ] **Step 6: Commit** — `git commit -m "feat(git): repositorio no pipeline, PR no run, excluir e duplicar pipeline"`

---

### Task 5: Gerenciador de workspace (clone, alterações, commit, publicação)

**Files:**
- Create: `agent-orchestrator/app/runtime/workspace.py`
- Modify: `agent-orchestrator/Dockerfile` (instalar git), `agent-orchestrator/app/core/config.py` (`workspaces_dir`, `workspace_retention_days`, `git_author_name`, `git_author_email`)
- Test: `agent-orchestrator/tests/test_runtime_workspace.py`

**Interfaces:**
- Produces:
  - `slugify_branch(pipeline_name: str, run_id: str) -> str` → `agent-portal/<slug>-<run_id[:8]>`.
  - `class WorkspaceError(Exception)` com `.message` (pt-BR, sem URL autenticada).
  - `class WorkspaceManager(root: Path)`:
    - `path(run_id) -> Path`
    - `create_empty(run_id) -> Path`
    - `async clone(run_id, clone_url, base_branch) -> Path`
    - `async changed_files(run_id) -> list[dict]` (`{"path", "status": "added"|"modified"|"deleted"}`)
    - `tree(run_id) -> list[dict]` (`{"path", "size", "binary": bool}`)
    - `read_file(run_id, rel_path, max_bytes=1_000_000) -> dict` (`{"path","content"|None,"binary","tooLarge"}`)
    - `async diff(run_id) -> str`
    - `zip_bytes(run_id) -> bytes`
    - `async commit_and_push(run_id, clone_url, branch, message) -> str | None` (branch efetivamente usada; `None` sem alterações)
    - `remove(run_id)`, `remove_many(run_ids)`, `purge_older_than(days) -> int`.

- [ ] **Step 1: Failing tests** (repositório bare local como "remote")

```python
# agent-orchestrator/tests/test_runtime_workspace.py
import asyncio
import subprocess
from pathlib import Path

import pytest

from app.runtime.workspace import WorkspaceError, WorkspaceManager, slugify_branch


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def remote(tmp_path) -> str:
    bare = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", "-b", "main", str(bare))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", str(bare), str(seed))
    (seed / "README.md").write_text("# base\n")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "add", ".")
    _git(seed, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-m", "base")
    _git(seed, "push", "origin", "main")
    return str(bare)


def test_slugify_branch():
    assert slugify_branch("Especificação & Código!", "abcdef123456") == "agent-portal/especificacao-codigo-abcdef12"
    assert slugify_branch("   ", "abcdef123456") == "agent-portal/pipeline-abcdef12"


@pytest.mark.asyncio
async def test_clone_change_commit_push(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    path = await ws.clone("run1", remote, "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("print('oi')\n")
    (path / "README.md").write_text("# alterado\n")
    changed = await ws.changed_files("run1")
    assert {"path": "src/app.py", "status": "added"} in changed
    assert {"path": "README.md", "status": "modified"} in changed
    assert "+print('oi')" in await ws.diff("run1")
    branch = await ws.commit_and_push("run1", remote, "agent-portal/x-run1", "msg")
    assert branch == "agent-portal/x-run1"
    out = subprocess.run(["git", "--git-dir", remote, "branch"], capture_output=True, text=True).stdout
    assert "agent-portal/x-run1" in out


@pytest.mark.asyncio
async def test_existing_branch_gets_suffix_and_no_changes_returns_none(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    for run in ("r1", "r2"):
        p = await ws.clone(run, remote, "main")
        (p / f"{run}.txt").write_text(run)
        branch = await ws.commit_and_push(run, remote, "agent-portal/x", "m")
    assert branch == "agent-portal/x-2"
    await ws.clone("r3", remote, "main")
    assert await ws.commit_and_push("r3", remote, "agent-portal/y", "m") is None


@pytest.mark.asyncio
async def test_clone_errors_are_clear_and_hide_credentials(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r1", remote, "nao-existe")
    assert "branch 'nao-existe' não existe" in exc.value.message
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r2", "https://user:SEGREDO@127.0.0.1:9/x.git", "main")
    assert "SEGREDO" not in exc.value.message


def test_read_file_binary_large_and_escape(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    p = ws.create_empty("r1")
    (p / "img.png").write_bytes(b"\x89PNG\x00\x01")
    (p / "big.txt").write_text("x" * 20)
    assert ws.read_file("r1", "img.png")["binary"] is True
    assert ws.read_file("r1", "big.txt", max_bytes=10)["tooLarge"] is True
    with pytest.raises(WorkspaceError):
        ws.read_file("r1", "../../etc/passwd")
```

- [ ] **Step 2: Dockerfile + run** — no `agent-orchestrator/Dockerfile`, antes do `pip install`: `RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*`. `docker compose -p squad-agentica build orchestrator && docker compose -p squad-agentica up -d orchestrator`. Rodar os testes → FAIL (módulo inexistente).

- [ ] **Step 3: Implementation**

```python
# agent-orchestrator/app/runtime/workspace.py
"""Workspace compartilhado por run: clone, alterações, diff, zip e publicação."""

from __future__ import annotations

import asyncio
import io
import re
import shutil
import time
import unicodedata
import zipfile
from pathlib import Path

from app.core.config import settings


class WorkspaceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


_CRED = re.compile(r"(https?://)[^@/\s]+@")


def _scrub(text: str) -> str:
    return _CRED.sub(r"\1***@", text)


def slugify_branch(pipeline_name: str, run_id: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", pipeline_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:40].strip("-") or "pipeline"
    return f"agent-portal/{slug}-{run_id.replace('-', '')[:8]}"


async def _git(cwd: Path | None, *args: str, check: bool = True) -> tuple[int, str]:
    env = {"GIT_TERMINAL_PROMPT": "0", "PATH": "/usr/local/bin:/usr/bin:/bin"}
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=str(cwd) if cwd else None, env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    text = _scrub(out.decode("utf-8", errors="replace"))
    if check and proc.returncode != 0:
        raise WorkspaceError(text.strip()[-500:] or f"git {args[0]} falhou")
    return proc.returncode or 0, text


class WorkspaceManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.workspaces_dir)

    def path(self, run_id: str) -> Path:
        return self.root / run_id

    def _safe(self, run_id: str, rel: str) -> Path:
        base = self.path(run_id).resolve()
        target = (base / rel).resolve()
        if target != base and base not in target.parents:
            raise WorkspaceError("caminho fora do workspace")
        return target

    def create_empty(self, run_id: str) -> Path:
        p = self.path(run_id)
        p.mkdir(parents=True, exist_ok=True)
        return p

    async def clone(self, run_id: str, clone_url: str, base_branch: str) -> Path:
        dest = self.path(run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        code, out = await _git(None, "clone", "--depth", "1", "--branch", base_branch,
                               clone_url, str(dest), check=False)
        if code != 0:
            shutil.rmtree(dest, ignore_errors=True)
            if "Remote branch" in out and "not found" in out:
                raise WorkspaceError(f"branch '{base_branch}' não existe no repositório")
            if "Authentication failed" in out or "403" in out or "could not read Username" in out:
                raise WorkspaceError("token inválido ou sem acesso ao repositório")
            raise WorkspaceError(f"falha ao clonar o repositório: {out.strip()[-300:]}")
        # Credencial fora do remote: o worker (e os agentes) nunca veem o token.
        await _git(dest, "remote", "set-url", "origin", _CRED.sub(r"\1", clone_url))
        return dest

    async def changed_files(self, run_id: str) -> list[dict]:
        p = self.path(run_id)
        if not (p / ".git").exists():
            return [{"path": f["path"], "status": "added"} for f in self.tree(run_id)]
        _, out = await _git(p, "status", "--porcelain", "--untracked-files=all")
        result = []
        for line in out.splitlines():
            code, name = line[:2], line[3:]
            status = "added" if "?" in code or "A" in code else "deleted" if "D" in code else "modified"
            result.append({"path": name.strip('"'), "status": status})
        return result

    def tree(self, run_id: str) -> list[dict]:
        base = self.path(run_id)
        items = []
        for f in sorted(base.rglob("*")):
            if f.is_file() and ".git" not in f.relative_to(base).parts:
                head = f.read_bytes()[:8000]
                items.append({"path": f.relative_to(base).as_posix(), "size": f.stat().st_size,
                              "binary": b"\x00" in head})
        return items

    def read_file(self, run_id: str, rel_path: str, max_bytes: int = 1_000_000) -> dict:
        f = self._safe(run_id, rel_path)
        if not f.is_file():
            raise WorkspaceError("arquivo não encontrado")
        size = f.stat().st_size
        data = f.read_bytes()[: max_bytes + 1]
        binary = b"\x00" in data[:8000]
        too_large = size > max_bytes
        content = None if binary or too_large else data.decode("utf-8", errors="replace")
        return {"path": rel_path, "content": content, "binary": binary, "tooLarge": too_large, "size": size}

    async def diff(self, run_id: str) -> str:
        p = self.path(run_id)
        if not (p / ".git").exists():
            return ""
        await _git(p, "add", "-A", "-N")
        _, out = await _git(p, "diff")
        return out

    def zip_bytes(self, run_id: str) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for item in self.tree(run_id):
                z.write(self.path(run_id) / item["path"], item["path"])
        return buf.getvalue()

    async def commit_and_push(self, run_id: str, clone_url: str, branch: str, message: str) -> str | None:
        p = self.path(run_id)
        if not await self.changed_files(run_id):
            return None
        author = ["-c", f"user.name={settings.git_author_name}",
                  "-c", f"user.email={settings.git_author_email}"]
        await _git(p, "add", "-A")
        await _git(p, *author, "commit", "-m", message)
        candidate, n = branch, 1
        while True:
            code, _ = await _git(p, "ls-remote", "--exit-code", "--heads", clone_url, candidate, check=False)
            if code != 0:
                break
            n += 1
            candidate = f"{branch}-{n}"
        await _git(p, "push", clone_url, f"HEAD:refs/heads/{candidate}")
        return candidate

    def remove(self, run_id: str) -> None:
        shutil.rmtree(self.path(run_id), ignore_errors=True)

    def remove_many(self, run_ids: list[str]) -> None:
        for r in run_ids:
            self.remove(r)

    def purge_older_than(self, days: int) -> int:
        if not self.root.exists():
            return 0
        limit = time.time() - days * 86400
        removed = 0
        for d in self.root.iterdir():
            if d.is_dir() and d.stat().st_mtime < limit:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed
```

`config.py`: `workspaces_dir: str = "/workspaces"`, `workspace_retention_days: int = 7`, `git_author_name: str = "Agent Portal"`, `git_author_email: str = "agent-portal@localhost"`.

- [ ] **Step 4: Run** → PASS; `ruff check app/runtime/workspace.py tests/test_runtime_workspace.py`.

- [ ] **Step 5: Commit** — `git commit -m "feat(git): workspace por run (clone, alteracoes, diff, zip, push)"`

---

### Task 6: Worker confinado ao workspace do run

**Files:**
- Create: `agent-worker/app/workspace_guard.py`
- Modify: `agent-worker/app/main.py` (`ExecuteRequest.workspaceDir`), `agent-worker/app/worker.py` (ferramentas usam o guard; `execute_agent` recebe o workspace)
- Test: `agent-worker/tests/test_workspace_guard.py`

**Interfaces:**
- Produces: `current_workspace: ContextVar[Path]`; `resolve_in_workspace(raw: str) -> Path` (lança `WorkspaceEscapeError`); `ExecuteRequest.workspaceDir: str | None` (precisa estar dentro de `WORKSPACES_DIR`, senão 400 `invalid_workspace`).

- [ ] **Step 1: Failing tests**

```python
# agent-worker/tests/test_workspace_guard.py
import os
from pathlib import Path

import pytest

from app import worker
from app.workspace_guard import WorkspaceEscapeError, current_workspace, resolve_in_workspace


@pytest.fixture
def ws(tmp_path):
    token = current_workspace.set(tmp_path)
    yield tmp_path
    current_workspace.reset(token)


def test_relative_and_absolute_inside(ws):
    assert resolve_in_workspace("src/a.py") == ws / "src" / "a.py"
    assert resolve_in_workspace(str(ws / "b.txt")) == ws / "b.txt"


@pytest.mark.parametrize("raw", ["/etc/passwd", "../fora.txt", "src/../../fora.txt"])
def test_escape_is_refused(ws, raw):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace(raw)


def test_symlink_out_is_refused(ws, tmp_path_factory):
    outside = tmp_path_factory.mktemp("out") / "secret.txt"
    outside.write_text("x")
    os.symlink(outside, ws / "link.txt")
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("link.txt")


@pytest.mark.asyncio
async def test_tools_write_and_shell_use_run_workspace(ws):
    assert (await worker.execute_tool("write_file", {"path": "a.txt", "content": "oi"}))["success"]
    assert (ws / "a.txt").read_text() == "oi"
    res = await worker.execute_tool("read_file", {"path": "/etc/hostname"})
    assert "fora do workspace" in res["error"]
    shell = await worker.execute_tool("shell", {"command": "ls"})
    assert "a.txt" in shell["stdout"]
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Implementation**

```python
# agent-worker/app/workspace_guard.py
"""Confina as ferramentas do agente ao workspace do run (spec 14.1)."""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path

WORKSPACES_ROOT = Path(os.environ.get("WORKSPACES_DIR", "/workspaces"))
current_workspace: ContextVar[Path] = ContextVar(
    "current_workspace", default=Path(os.environ.get("AGENT_WORKSPACE", "/tmp/agent-workspace"))
)


class WorkspaceEscapeError(Exception):
    pass


def resolve_in_workspace(raw: str) -> Path:
    base = current_workspace.get().resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = Path(raw)
    target = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if target != base and base not in target.parents:
        raise WorkspaceEscapeError(f"caminho fora do workspace: {raw}")
    return target
```

Em `worker.py`: remover o `WORKSPACE_DIR` global; cada ferramenta de arquivo troca `Path(WORKSPACE_DIR) / path` por `resolve_in_workspace(args.get("path", ""))`, com `except WorkspaceEscapeError as e: return {"error": str(e)}`; `glob`/`grep`/`list_directory` resolvem a base igual; `shell` usa `cwd=str(current_workspace.get())` e `HOME` idem. Em `execute_agent(...)`, novo parâmetro `workspace_dir: str | None`: `token = current_workspace.set(Path(workspace_dir))` no início e `current_workspace.reset(token)` num `finally`.

Em `main.py`: `workspaceDir: str | None = None` no `ExecuteRequest`; antes de executar, se veio, validar `Path(req.workspaceDir).resolve()` dentro de `WORKSPACES_ROOT.resolve()` (senão 400 `invalid_workspace`) e passar a `execute_agent`.

- [ ] **Step 4: Run** → PASS (worker inteiro: `python -m pytest -q`); `ruff check app tests`.

- [ ] **Step 5: Commit** — `git commit -m "fix(seguranca): ferramentas do agente confinadas ao workspace do run"`

---

### Task 7: Executor — workspace no run e publicação do PR

**Files:**
- Modify: `agent-orchestrator/app/compiler/graph_builder.py` (`WorkerClient.execute(..., workspace_dir: str | None = None)`; o nó passa `state["workspace_dir"]`)
- Modify: `agent-orchestrator/app/compiler/state.py` (`workspace_dir: str` com reducer "last")
- Modify: `agent-orchestrator/app/runtime/worker_client.py` (inclui `workspaceDir` no corpo)
- Modify: `agent-orchestrator/app/runtime/executor.py` (`execute(..., workspace_dir=...)`; ao concluir, `publish_run`)
- Create: `agent-orchestrator/app/runtime/publisher.py` (`async publish_run(run_id) -> None`)
- Modify: `agent-orchestrator/app/api/pipeline_runs.py` (execute cria o workspace/clona; `POST /runs/{run_id}/publish`)
- Modify: `docker-compose.yml` (volume `project-workspaces` em orchestrator e agent-worker; env `WORKSPACES_DIR`)
- Test: `agent-orchestrator/tests/test_runtime_publisher.py`, casos novos em `tests/test_rt_executor.py`

**Interfaces:**
- Consumes: `WorkspaceManager`, `slugify_branch` (Task 5); `provider_for` (Task 2); campos do run (Task 4).
- Produces: `publish_run(run_id: str, *, manager: WorkspaceManager | None = None, provider_factory=provider_for) -> dict` que atualiza `publish_status`/`pr_url`/`pr_number`/`publish_error` e devolve o JSON do run; `POST /api/runs/{run_id}/publish` → 200 com o run.

- [ ] **Step 1: Failing tests** — publicador com remote bare e provedor fake

```python
# agent-orchestrator/tests/test_runtime_publisher.py
import pytest

from app.integrations.git_providers import PullRequest
from app.runtime.publisher import build_pr_body, publish_workspace


class FakeProvider:
    def __init__(self, remote):
        self.remote, self.created = remote, []
    def clone_url(self, repo):
        return self.remote
    async def find_open_pull_request(self, repo, head):
        return next((pr for h, pr in self.created if h == head), None)
    async def create_pull_request(self, repo, head, base, title, body):
        pr = PullRequest(len(self.created) + 1, f"https://example/pr/{len(self.created) + 1}")
        self.created.append((head, pr))
        return pr


@pytest.mark.asyncio
async def test_publish_creates_branch_and_pr_and_is_idempotent(tmp_path, remote):
    # a fixture `remote` da Task 5 passa para tests/conftest.py neste step, para os dois arquivos a usarem
    from app.runtime.workspace import WorkspaceManager
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run-abc12345", remote, "main")
    (p / "novo.txt").write_text("x")
    prov = FakeProvider(remote)
    first = await publish_workspace(ws, prov, run_id="run-abc12345", repo="o/r", base="main",
                                    pipeline_name="Projeto X", title="Projeto X: ideia", body="b")
    assert first == {"status": "published", "number": 1, "url": "https://example/pr/1",
                     "branch": "agent-portal/projeto-x-runabc12"}
    again = await publish_workspace(ws, prov, run_id="run-abc12345", repo="o/r", base="main",
                                    pipeline_name="Projeto X", title="t", body="b")
    assert again["number"] == 1 and len(prov.created) == 1


@pytest.mark.asyncio
async def test_publish_without_changes(tmp_path, remote):
    from app.runtime.workspace import WorkspaceManager
    ws = WorkspaceManager(tmp_path / "ws")
    await ws.clone("r2", remote, "main")
    res = await publish_workspace(ws, FakeProvider(remote), run_id="r2", repo="o/r", base="main",
                                  pipeline_name="P", title="t", body="b")
    assert res == {"status": "no_changes"}


def test_pr_body_has_inputs_outputs_and_link():
    body = build_pr_body(inputs={"ideia": "app"}, outputs={"Redator": {"spec": "# Spec"}},
                         run_url="http://localhost/pipelines/p/run")
    assert "app" in body and "# Spec" in body and "http://localhost/pipelines/p/run" in body
```

- [ ] **Step 2: Run** → FAIL.

- [ ] **Step 3: Publisher**

```python
# agent-orchestrator/app/runtime/publisher.py
"""Publica o workspace de um run: commit, push e Pull Request."""

from __future__ import annotations

from typing import Any

from app.integrations.git_providers import GitProviderError
from app.runtime.workspace import WorkspaceError, WorkspaceManager, slugify_branch


def build_pr_body(inputs: dict[str, Any], outputs: dict[str, dict[str, Any]], run_url: str) -> str:
    lines = ["Gerado pelo **Agent Portal**.", "", f"Run: {run_url}", "", "## Entrada"]
    lines += [f"- **{k}**: {v}" for k, v in inputs.items()] or ["- (sem entradas)"]
    for agent, out in outputs.items():
        lines += ["", f"## {agent}"]
        for port, value in out.items():
            if not str(port).startswith("_"):
                lines += [f"### {port}", str(value)[:3000]]
    return "\n".join(lines)


async def publish_workspace(ws: WorkspaceManager, provider: Any, *, run_id: str, repo: str,
                            base: str, pipeline_name: str, title: str, body: str) -> dict[str, Any]:
    branch = slugify_branch(pipeline_name, run_id)
    try:
        existing = await provider.find_open_pull_request(repo, branch)
        if existing:
            return {"status": "published", "number": existing.number, "url": existing.url, "branch": branch}
        pushed = await ws.commit_and_push(run_id, provider.clone_url(repo), branch, title)
        if pushed is None:
            return {"status": "no_changes"}
        pr = await provider.create_pull_request(repo, pushed, base, title, body)
        return {"status": "published", "number": pr.number, "url": pr.url, "branch": pushed}
    except (WorkspaceError, GitProviderError) as e:
        return {"status": "failed", "error": e.message}
```

`publish_run(run_id)` (mesmo arquivo): carrega run, pipeline e integração do banco; sem repositório → `publish_status="none"`; senão chama `publish_workspace` com `provider_for(integration)`, título `"<pipeline>: <primeira entrada resumida em 60 chars>"`, corpo com `build_pr_body` (entradas do run guardadas no estado `run_inputs`; saídas dos checkpoints concluídos do run); grava `publish_status`, `pr_url`, `pr_number`, `publish_error` e emite `pipeline:status` agregado (`nodeId=""`) para o monitor recarregar o run.

- [ ] **Step 4: Executor, worker client e API**

- `state.py`: `workspace_dir: str` (reducer padrão "last"); `initial_state()` inclui `"workspace_dir": ""`.
- `graph_builder._make_agent_node`: `await worker_client.execute(..., timeout=timeout, workspace_dir=state.get("workspace_dir") or None)`.
- `WorkerClient` (Protocol) e `HttpWorkerClient.execute` ganham `workspace_dir: str | None = None`; corpo: `if workspace_dir: body["workspaceDir"] = workspace_dir`. Fakes dos testes (`FakeWorker` em `tests/test_rt_executor.py`, `tests/test_hitl_approval.py`, `tests/test_compiler_graph_builder.py`) ganham `workspace_dir=None` na assinatura.
- `executor.execute(..., workspace_dir: str | None = None)`: `state["workspace_dir"] = workspace_dir or ""`. No fim de `_run`, se `final_status == "completed"`, `await publish_run(active.run_id)` dentro de try/except que só loga (a publicação nunca muda o status do run).
- `pipeline_runs.execute_pipeline`: depois de criar o `PipelineRun`, `ws = WorkspaceManager()`; se o pipeline tem repositório: `await ws.clone(run_id, provider_for(integ).clone_url(repo), base)`; `WorkspaceError`/`GitProviderError` → run gravado como `failed` com `error=e.message` e resposta 200 com o run (o monitor mostra o motivo); senão `ws.create_empty(run_id)`. Passar `workspace_dir=str(ws.path(run_id))` ao executor.
- Novo `POST /api/runs/{run_id}/publish` (dono do run; 409 `run_not_completed` se o run não está `completed`) → `await publish_run(run_id)`.
- `docker-compose.yml`: `volumes: - project-workspaces:/workspaces` em `orchestrator` e `agent-worker`; `WORKSPACES_DIR: /workspaces` nos dois; `project-workspaces:` na seção `volumes:` do topo.

- [ ] **Step 5: Teste do executor** — em `tests/test_rt_executor.py`:

```python
async def test_workspace_dir_reaches_worker(self, executor, worker):
    pipeline = _simple_pipeline_a_b_c()
    with patch("app.runtime.executor.publish_run", new_callable=AsyncMock) as pub:
        await executor.execute(pipeline, owner_id="o", workspace_dir="/workspaces/r1")
        active = get_active_run("p-test")
        await asyncio.wait_for(active.task, timeout=10)
    assert {c["workspace_dir"] for c in worker.calls} == {"/workspaces/r1"}
    pub.assert_awaited_once()
```

(`FakeWorker.execute` passa a registrar `workspace_dir` em `self.calls`.)

- [ ] **Step 6: Run** — `docker compose -p squad-agentica up -d` (volume novo); `...pytest -q` (suíte inteira do orchestrator) → PASS; worker `python -m pytest -q` → PASS.

- [ ] **Step 7: Commit** — `git commit -m "feat(git): run clona o repositorio, agentes trabalham no workspace e o run abre PR"`

---

### Task 8: API de arquivos do run e limpeza

**Files:**
- Create: `agent-orchestrator/app/api/workspaces.py`
- Modify: `agent-orchestrator/app/main.py` (tarefa de limpeza no lifespan: `purge_older_than` no start e a cada 24h)
- Test: `agent-orchestrator/tests/test_api_workspaces.py`

**Interfaces:**
- Produces (todos checam o dono do run; 404 `run_not_found`):
  - `GET /api/runs/{run_id}/files` → `{"items": [{"path", "size", "binary", "status": "added"|"modified"|"deleted"|null}]}`
  - `GET /api/runs/{run_id}/files/content?path=` → `{"path","content"|null,"binary","tooLarge","size"}` (400 `invalid_path` se escapar)
  - `GET /api/runs/{run_id}/diff` → `{"diff": "<unified diff>"}`
  - `GET /api/runs/{run_id}/archive` → `application/zip` com `Content-Disposition: attachment; filename="<slug>-<run8>.zip"`

- [ ] **Step 1: Failing tests**

```python
# agent-orchestrator/tests/test_api_workspaces.py
import io
import zipfile


async def test_files_content_diff_and_zip(client, make_run_with_workspace):
    run_id, path = await make_run_with_workspace()      # fixture: run do usuário + WorkspaceManager.create_empty
    (path / "src").mkdir()
    (path / "src" / "a.py").write_text("print(1)\n")
    (path / "logo.png").write_bytes(b"\x89PNG\x00")

    files = (await client.get(f"/api/runs/{run_id}/files")).json()["items"]
    assert {f["path"] for f in files} == {"src/a.py", "logo.png"}
    assert next(f for f in files if f["path"] == "logo.png")["binary"] is True

    content = (await client.get(f"/api/runs/{run_id}/files/content", params={"path": "src/a.py"})).json()
    assert content["content"] == "print(1)\n"
    bad = await client.get(f"/api/runs/{run_id}/files/content", params={"path": "../../etc/passwd"})
    assert bad.status_code == 400

    z = await client.get(f"/api/runs/{run_id}/archive")
    assert z.headers["content-type"] == "application/zip"
    assert "src/a.py" in zipfile.ZipFile(io.BytesIO(z.content)).namelist()


async def test_other_owner_gets_404(client_other_user, make_run_with_workspace):
    run_id, _ = await make_run_with_workspace()
    assert (await client_other_user.get(f"/api/runs/{run_id}/files")).status_code == 404
```

Fixtures em `tests/conftest.py`: `make_run_with_workspace` (cria pipeline + run do usuário no banco de teste, `WorkspaceManager(tmp_path)` monkeypatched em `app.api.workspaces`) e `client_other_user` (cliente autenticado como outro usuário, igual aos testes de isolamento existentes).

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** o router (prefixo `/api/runs`), usando `WorkspaceManager()` e `changed_files` para preencher `status`; `WorkspaceError` → 400 `invalid_path`/404 `file_not_found`. Lifespan: `asyncio.create_task(_purge_loop())`, que chama `WorkspaceManager().purge_older_than(settings.workspace_retention_days)` e dorme 24h.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** — `git commit -m "feat(git): API de arquivos, diff e zip do run; limpeza por retencao"`

---

### Task 9: Portal — tela de Integrações com abas

**Files:**
- Create: `agent-portal/app/(dashboard)/integrations/page.tsx`, `agent-portal/components/integrations/integrations-view.tsx`, `agent-portal/components/integrations/git-connections.tsx`, `agent-portal/components/integrations/git-connection-form.tsx`
- Modify: `agent-portal/components/layout/app-topbar.tsx` (engrenagem `Settings` → `/integrations`, `aria-label="Integrações"`), `agent-portal/components/library/knowledge-view.tsx` (remover a caixa do Rivvn), `agent-portal/lib/types.ts`, `agent-portal/lib/api.ts` (`CODE_MESSAGES`: `git_provider_error`, `not_a_git_integration`, `invalid_repository`, `secret_key_missing`)
- Test: `agent-portal/components/integrations/integrations-view.test.tsx`

**Interfaces:**
- Consumes: `POST/GET/PUT/DELETE /api/integrations`, `POST /api/integrations/{id}/test` (Task 3).
- Produces: `IntegrationsView` com abas `github` | `azure` | `outras` (query `?tab=`); `GitConnections({ provider: "github" | "azure" })`.

- [ ] **Step 1: Failing test**

```tsx
// agent-portal/components/integrations/integrations-view.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { IntegrationsView } from "./integrations-view";
import { ToastProvider } from "@/components/ui/toast";

const mockList = vi.fn();
const mockPost = vi.fn();
vi.mock("@/lib/api", async (orig) => ({
  ...(await orig<typeof import("@/lib/api")>()),
  api: { list: (...a: unknown[]) => mockList(...a), post: (...a: unknown[]) => mockPost(...a),
         put: vi.fn(), delete: vi.fn(), get: vi.fn() },
}));

const render_ = () => render(<ToastProvider><IntegrationsView /></ToastProvider>);

describe("IntegrationsView", () => {
  beforeEach(() => { mockList.mockReset(); mockPost.mockReset(); });

  it("shows tabs and lists connections of the active provider", async () => {
    mockList.mockResolvedValue({ items: [
      { id: "1", type: "github", name: "Meu GitHub", config: { token: "***" }, status: "active" },
      { id: "2", type: "azure", name: "Azure Org", config: { token: "***", organization: "org" }, status: "active" },
    ], total: 2, page: 1, limit: 100 });
    render_();
    expect(await screen.findByRole("tab", { name: "GitHub" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("Meu GitHub")).toBeInTheDocument();
    expect(screen.queryByText("Azure Org")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Azure DevOps" }));
    expect(await screen.findByText("Azure Org")).toBeInTheDocument();
  });

  it("creates an Azure DevOps connection with organization and never shows the token", async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
    mockPost.mockResolvedValue({ id: "9", type: "azure", name: "Az", config: { token: "***", organization: "org" } });
    render_();
    fireEvent.click(await screen.findByRole("tab", { name: "Azure DevOps" }));
    fireEvent.click(screen.getByRole("button", { name: /Nova conexão/i }));
    fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Az" } });
    fireEvent.change(screen.getByLabelText("Organização"), { target: { value: "org" } });
    fireEvent.change(screen.getByLabelText(/Token/), { target: { value: "pat-123" } });
    fireEvent.click(screen.getByRole("button", { name: /Salvar conexão/i }));
    await waitFor(() => expect(mockPost).toHaveBeenCalledWith("/api/integrations", {
      type: "azure", name: "Az", config: { token: "pat-123", organization: "org" } }));
    expect(screen.queryByText("pat-123")).not.toBeInTheDocument();
  });

  it("tests a connection and shows the result", async () => {
    mockList.mockResolvedValue({ items: [{ id: "1", type: "github", name: "GH", config: { token: "***" }, status: "active" }], total: 1, page: 1, limit: 100 });
    mockPost.mockResolvedValue({ ok: false, error: "Listar repositórios: token inválido ou sem acesso" });
    render_();
    fireEvent.click(await screen.findByRole("button", { name: /Testar conexão GH/i }));
    expect(await screen.findByText(/token inválido ou sem acesso/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.**
  - Abas acessíveis: `role="tablist"`/`role="tab"`, `aria-selected`, teclado ←/→.
  - Aba GitHub: campos Nome e Token (`type="password"`, hint "PAT com escopo repo").
  - Aba Azure DevOps: campos Nome, Organização e Token (hint "Code: Read & Write").
  - Cada conexão tem:
    - nome e status;
    - "Testar conexão <nome>", que mostra "Conectado, N repositórios" ou o erro;
    - Editar (token vazio mantém o atual: envia `token: "***"`);
    - Excluir com o `Modal` de confirmação. A confirmação lista os pipelines que usam a conexão (spec §3): carregar `GET /api/pipelines?limit=100` e filtrar por `repository.integrationId`. O texto fica "Os pipelines X e Y ficarão sem repositório.". Acrescentar ao teste: excluir uma conexão usada pelo pipeline "Gerador" mostra "Gerador" no modal.
  - Aba Outras: a caixa do Rivvn, movida de `knowledge-view.tsx` sem mudar comportamento.
  - Página `integrations/page.tsx`: `<IntegrationsView />`. Topbar: botão com ícone `Settings` que navega para `/integrations`.
- [ ] **Step 4: Run** → PASS; `npx tsc --noEmit`, `npm run lint`, `npx vitest run components/integrations components/layout components/library`.
- [ ] **Step 5: Commit** — `git commit -m "feat(portal): tela de Integracoes com abas (GitHub, Azure DevOps, Outras)"`

---

### Task 10: Portal — cabeçalho do pipeline (nome, descrição, repositório, excluir, duplicar) e lista

**Files:**
- Create: `agent-portal/components/pipelines/pipeline-header.tsx`, `agent-portal/components/pipelines/repository-picker.tsx`
- Modify: `agent-portal/app/(dashboard)/pipelines/[id]/page.tsx` (usa o header; salva nome/descrição/repositório via PUT), `agent-portal/app/(dashboard)/pipelines/page.tsx` (card com repositório, último run e atalho do monitor; excluir/duplicar no menu do card; criar abre o editor com o nome em edição via `?new=1`), `agent-portal/lib/types.ts` (`Pipeline.repository`)
- Test: `agent-portal/components/pipelines/pipeline-header.test.tsx`, `agent-portal/components/pipelines/repository-picker.test.tsx`

**Interfaces:**
- Consumes: `GET /api/integrations`, `GET /api/integrations/{id}/repositories`, `GET /api/integrations/{id}/branches?repo=` (Task 3); `PUT /api/pipelines/{id}` com `name`, `description`, `repository`; `DELETE` e `POST .../duplicate` (Task 4).
- Produces: `PipelineHeader({ pipeline, onChange(patch: Partial<Pipeline>), onDeleted(), onDuplicated(id) })`; `RepositoryPicker({ value: Pipeline["repository"], onChange(v) })`.

- [ ] **Step 1: Failing tests**

```tsx
// pipeline-header.test.tsx (trechos principais)
it("edits the name inline and saves on Enter", async () => {
  const onChange = vi.fn();
  render(<ToastProvider><PipelineHeader pipeline={makePipeline({ name: "Novo pipeline" })} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} autoEditName /></ToastProvider>);
  const input = screen.getByLabelText("Nome do pipeline");
  fireEvent.change(input, { target: { value: "Gerador de API" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(onChange).toHaveBeenCalledWith({ name: "Gerador de API" });
});

it("refuses an empty name", () => {
  const onChange = vi.fn();
  render(<ToastProvider><PipelineHeader pipeline={makePipeline()} onChange={onChange} onDeleted={vi.fn()} onDuplicated={vi.fn()} autoEditName /></ToastProvider>);
  const input = screen.getByLabelText("Nome do pipeline");
  fireEvent.change(input, { target: { value: "   " } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toHaveTextContent("Informe um nome");
});

it("deletes after confirmation", async () => {
  mockDelete.mockResolvedValue(undefined);
  const onDeleted = vi.fn();
  render(<ToastProvider><PipelineHeader pipeline={makePipeline({ id: "p1", name: "X" })} onChange={vi.fn()} onDeleted={onDeleted} onDuplicated={vi.fn()} /></ToastProvider>);
  fireEvent.click(screen.getByRole("button", { name: "Mais ações" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Excluir pipeline" }));
  fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
  await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("/api/pipelines/p1"));
  expect(onDeleted).toHaveBeenCalled();
});
```

```tsx
// repository-picker.test.tsx
it("loads repositories of the chosen connection and preselects the default branch", async () => {
  mockList.mockResolvedValue({ items: [{ id: "i1", type: "github", name: "GH", config: {} }], total: 1, page: 1, limit: 100 });
  mockGet.mockImplementation(async (path: string) =>
    path.endsWith("/repositories") ? { items: [{ fullName: "o/r", defaultBranch: "develop" }] }
      : { items: ["develop", "main"] });
  const onChange = vi.fn();
  render(<RepositoryPicker value={null} onChange={onChange} />);
  fireEvent.change(await screen.findByLabelText("Conexão"), { target: { value: "i1" } });
  fireEvent.change(await screen.findByLabelText("Repositório"), { target: { value: "o/r" } });
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith({ integrationId: "i1", fullName: "o/r", baseBranch: "develop" }));
});

it("shows a link to Integrations when there is no Git connection", async () => {
  mockList.mockResolvedValue({ items: [], total: 0, page: 1, limit: 100 });
  render(<RepositoryPicker value={null} onChange={vi.fn()} />);
  expect(await screen.findByRole("link", { name: /Cadastrar conexão Git/i })).toHaveAttribute("href", "/integrations");
});
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** O `PipelineHeader` substitui o `<h1>` e a descrição atuais da página do editor. Terá:
  - nome clicável que vira `input` (Enter/blur salvam, Esc cancela, vazio mostra erro);
  - descrição editável (textarea de uma linha que cresce);
  - chip "Repositório: o/r (develop)" que abre o `RepositoryPicker` num popover (opção "Sem repositório" limpa);
  - menu "Mais ações" com Duplicar e Excluir (confirmação no `Modal`).
  A página salva cada alteração com `PUT` só daquele campo. `?new=1` liga `autoEditName`. A lista mostra no card: repositório, "Último run: Concluído há 5 min" (de `GET /pipelines/{id}/runs?limit=1`) e o link "Monitor".
- [ ] **Step 4: Run** → PASS; `tsc`, `lint`, `npx vitest run components/pipelines "app/(dashboard)/pipelines"`.
- [ ] **Step 5: Commit** — `git commit -m "feat(portal): nome, descricao, repositorio, excluir e duplicar pipeline"`

---

### Task 11: Portal — monitor com abas e markdown

**Files:**
- Create: `agent-portal/components/ui/markdown.tsx`, `agent-portal/components/monitor/run-header.tsx`, `stage-strip.tsx`, `results-tab.tsx`, `files-tab.tsx`, `logs-tab.tsx`, `history-tab.tsx`
- Modify: `agent-portal/components/monitor/pipeline-monitor.tsx` (vira o contêiner: estado, WS e abas; o grafo completo sai para um `Modal` "Ver grafo"), `agent-portal/package.json` (`react-markdown`, `remark-gfm`)
- Test: `agent-portal/components/ui/markdown.test.tsx`, `agent-portal/components/monitor/results-tab.test.tsx`, `files-tab.test.tsx`, `run-header.test.tsx`; ajustar `pipeline-monitor.test.tsx`

**Interfaces:**
- Consumes: `GET /api/runs/{id}/files`, `/files/content`, `/diff`, `/archive`, `POST /api/runs/{id}/publish` (Tasks 7/8); campos `prUrl`, `prNumber`, `publishStatus`, `publishError` do run (Task 4).
- Produces:
  - `Markdown({ children: string })`
  - `ResultsTab({ steps: { nodeId, name, status, output }[], focusNodeId?: string })`
  - `FilesTab({ runId })`
  - `RunHeader({ pipeline, run, onPublish, actions })`
  - `StageStrip({ steps, onSelect(nodeId) })`

- [ ] **Step 1: Instalar deps** — em `agent-portal/`: `npm install react-markdown@9 remark-gfm@4` (o nó roda sozinho; pode instalar).

- [ ] **Step 2: Failing tests**

```tsx
// markdown.test.tsx
it("renders headings, lists and code; keeps raw HTML as text", () => {
  const { container } = render(<Markdown>{"# Título\n\n- item\n\n`code`\n\n<script>alert(1)</script>"}</Markdown>);
  expect(container.querySelector("h1")?.textContent).toBe("Título");
  expect(container.querySelector("li")?.textContent).toBe("item");
  expect(container.querySelector("code")?.textContent).toBe("code");
  expect(container.querySelector("script")).toBeNull();
});

// results-tab.test.tsx
it("shows each agent output as rendered markdown in order, full width", () => {
  render(<ResultsTab steps={[
    { nodeId: "a", name: "Redator", status: "completed", output: { especificacao: "# Spec\n\n- RF-001" } },
    { nodeId: "b", name: "Revisor", status: "running", output: undefined },
  ]} />);
  const sections = screen.getAllByRole("region");
  expect(sections[0]).toHaveAccessibleName("Redator");
  expect(within(sections[0]).getByRole("heading", { name: "Spec" })).toBeInTheDocument();
  expect(within(sections[1]).getByText(/Em execução/)).toBeInTheDocument();
});

it("copies an output", async () => {
  const writeText = vi.fn();
  Object.assign(navigator, { clipboard: { writeText } });
  render(<ResultsTab steps={[{ nodeId: "a", name: "Redator", status: "completed", output: { especificacao: "texto" } }]} />);
  fireEvent.click(screen.getByRole("button", { name: "Copiar especificacao" }));
  expect(writeText).toHaveBeenCalledWith("texto");
});

// files-tab.test.tsx
it("lists files with status, opens text, marks binary and offers zip", async () => {
  mockGet.mockImplementation(async (p: string) => p.endsWith("/files")
    ? { items: [{ path: "src/a.py", size: 9, binary: false, status: "added" }, { path: "logo.png", size: 5, binary: true, status: "added" }] }
    : { path: "src/a.py", content: "print(1)", binary: false, tooLarge: false, size: 9 });
  render(<FilesTab runId="r1" />);
  fireEvent.click(await screen.findByRole("button", { name: /src\/a\.py/ }));
  expect(await screen.findByText("print(1)")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /logo\.png/ }));
  expect(screen.getByText(/Arquivo binário/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Baixar \.zip/ })).toHaveAttribute("href", "/api/runs/r1/archive");
});

// run-header.test.tsx
it("shows the PR link or the publish failure with retry", () => {
  const onPublish = vi.fn();
  const { rerender } = render(<RunHeader pipeline={makePipeline({ name: "P" })} run={makeRun({ status: "completed", publishStatus: "published", prUrl: "https://x/pull/3", prNumber: 3 })} onPublish={onPublish} actions={null} />);
  expect(screen.getByRole("link", { name: "PR #3" })).toHaveAttribute("href", "https://x/pull/3");
  rerender(<RunHeader pipeline={makePipeline({ name: "P" })} run={makeRun({ status: "completed", publishStatus: "failed", publishError: "token inválido ou sem acesso" })} onPublish={onPublish} actions={null} />);
  expect(screen.getByRole("alert")).toHaveTextContent("token inválido");
  fireEvent.click(screen.getByRole("button", { name: /Tentar publicar de novo/ }));
  expect(onPublish).toHaveBeenCalled();
});
```

O download do zip usa uma rota do portal `app/api/runs/[id]/archive/route.ts`, que faz proxy autenticado para o orchestrator com o token da sessão (o `<a href>` do navegador não manda `Authorization`). Teste da rota: `route.test.ts` verifica o header `Authorization` repassado e o `Content-Disposition`.

- [ ] **Step 3: Run** → FAIL. **Step 4: Implement.**
  - `Markdown`: `react-markdown` com `remarkPlugins={[remarkGfm]}`, sem `rehype-raw` (HTML vira texto), links com `target="_blank" rel="noreferrer"`, estilos de tipografia do design system.
  - Monitor:
    - cabeçalho = `RunHeader`;
    - abaixo, `StageStrip`, com chips horizontais por agente e aprovação, na ordem topológica do grafo, com status e clique que foca o resultado;
    - botão "Ver grafo" abre o `FlowEditor` somente leitura num `Modal` grande;
    - abas: Resultado (padrão), Arquivos do projeto, Logs e Histórico; o histórico atual migra para `history-tab.tsx` sem mudar comportamento;
    - `logs-tab.tsx` ocupa a largura total e ganha filtros por agente e por nível (`info`/`warn`/`error`), conforme a spec §6. Teste em `logs-tab.test.tsx`: com logs de 2 agentes, escolher o agente "Revisor" esconde as linhas do Redator; escolher "error" mostra só os erros;
    - aba Arquivos só aparece se `run` existe;
    - a aba ativa vai para a URL (`?tab=`); depois de executar pelo editor, o portal navega para `/pipelines/<id>/run?tab=resultado` (spec §7).
- [ ] **Step 5: Run** → PASS; `npx vitest run components/monitor components/ui`, `tsc`, `lint`.
- [ ] **Step 6: Commit** — `git commit -m "feat(portal): monitor com abas (Resultado em markdown, Arquivos, Logs, Historico) e link do PR"`

---

### Task 12: Portal — editor, execução, aprovações e agente

**Files:**
- Modify: `agent-portal/components/flow/agent-node.tsx` (largura 280px, nome em até 2 linhas com `-webkit-line-clamp: 2`, `title` com o nome completo)
- Create: `agent-portal/components/flow/validation-list.tsx` (lista clicável dos erros)
- Modify: `agent-portal/app/(dashboard)/pipelines/[id]/page.tsx` (o indicador "N erros" abre a `ValidationList`; clique seleciona o nó/aresta e centraliza)
- Modify: `agent-portal/components/EdgePanel.tsx` (textos: "Dados: leva a saída escolhida para a entrada do próximo agente e já define a ordem"; "Requer aprovação: pausa aqui até alguém aprovar")
- Modify: `agent-portal/components/flow/run-inputs-modal.tsx` (descrição da entrada, quando o agente tiver; linha "Repositório: o/r (develop)" ou "Sem repositório: baixe o resultado em .zip")
- Modify: `agent-portal/components/approvals/approval-panel.tsx` (seção "Arquivos alterados" com `GET /api/runs/{runId}/files` filtrando `status != null`, link para o monitor na aba Arquivos; dica curta sob cada botão)
- Modify: `agent-portal/components/agents/agent-preview.tsx` e a API `GET /api/agents/{id}` (campo `effectiveModel` = `LLM_MODEL` quando definido; `agent-orchestrator/app/api/agents.py`)
- Test: `validation-list.test.tsx`, casos novos em `agent-node.test.tsx`, `run-inputs-modal.test.tsx`, `approval-panel.test.tsx`, `agent-preview.test.tsx`; `agent-orchestrator/tests/test_agents_crud.py` (`effectiveModel`)

**Interfaces:**
- Produces: `ValidationList({ errors: ValidationError[], onSelect(target: { nodeId?: string; edgeId?: string }) })`; `Agent.effectiveModel?: string`.

- [ ] **Step 1: Failing tests** (principais)

```tsx
// validation-list.test.tsx
it("lists errors and selects the node or edge on click", () => {
  const onSelect = vi.fn();
  render(<ValidationList errors={[{ rule: 8, message: "\"Revisor\" é um nó órfão", nodeId: "n2" },
                                  { rule: 1, message: "mapeamento incompleto", edgeId: "e1" }]} onSelect={onSelect} />);
  fireEvent.click(screen.getByRole("button", { name: /nó órfão/ }));
  expect(onSelect).toHaveBeenCalledWith({ nodeId: "n2" });
  fireEvent.click(screen.getByRole("button", { name: /mapeamento incompleto/ }));
  expect(onSelect).toHaveBeenCalledWith({ edgeId: "e1" });
});

// agent-node.test.tsx
it("shows the full agent name in the title and does not cut it to one line", () => {
  renderNode({ label: "Redator de Especificações Técnicas" });
  const name = screen.getByText("Redator de Especificações Técnicas");
  expect(name).toHaveAttribute("title", "Redator de Especificações Técnicas");
  expect(name.style.webkitLineClamp).toBe("2");
});

// run-inputs-modal.test.tsx
it("shows the repository that will be used", () => {
  render(<RunInputsModal open agentName="Redator" inputs={[]} repository={{ integrationId: "i", fullName: "o/r", baseBranch: "develop" }} onCancel={() => {}} onSubmit={() => {}} />);
  expect(screen.getByText("Repositório: o/r (develop)")).toBeInTheDocument();
});
```

```python
# test_agents_crud.py
async def test_effective_model_reflects_llm_model(client, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "llm_model", "Qwen3.8-27B-Q8_0")
    created = await client.post("/api/agents", json=minimal_agent(model="gpt-4o"))
    assert created.json()["model"] == "gpt-4o"
    assert created.json()["effectiveModel"] == "Qwen3.8-27B-Q8_0"
```

- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** o descrito em Files. `effectiveModel` é `settings.llm_model or agent.model` na resposta. O preview mostra "Modelo: Qwen3.8-27B-Q8_0 (definido pelo servidor)" quando difere de `model`. `RunInputsModal` ganha a prop `repository`.
- [ ] **Step 4: Run** → PASS (portal e orchestrator). **Step 5: Commit** — `git commit -m "feat(portal): nomes completos, erros clicaveis, execucao e aprovacao com repositorio e arquivos"`

---

### Task 13: Integração ponta a ponta com repositório Git local, E2E e validação real

**Files:**
- Modify: `docker-compose.yml` (serviço `git-test`, `profiles: ["test"]`: imagem `alpine/git`, `git daemon --reuseaddr --export-all --enable=receive-pack --base-path=/srv/git`, volume `git-test-repos`)
- Create: `tests/integration/test_09_git_project.py`
- Modify: `e2e/tests/05-pipeline-editor.spec.ts`, `e2e/tests/06-run-monitor.spec.ts`; create `e2e/tests/10-integrations.spec.ts`
- Modify: `docs/superpowers/validacoes/PENDENCIAS.md`; create `docs/superpowers/validacoes/qa-projeto-git.md`

**Interfaces:**
- Consumes: tudo das Tasks 1–12. Um provedor "local" para testes: `GitHubProvider` com `GITHUB_API_BASE` apontando para um servidor fake (`tests/integration/fake_git_api.py`, FastAPI mínimo: `/user/repos`, `/repos/{o}/{r}/branches`, `POST /repos/{o}/{r}/pulls` guardando os PRs, `GET /repos/{o}/{r}/pulls`), e `clone_url` sobrescrito por `GIT_CLONE_BASE_OVERRIDE=git://git-test/` (settings) só no perfil de teste.

- [ ] **Step 1: Failing integration test**

```python
# tests/integration/test_09_git_project.py
def test_pipeline_writes_files_and_opens_pr(user, git_test_repo, fake_git_api):
    integ = user.post("/api/integrations", json={"type": "github", "name": "local", "config": {"token": "t"}}).json()
    a1 = create_agent(user, "dev", outputs=[{"name": "codigo", "type": "code", "required": True}])
    pipe = user.post("/api/pipelines", json={**single_node_graph(a1),
        "repository": {"integrationId": integ["id"], "fullName": "qa/projeto", "baseBranch": "main"}}).json()
    run = user.post(f"/api/pipelines/{pipe['id']}/execute", json={"inputs": {"ideia": "hello"}}).json()
    wait_until(lambda: run_status(user, pipe["id"]) == "completed", timeout=90, desc="run concluído")
    files = user.get(f"/api/runs/{run['runId']}/files").json()["items"]
    assert any(f["path"] == "result.md" for f in files)       # o worker mock grava as saídas em result.md
    r = latest_run(user, pipe["id"])
    assert r["publishStatus"] == "published" and r["prUrl"]
    assert "agent-portal/" in git_test_repo.branches()
```

No worker, com `LLM_PROVIDER=mock` e workspace definido, o agente mock grava `result.md` com as saídas no workspace (comportamento determinístico para testes, em `MockLLMClient` via uma tool call `write_file` quando existe workspace). Isso permite provar arquivos → commit → PR sem LLM real. Coberto por teste unitário no worker, neste mesmo step.

- [ ] **Step 2: Run** com `docker compose -p squad-agentica --profile test up -d git-test` + fake API → FAIL; implementar os fixtures (`git_test_repo` cria `qa/projeto.git` no volume do `git-test` com um commit inicial em `main`) → PASS.
- [ ] **Step 3: E2E** — `10-integrations.spec.ts`: cadastrar conexão (token de teste), testar (API fake), vincular ao pipeline pelo `RepositoryPicker`, executar, abrir o monitor na aba Arquivos e ver o link do PR. Atualizar 05/06 para o novo cabeçalho (nome editável) e abas. Rodar a suíte completa.
- [ ] **Step 4: Suítes completas em mock + build:**
  - orchestrator, worker e portal (vitest, tsc e lint);
  - integração (`tests/integration`);
  - E2E completo;
  - `npm run build` e reinício do portal.
  Colar os resultados em `qa-projeto-git.md`.
- [ ] **Step 5: Validação real assistida:**
  - voltar o stack ao provedor real;
  - o usuário cadastra na tela Integrações os PATs de GitHub e/ou Azure DevOps e cria um repositório de teste;
  - eu vinculo o repositório a um pipeline "Analista → Desenvolvedor → Revisor", executo com o Qwen, aprovo e confiro no navegador: aba Resultado legível, arquivos na aba Arquivos e o PR aberto no provedor com os arquivos.
  - Registrar prints e resultado em `qa-projeto-git.md`; pendências em `PENDENCIAS.md`.
- [ ] **Step 6: Commit** — `git commit -m "test(git): projeto ponta a ponta com repositorio local; validacao real registrada"`
