"""Tests for app/runtime/worker_client.py.

Covers (per prompt requirements):
  - Success: worker responds 200, client returns WorkerResponse
  - 5xx with retry and backoff: worker returns 500, client retries 3x
  - Timeout: worker takes too long, client returns failure
  - Worker down (connection error): client returns failure without exception
  - Header X-Worker-Token present in request

Uses httpx MockTransport for deterministic HTTP mocking.
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest

from app.compiler.graph_builder import WorkerResponse
from app.runtime.worker_client import HttpWorkerClient

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _success_response(status_code: int = 200, body: dict | None = None) -> httpx.Response:
    """Create a mock HTTP response."""
    if body is None:
        body = {
            "status": "completed",
            "outputs": {"result": "hello"},
            "action": "follow",
            "iterations": 1,
            "logs": ["done"],
        }
    return httpx.Response(
        status_code=status_code,
        json=body,
        headers={"Content-Type": "application/json"},
    )


def _make_client(
    handler: httpx.MockTransport | None = None,
    worker_url: str = "http://nginx:8081/execute",
    worker_token: str = "test-token",
    max_retries: int = 3,
    backoff_base: float = 0.01,  # Fast backoff for tests
) -> HttpWorkerClient:
    """Create an HttpWorkerClient with a mock transport."""
    client = HttpWorkerClient(
        worker_url=worker_url,
        worker_token=worker_token,
        max_retries=max_retries,
        backoff_base=backoff_base,
    )
    if handler is not None:
        # Patch the _post method to use mock transport.
        _patch_post(client, handler)
    return client


def _patch_post(client: HttpWorkerClient, handler: httpx.MockTransport) -> None:
    """Replace _post with a version that uses the mock transport."""

    async def mock_post(
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> httpx.Response:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, timeout=timeout) as c:
            response = await c.post(
                client._worker_url,
                json=body,
                headers=headers,
            )
            response.raise_for_status()
            return response

    client._post = mock_post


# ---------------------------------------------------------------------------
# Tests: Success
# ---------------------------------------------------------------------------


class TestWorkerClientSuccess:
    """Worker responds 200: client returns WorkerResponse with data."""

    async def test_success_returns_completed(self):
        """Worker returns 200 with status=completed."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _success_response(200, {
                "status": "completed",
                "outputs": {"answer": "42"},
                "action": "follow",
                "iterations": 1,
                "logs": ["executed"],
            })

        client = _make_client(handler)
        result = await client.execute("agent-1", "node-1", {"prompt": "hi"})

        assert isinstance(result, WorkerResponse)
        assert result.status == "completed"
        assert result.outputs == {"answer": "42"}
        assert result.action == "follow"
        assert result.iterations == 1
        assert result.logs == ["executed"]
        assert result.error is None

    async def test_success_returns_failed_status(self):
        """Worker returns 200 with status=failed (agent-level failure)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return _success_response(200, {
                "status": "failed",
                "outputs": {},
                "action": "follow",
                "iterations": 1,
                "logs": ["agent error"],
                "error": "agent crashed",
            })

        client = _make_client(handler)
        result = await client.execute("agent-1", "node-1", {"prompt": "hi"})

        assert result.status == "failed"
        assert result.error == "agent crashed"
        assert result.outputs == {}


# ---------------------------------------------------------------------------
# Tests: Retry with backoff (5xx)
# ---------------------------------------------------------------------------


class TestWorkerClientRetry:
    """Worker returns 5xx: client retries with backoff."""

    async def test_5xx_retries_then_succeeds(self):
        """First two attempts return 500, third succeeds."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return httpx.Response(500, json={"error": "internal"})
            return _success_response(200, {
                "status": "completed",
                "outputs": {"ok": True},
                "action": "follow",
                "iterations": 1,
                "logs": [],
            })

        client = _make_client(handler, backoff_base=0.01)
        result = await client.execute("agent-1", "node-1", {})

        assert result.status == "completed"
        assert call_count == 3

    async def test_5xx_all_retries_exhausted(self):
        """All 3 attempts return 500: client returns failed (no exception)."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(500, json={"error": "internal"})

        client = _make_client(handler, backoff_base=0.01)
        result = await client.execute("agent-1", "node-1", {})

        assert result.status == "failed"
        assert result.error is not None
        assert "500" in result.error
        assert call_count == 3  # 3 attempts total

    async def test_502_retries(self):
        """502 (bad gateway) triggers retry."""
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(502, json={"error": "bad gateway"})

        client = _make_client(handler, backoff_base=0.01)
        result = await client.execute("agent-1", "node-1", {})

        assert result.status == "failed"
        assert call_count == 3


# ---------------------------------------------------------------------------
# Tests: Timeout
# ---------------------------------------------------------------------------


class TestWorkerClientTimeout:
    """Worker takes too long: client returns failure."""

    async def test_timeout_returns_failed(self):
        """Request times out: client returns failed without exception."""

        async def slow_post(body, headers, timeout):
            raise httpx.TimeoutException("timed out")

        client = HttpWorkerClient(
            worker_url="http://nginx:8081/execute",
            worker_token="test-token",
            max_retries=3,
            backoff_base=0.01,
        )
        client._post = slow_post

        result = await client.execute("agent-1", "node-1", {}, timeout=5)

        assert result.status == "failed"
        assert "timeout" in result.error.lower()

    async def test_timeout_retries_all_attempts(self):
        """Timeout on all attempts: still returns failed (no exception)."""
        call_count = 0

        async def always_timeout(body, headers, timeout):
            nonlocal call_count
            call_count += 1
            raise httpx.TimeoutException("timed out")

        client = HttpWorkerClient(
            worker_url="http://nginx:8081/execute",
            worker_token="test-token",
            max_retries=3,
            backoff_base=0.01,
        )
        client._post = always_timeout

        result = await client.execute("agent-1", "node-1", {}, timeout=5)

        assert result.status == "failed"
        assert call_count == 3


# ---------------------------------------------------------------------------
# Tests: Worker down (connection error)
# ---------------------------------------------------------------------------


class TestWorkerClientDown:
    """Worker unreachable: client returns failure without exception (ADR-001)."""

    async def test_connection_error_returns_failed(self):
        """Worker is down (connection refused): no exception, returns failed."""

        async def conn_error_post(body, headers, timeout):
            raise httpx.ConnectError("connection refused")

        client = HttpWorkerClient(
            worker_url="http://nginx:8081/execute",
            worker_token="test-token",
            max_retries=3,
            backoff_base=0.01,
        )
        client._post = conn_error_post

        result = await client.execute("agent-1", "node-1", {})

        assert result.status == "failed"
        assert result.error is not None
        assert "connection" in result.error.lower()
        assert result.outputs == {}
        assert result.action == "follow"

    async def test_worker_down_never_raises(self):
        """ADR-001 golden rule: even with worker completely down, no exception."""
        call_count = 0

        async def always_down(body, headers, timeout):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("no route to host")

        client = HttpWorkerClient(
            worker_url="http://nginx:8081/execute",
            worker_token="test-token",
            max_retries=3,
            backoff_base=0.01,
        )
        client._post = always_down

        # This must NOT raise.
        result = await client.execute("agent-1", "node-1", {"data": "test"})

        assert result.status == "failed"
        assert call_count == 3
        assert result.logs  # Has at least one log entry


# ---------------------------------------------------------------------------
# Tests: Header X-Worker-Token
# ---------------------------------------------------------------------------


class TestWorkerClientHeader:
    """X-Worker-Token header is present in every request."""

    async def test_token_header_present(self):
        """The X-Worker-Token header is sent with the correct value."""
        captured_headers: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_headers.update(dict(request.headers))
            return _success_response()

        client = _make_client(handler, worker_token="my-secret-token")
        await client.execute("agent-1", "node-1", {})

        assert "x-worker-token" in captured_headers
        assert captured_headers["x-worker-token"] == "my-secret-token"

    async def test_token_header_on_retry(self):
        """Token header is present on all retry attempts."""
        call_count = 0
        tokens_seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            tokens_seen.append(request.headers.get("x-worker-token", ""))
            if call_count < 3:
                return httpx.Response(500, json={"error": "fail"})
            return _success_response()

        client = _make_client(handler, worker_token="retry-token", backoff_base=0.01)
        await client.execute("agent-1", "node-1", {})

        assert len(tokens_seen) == 3
        assert all(t == "retry-token" for t in tokens_seen)


# ---------------------------------------------------------------------------
# Tests: Request body format
# ---------------------------------------------------------------------------


class TestWorkerClientBody:
    """Request body matches the contract (§2.3)."""

    async def test_body_format(self):
        """Body has agentId, nodeId, inputs, timeout (camelCase)."""
        captured_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content))
            return _success_response()

        client = _make_client(handler)
        await client.execute("agent-uuid-123", "node-42", {"prompt": "test"}, timeout=30)

        assert captured_body["agentId"] == "agent-uuid-123"
        assert captured_body["nodeId"] == "node-42"
        assert captured_body["inputs"] == {"prompt": "test"}
        assert captured_body["timeout"] == 30

    async def test_default_timeout_is_60(self):
        """Default timeout in body is 60 seconds."""
        captured_body: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured_body.update(json.loads(request.content))
            return _success_response()

        client = _make_client(handler)
        await client.execute("agent-1", "node-1", {})

        assert captured_body["timeout"] == 60

    async def test_workspace_dir_in_body_only_when_set(self):
        """``workspaceDir`` vai no corpo só quando o run tem workspace."""
        bodies: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            bodies.append(json.loads(request.content))
            return _success_response()

        client = _make_client(handler)
        await client.execute("agent-1", "node-1", {}, workspace_dir="/workspaces/r1")
        await client.execute("agent-1", "node-1", {})

        assert bodies[0]["workspaceDir"] == "/workspaces/r1"
        assert "workspaceDir" not in bodies[1]


# ---------------------------------------------------------------------------
# Tests: Backoff timing (approximate)
# ---------------------------------------------------------------------------


class TestWorkerClientBackoff:
    """Backoff delays are approximately 2s, 4s, 8s (scaled in tests)."""

    async def test_backoff_delays_increase(self):
        """Backoff delays increase exponentially between retries."""
        call_times: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            call_times.append(time.monotonic())
            return httpx.Response(500, json={"error": "fail"})

        # Use a measurable backoff base (0.1s -> 0.1, 0.2, 0.4).
        client = _make_client(handler, backoff_base=0.1)
        await client.execute("agent-1", "node-1", {})

        assert len(call_times) == 3
        # Delay between attempt 1 and 2 should be ~0.1s
        delay1 = call_times[1] - call_times[0]
        # Delay between attempt 2 and 3 should be ~0.2s
        delay2 = call_times[2] - call_times[1]
        # Second delay should be roughly double the first (with tolerance).
        assert delay2 > delay1 * 1.5
