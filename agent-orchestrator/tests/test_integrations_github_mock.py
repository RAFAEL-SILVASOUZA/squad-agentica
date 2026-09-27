"""Tests for GitHub integration with mocked httpx.

Dono: be-integrations (FASE 4).

Testa:
- list_repos, list_pulls, list_issues, get_pr_diff
- Token inválido (401)
- Rate limit (403 com X-RateLimit-Remaining: 0)
- Não vazamento do token (token nunca aparece em respostas/erros)
- wrap_external_data helper
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.errors import AppError
from app.integrations.github import (
    EXTERNAL_DATA_END,
    EXTERNAL_DATA_START,
    get_pr_diff,
    list_issues,
    list_pulls,
    list_repos,
    wrap_external_data,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(responses: list[httpx.Response]) -> AsyncMock:
    """Cria um mock de httpx.AsyncClient que retorna as respostas em ordem.

    O mock suporta `async with` e `.get()` que retorna as respostas sequencialmente.
    """
    call_count = {"n": 0}

    async def _get(*args, **kwargs) -> httpx.Response:
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = _get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


def _response(
    status_code: int,
    json_data: list | dict | None = None,
    text: str = "",
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Cria uma httpx.Response."""
    if json_data is not None:
        content = json.dumps(json_data).encode()
    else:
        content = text.encode()
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers=headers or {},
        request=httpx.Request("GET", "https://api.github.com/test"),
    )


# ---------------------------------------------------------------------------
# Tests: wrap_external_data
# ---------------------------------------------------------------------------


class TestWrapExternalData:
    def test_wraps_content(self) -> None:
        result = wrap_external_data("some PR content")
        assert result.startswith(EXTERNAL_DATA_START)
        assert result.endswith(EXTERNAL_DATA_END)
        assert "some PR content" in result

    def test_markers_are_correct(self) -> None:
        assert EXTERNAL_DATA_START == "<<<EXTERNAL_DATA>>>"
        assert EXTERNAL_DATA_END == "<<<END_EXTERNAL_DATA>>>"


# ---------------------------------------------------------------------------
# Tests: list_repos
# ---------------------------------------------------------------------------


