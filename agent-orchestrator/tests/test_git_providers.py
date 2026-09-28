import json

import httpx
import pytest

from app.integrations.git_providers import (
    AzureDevOpsProvider,
    GitHubProvider,
    GitProviderError,
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
