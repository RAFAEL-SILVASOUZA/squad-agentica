"""HTTP implementation of the WorkerClient Protocol (compiler contract).

Implements the HTTP call from orchestrator to worker per CONTRATO-TECNICO.md
§2.3:
  - POST http://nginx:8081/execute
  - Header: X-Worker-Token: <WORKER_TOKEN>
  - Body: {"agentId": "uuid", "nodeId": "node-1", "inputs": {...}, "timeout": 60}
  - Response 200: {"status": "completed"|"failed", "outputs": {...},
    "action": ..., "iterations": int, "logs": [str]}

Retry: 3 attempts with exponential backoff (2s, 4s, 8s).
Timeout: per-request, configurable.

ADR-001 (golden rule): NEVER propagates an exception to the node function.
Any failure (timeout, 5xx, connection error, all retries exhausted) returns
a WorkerResponse with status="failed" and an error message. The graph does
NOT abort; the route_fn sends to END.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from app.compiler.graph_builder import WorkerResponse

logger = logging.getLogger(__name__)

# Default worker URL (internal NGINX route, §2.3).
DEFAULT_WORKER_URL = "http://nginx:8081/execute"

# Retry configuration (CONTRATO-TECNICO.md §2.3: 3 tentativas, backoff 2s/4s/8s).
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2.0  # 2s, 4s, 8s (exponential: base * 2^attempt)

# Default per-request timeout (seconds).
DEFAULT_TIMEOUT = 60.0


class HttpWorkerClient:
    """HTTP implementation of the WorkerClient Protocol.

    Implements:
        async def execute(agent_id, node_id, inputs, *, timeout=60) -> WorkerResponse

    Never raises (ADR-001). All failures return WorkerResponse(status="failed").

    Configuration via environment variables:
        WORKER_URL: override the worker endpoint (default: http://nginx:8081/execute)
        WORKER_TOKEN: shared secret for X-Worker-Token header
    """

    def __init__(
        self,
        worker_url: str | None = None,
        worker_token: str | None = None,
        max_retries: int = MAX_RETRIES,
        backoff_base: float = BACKOFF_BASE_SECONDS,
    ) -> None:
        self._worker_url = worker_url or os.environ.get("WORKER_URL", DEFAULT_WORKER_URL)
        self._worker_token = worker_token or os.environ.get("WORKER_TOKEN", "")
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    async def execute(
        self,
        agent_id: str,
        node_id: str,
        inputs: dict[str, Any],
        *,
        timeout: int = 60,
    ) -> WorkerResponse:
        """Execute an agent on the worker. NEVER raises (ADR-001).

        Args:
            agent_id: UUID of the agent to execute.
            node_id: Node ID in the pipeline graph (for logging/correlation).
            inputs: Input data for the agent.
            timeout: Per-request timeout in seconds (sent in body to worker).

        Returns:
            WorkerResponse with status="completed" on success, or
            status="failed" with error message on any failure.
        """
        body = {
            "agentId": agent_id,
            "nodeId": node_id,
            "inputs": inputs,
            "timeout": timeout,
        }
        headers = {
            "X-Worker-Token": self._worker_token,
            "Content-Type": "application/json",
        }

        last_error: str = "unknown error"
        # F14: ``worker_down`` = falhas por indisponibilidade (timeout, erro
        # de conexão, 5xx do pool/replica caída). 4xx do worker (ex.: token
        # inválido) indica worker ALCANÇÁVEL com erro de configuração: não é
        # "worker fora" e o run falha (comportamento antigo).
        worker_down = True

        for attempt in range(self._max_retries):
            try:
                response = await self._post(body, headers, timeout)
                return self._parse_response(response)
            except httpx.TimeoutException as e:
                last_error = f"timeout after {timeout}s: {e}"
                logger.warning(
                    "Worker timeout (attempt %d/%d) agent=%s node=%s: %s",
                    attempt + 1,
                    self._max_retries,
                    agent_id,
                    node_id,
                    e,
                )
            except httpx.ConnectError as e:
                last_error = f"connection error: {e}"
                logger.warning(
                    "Worker connection error (attempt %d/%d) agent=%s node=%s: %s",
                    attempt + 1,
                    self._max_retries,
                    agent_id,
                    node_id,
                    e,
                )
            except httpx.HTTPStatusError as e:
                # 4xx/5xx that httpx raises with raise_for_status
                if e.response.status_code < 500:
                    worker_down = False  # worker alcançável; erro de configuração
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
                logger.warning(
                    "Worker HTTP error (attempt %d/%d) agent=%s node=%s: %s",
                    attempt + 1,
                    self._max_retries,
                    agent_id,
                    node_id,
                    last_error,
                )
            except Exception as e:
                # Catch-all: ADR-001 says never propagate.
                last_error = f"unexpected error: {type(e).__name__}: {e}"
                logger.error(
                    "Worker unexpected error (attempt %d/%d) agent=%s node=%s: %s",
                    attempt + 1,
                    self._max_retries,
                    agent_id,
                    node_id,
                    e,
                    exc_info=True,
                )
                # Non-retryable: break immediately for unexpected errors.
                worker_down = False
                break

            # Backoff before next attempt (not after last).
            if attempt < self._max_retries - 1:
                delay = self._backoff_base * (2**attempt)
                logger.info(
                    "Retrying worker call in %.1fs (attempt %d/%d) agent=%s node=%s",
                    delay,
                    attempt + 1,
                    self._max_retries,
                    agent_id,
                    node_id,
                )
                await asyncio.sleep(delay)

        # All retries exhausted or non-retryable error.
        logger.error(
            "Worker execution failed after %d attempts agent=%s node=%s: %s",
            self._max_retries,
            agent_id,
            node_id,
            last_error,
        )
        return WorkerResponse(
            status="failed",
            outputs={},
            action="follow",
            iterations=0,
            logs=[f"worker execution failed: {last_error}"],
            error=last_error,
            worker_down=worker_down,
        )

    async def _post(
        self,
        body: dict[str, Any],
        headers: dict[str, str],
        timeout: int,
    ) -> httpx.Response:
        """Perform the HTTP POST with per-request timeout."""
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                self._worker_url,
                json=body,
                headers=headers,
            )
            # Raise for 4xx/5xx so the retry loop handles them.
            response.raise_for_status()
            return response

    def _parse_response(self, response: httpx.Response) -> WorkerResponse:
        """Parse a successful (200) HTTP response into a WorkerResponse."""
        data = response.json()
        return WorkerResponse(
            status=data.get("status", "failed"),
            outputs=data.get("outputs", {}),
            action=data.get("action", "follow"),
            iterations=data.get("iterations", 1),
            logs=data.get("logs", []),
            error=data.get("error"),
        )
