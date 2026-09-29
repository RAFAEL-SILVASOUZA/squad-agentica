import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.git_providers import (
    AzureDevOpsProvider,
    GitHubProvider,
    GitProviderError,
    provider_for,
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
    pr = await gh.create_pull_request(
        "o/r", "agent-portal/x-1", "main", "Título", "Corpo"
    )
    assert (pr.number, pr.url) == (7, "https://github.com/o/r/pull/7")
    assert seen["body"] == {
        "title": "Título",
        "head": "agent-portal/x-1",
        "base": "main",
        "body": "Corpo",
    }
    assert seen["auth"] == "Bearer ghp_x"
    assert (
        gh.clone_url("o/r")
        == "https://x-access-token:ghp_x@github.com/o/r.git"
    )


@pytest.mark.asyncio
async def test_github_bad_token_message_has_no_secret():
    gh = GitHubProvider(
        token="ghp_secret",
        api_base="https://api.github.com",
        transport=_transport({
            ("GET", "/user/repos"): lambda r: (401, {"message": "Bad credentials"}),
        }),
    )
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


# ---------------------------------------------------------------------------
# Tests: provider_for() factory
# ---------------------------------------------------------------------------


def test_provider_for_github(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.core.secrets import encrypt_secret

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integrations_secret_key", key)

    integration = SimpleNamespace(
        type="github",
        config={"token_encrypted": encrypt_secret("ghp_test")},
    )
    provider = provider_for(integration)
    assert isinstance(provider, GitHubProvider)


def test_github_clone_base_override_is_test_only_and_off_by_default():
    gh = GitHubProvider("ghp_x")
    assert gh.clone_url("o/r") == "https://x-access-token:ghp_x@github.com/o/r.git"
    local = GitHubProvider("ghp_x", clone_base="git://git-test/")
    # Remoto local de teste (git daemon): sem credencial na URL.
    assert local.clone_url("qa/projeto") == "git://git-test/qa/projeto.git"


def test_provider_for_github_uses_clone_base_override(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import Settings, settings
    from app.core.secrets import encrypt_secret

    monkeypatch.setattr(settings, "integrations_secret_key", Fernet.generate_key().decode())
    # Desligado por padrão (o perfil de teste o liga por ambiente).
    assert Settings.model_fields["git_clone_base_override"].default == ""
    monkeypatch.setattr(settings, "git_clone_base_override", "git://git-test")
    integration = SimpleNamespace(
        type="github", config={"token_encrypted": encrypt_secret("ghp_test")}
    )
    assert provider_for(integration).clone_url("qa/p") == "git://git-test/qa/p.git"


def test_provider_for_azure(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.core.secrets import encrypt_secret

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integrations_secret_key", key)

    integration = SimpleNamespace(
        type="azure",
        config={"token_encrypted": encrypt_secret("az_test"), "organization": "org"},
    )
    provider = provider_for(integration)
    assert isinstance(provider, AzureDevOpsProvider)


def test_provider_for_azure_without_organization(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.core.secrets import encrypt_secret

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integrations_secret_key", key)

    integration = SimpleNamespace(
        type="azure",
        config={"token_encrypted": encrypt_secret("az_test")},
    )
    with pytest.raises(GitProviderError) as exc:
        provider_for(integration)
    assert (
        "Conexão Azure DevOps sem organização" in exc.value.message
    )


def test_provider_for_unsupported_type(monkeypatch):
    from cryptography.fernet import Fernet

    from app.core.config import settings
    from app.core.secrets import encrypt_secret

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integrations_secret_key", key)

    integration = SimpleNamespace(
        type="rivvn",
        config={"token_encrypted": encrypt_secret("token")},
    )
    with pytest.raises(GitProviderError) as exc:
        provider_for(integration)
    assert "não é um provedor Git" in exc.value.message


# ---------------------------------------------------------------------------
# Revisão final I5: paginação (Link do GitHub, continuationToken do Azure)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_github_list_repos_follows_link_header_up_to_10_pages():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        page = int(request.url.params.get("page", "1"))
        headers = {}
        # Sempre há "próxima": o provedor precisa parar em 10 páginas.
        nxt = f"https://api.github.com/user/repos?per_page=100&page={page + 1}"
        headers["Link"] = f'<{nxt}>; rel="next", <https://api.github.com/x>; rel="last"'
        body = [{"full_name": f"o/r{page}-{i}", "default_branch": "main"} for i in range(100)]
        return httpx.Response(200, json=body, headers=headers)

    gh = GitHubProvider(token="ghp_x", transport=httpx.MockTransport(handler))
    repos = await gh.list_repos()
    assert len(calls) == 10
    assert len(repos) == 1000
    assert repos[-1].full_name == "o/r10-99"
    # A 1ª chamada leva os parâmetros; as seguintes usam a URL do Link.
    assert "sort=updated" in calls[0]


@pytest.mark.asyncio
async def test_github_list_branches_paginates_and_stops_without_next():
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("page", "1"))
        headers = {}
        if page < 3:
            headers["Link"] = (
                f'<https://api.github.com/repos/o/r/branches?per_page=100&page={page + 1}>;'
                ' rel="next"'
            )
        return httpx.Response(200, json=[{"name": f"b{page}"}], headers=headers)

    gh = GitHubProvider(token="ghp_x", transport=httpx.MockTransport(handler))
    assert await gh.list_branches("o/r") == ["b1", "b2", "b3"]


@pytest.mark.asyncio
async def test_github_pagination_never_follows_other_host():
    hosts = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts.append(request.url.host)
        return httpx.Response(
            200, json=[{"name": "main"}],
            headers={"Link": '<https://evil.example/steal?page=2>; rel="next"'},
        )

    gh = GitHubProvider(token="ghp_x", transport=httpx.MockTransport(handler))
    assert await gh.list_branches("o/r") == ["main"]
    assert hosts == ["api.github.com"]


@pytest.mark.asyncio
async def test_azure_branches_follow_continuation_token():
    seen_tokens = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.url.params.get("continuationToken")
        seen_tokens.append(token)
        if token is None:
            return httpx.Response(
                200, json={"value": [{"name": "refs/heads/main"}]},
                headers={"x-ms-continuationtoken": "abc"},
            )
        return httpx.Response(200, json={"value": [{"name": "refs/heads/dev"}]})

    az = AzureDevOpsProvider(token="az_x", organization="org",
                             transport=httpx.MockTransport(handler))
    assert await az.list_branches("Proj/app") == ["main", "dev"]
    assert seen_tokens == [None, "abc"]