class TestListRepos:
    @pytest.mark.asyncio
    async def test_list_repos_success(self) -> None:
        mock_data = [
            {"id": 1, "name": "repo1", "full_name": "org/repo1", "private": False},
            {"id": 2, "name": "repo2", "full_name": "org/repo2", "private": True},
        ]
        mock_client = _make_mock_client([_response(200, json_data=mock_data)])

        with patch("app.core.config.settings.github_token", "fake-token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                repos = await list_repos("myorg")

        assert len(repos) == 2
        assert repos[0]["name"] == "repo1"
        assert repos[0]["full_name"] == "org/repo1"
        assert repos[1]["private"] is True

    @pytest.mark.asyncio
    async def test_api_base_configurable(self) -> None:
        """F17: GITHUB_API_BASE aponta para GitHub Enterprise ou servidor fake."""
        mock_client = _make_mock_client([_response(200, json_data=[])])
        urls: list[str] = []
        original_get = mock_client.get

        async def _spy_get(url: str, *args, **kwargs) -> httpx.Response:
            urls.append(url)
            return await original_get(url, *args, **kwargs)

        mock_client.get = _spy_get
        with patch("app.core.config.settings.github_token", "fake-token"):
            with patch("app.core.config.settings.github_api_base", "http://fake-gh:8080/api/v3/"):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    await list_repos("myorg")
        assert urls == ["http://fake-gh:8080/api/v3/users/myorg/repos"]

    @pytest.mark.asyncio
    async def test_list_repos_token_not_configured(self) -> None:
        with patch("app.core.config.settings.github_token", ""):
            with pytest.raises(AppError) as exc_info:
                await list_repos("myorg")
        assert exc_info.value.status_code == 502
        assert exc_info.value.code == "github_error"
        # Token não deve aparecer na mensagem de erro
        assert "fake-token" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_list_repos_invalid_token(self) -> None:
        mock_client = _make_mock_client(
            [_response(401, json_data={"message": "Bad credentials"})]
        )

        with patch("app.core.config.settings.github_token", "bad-token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_repos("myorg")

        assert exc_info.value.status_code == 502
        assert exc_info.value.code == "github_error"
        # Token não deve vazar no erro
        assert "bad-token" not in str(exc_info.value)
        assert "bad-token" not in json.dumps(exc_info.value.details or {})

    @pytest.mark.asyncio
    async def test_list_repos_rate_limit(self) -> None:
        mock_client = _make_mock_client(
            [
                _response(
                    403,
                    json_data={"message": "rate limit exceeded"},
                    headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
                )
            ]
        )

        with patch("app.core.config.settings.github_token", "valid-token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_repos("myorg")

        assert exc_info.value.status_code == 502
        assert exc_info.value.code == "github_error"
        assert "Rate limit" in exc_info.value.details["message"]
        assert exc_info.value.details.get("retryAfter") == 1700000000

    @pytest.mark.asyncio
    async def test_list_repos_forbidden_no_rate_limit(self) -> None:
        """403 sem rate limit (sem permissão)."""
        mock_client = _make_mock_client(
            [
                _response(
                    403,
                    json_data={"message": "Forbidden"},
                    headers={"X-RateLimit-Remaining": "5000"},
                )
            ]
        )

        with patch("app.core.config.settings.github_token", "valid-token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_repos("myorg")

        assert exc_info.value.status_code == 502
        assert "sem permissão" in exc_info.value.details["message"]


# ---------------------------------------------------------------------------
# Tests: list_pulls
# ---------------------------------------------------------------------------


class TestListPulls:
    @pytest.mark.asyncio
    async def test_list_pulls_success(self) -> None:
        mock_data = [
            {
                "number": 1,
                "title": "Add feature",
                "state": "open",
                "user": {"login": "dev1"},
                "html_url": "https://github.com/org/repo/pull/1",
            },
        ]
        mock_client = _make_mock_client([_response(200, json_data=mock_data)])

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                pulls = await list_pulls("org", "repo", state="open")

        assert len(pulls) == 1
        assert pulls[0]["number"] == 1
        assert pulls[0]["title"] == "Add feature"
        assert pulls[0]["author"] == "dev1"

    @pytest.mark.asyncio
    async def test_list_pulls_not_found(self) -> None:
        mock_client = _make_mock_client(
            [_response(404, json_data={"message": "Not Found"})]
        )

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_pulls("org", "nonexistent")

        assert exc_info.value.status_code == 404
        assert exc_info.value.code == "github_resource_not_found"


# ---------------------------------------------------------------------------
# Tests: list_issues
# ---------------------------------------------------------------------------


class TestListIssues:
    @pytest.mark.asyncio
    async def test_list_issues_success(self) -> None:
        mock_data = [
            {
                "number": 10,
                "title": "Bug fix",
                "state": "open",
                "labels": [{"name": "bug"}, {"name": "critical"}],
                "user": {"login": "dev2"},
                "html_url": "https://github.com/org/repo/issues/10",
            },
        ]
        mock_client = _make_mock_client([_response(200, json_data=mock_data)])

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                issues = await list_issues("org", "repo", state="open", labels=["bug"])

        assert len(issues) == 1
        assert issues[0]["number"] == 10
        assert issues[0]["labels"] == ["bug", "critical"]
        assert issues[0]["author"] == "dev2"

    @pytest.mark.asyncio
    async def test_list_issues_no_labels(self) -> None:
        mock_data = [
            {
                "number": 5,
                "title": "No labels",
                "state": "closed",
                "labels": [],
                "user": {"login": "dev3"},
                "html_url": "https://github.com/org/repo/issues/5",
            },
        ]
        mock_client = _make_mock_client([_response(200, json_data=mock_data)])

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                issues = await list_issues("org", "repo")

        assert len(issues) == 1
        assert issues[0]["labels"] == []


# ---------------------------------------------------------------------------
# Tests: get_pr_diff
# ---------------------------------------------------------------------------


class TestGetPrDiff:
    @pytest.mark.asyncio
    async def test_get_pr_diff_success(self) -> None:
        diff_resp = _response(200, text="--- a/file.py\n+++ b/file.py\n+new line")
        files_resp = _response(
            200,
            json_data=[
                {"filename": "file.py", "additions": 1, "deletions": 0},
                {"filename": "other.py", "additions": 5, "deletions": 2},
            ],
        )
        mock_client = _make_mock_client([diff_resp, files_resp])

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                result = await get_pr_diff("org", "repo", 42)

        assert "diff" in result
        assert "new line" in result["diff"]
        assert len(result["files"]) == 2
        assert result["files"][0]["path"] == "file.py"
        assert result["files"][0]["additions"] == 1
        assert result["files"][1]["deletions"] == 2

    @pytest.mark.asyncio
    async def test_get_pr_diff_not_found(self) -> None:
        mock_client = _make_mock_client(
            [_response(404, json_data={"message": "Not Found"})]
        )

        with patch("app.core.config.settings.github_token", "token"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await get_pr_diff("org", "repo", 999)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: Token security (não vazamento)
# ---------------------------------------------------------------------------


class TestTokenSecurity:
    @pytest.mark.asyncio
    async def test_token_never_in_error_message(self) -> None:
        """O token nunca deve aparecer em mensagens de erro."""
        secret_token = "ghp_supersecrettoken12345"
        mock_client = _make_mock_client(
            [_response(401, json_data={"message": "Bad credentials"})]
        )

        with patch("app.core.config.settings.github_token", secret_token):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_repos("myorg")

        error_str = str(exc_info.value)
        details_str = json.dumps(exc_info.value.details or {})
        assert secret_token not in error_str
        assert secret_token not in details_str

    @pytest.mark.asyncio
    async def test_token_never_in_rate_limit_error(self) -> None:
        """O token nunca deve aparecer em erros de rate limit."""
        secret_token = "ghp_anothersecret67890"
        mock_client = _make_mock_client(
            [
                _response(
                    403,
                    json_data={"message": "rate limit"},
                    headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
                )
            ]
        )

        with patch("app.core.config.settings.github_token", secret_token):
            with patch("httpx.AsyncClient", return_value=mock_client):
                with pytest.raises(AppError) as exc_info:
                    await list_pulls("org", "repo")

        error_str = str(exc_info.value)
        details_str = json.dumps(exc_info.value.details or {})
        assert secret_token not in error_str
        assert secret_token not in details_str
