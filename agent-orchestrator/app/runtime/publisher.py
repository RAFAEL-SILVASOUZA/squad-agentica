"""Publica o workspace de um run: commit, push e Pull Request."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Checkpoint, Integration, Pipeline, PipelineNode, PipelineRun
from app.db.session import async_session_factory
from app.integrations.git_providers import GitProviderError, provider_for
from app.runtime.websocket import publish as ws_publish
from app.runtime.workspace import (
    EXPIRED_MESSAGE,
    WorkspaceError,
    WorkspaceManager,
    slugify_branch,
)

logger = logging.getLogger(__name__)

# Um lock por run: publicação automática (fim do run) e manual (POST
# /runs/:id/publish) serializam, senão as duas podiam abrir PRs duplicados.
# Contagem de usuários para remover a entrada quando ninguém mais espera.
_run_locks: dict[str, tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def _run_lock(run_id: str) -> AsyncIterator[None]:
    lock, users = _run_locks.get(run_id, (asyncio.Lock(), 0))
    _run_locks[run_id] = (lock, users + 1)
    try:
        async with lock:
            yield
    finally:
        lock, users = _run_locks[run_id]
        if users <= 1:
            _run_locks.pop(run_id, None)
        else:
            _run_locks[run_id] = (lock, users - 1)

# Limites do corpo do PR: cada valor é truncado e o corpo inteiro fica abaixo
# do limite do GitHub (65536 caracteres).
_MAX_INPUT_CHARS = 1000
_MAX_OUTPUT_CHARS = 3000
_MAX_BODY_CHARS = 60_000


def build_pr_body(inputs: dict[str, Any], outputs: dict[str, dict[str, Any]], run_url: str) -> str:
    lines = ["Gerado pelo **Agent Portal**.", "", f"Run: {run_url}", "", "## Entrada"]
    lines += [f"- **{k}**: {str(v)[:_MAX_INPUT_CHARS]}" for k, v in inputs.items()] or [
        "- (sem entradas)"
    ]
    for agent, out in outputs.items():
        lines += ["", f"## {agent}"]
        for port, value in out.items():
            if not str(port).startswith("_"):
                lines += [f"### {port}", str(value)[:_MAX_OUTPUT_CHARS]]
    body = "\n".join(lines)
    if len(body) > _MAX_BODY_CHARS:
        body = body[: _MAX_BODY_CHARS - 20] + "\n\n_(truncado)_"
    return body


async def publish_workspace(ws: WorkspaceManager, provider: Any, *, run_id: str, repo: str,
                            base: str, pipeline_name: str, title: str, body: str) -> dict[str, Any]:
    branch = slugify_branch(pipeline_name, run_id)
    try:
        existing = await provider.find_open_pull_request(repo, branch)
        if existing:
            return {"status": "published", "number": existing.number, "url": existing.url,
                    "branch": branch}
        pushed = await ws.commit_and_push(run_id, provider.clone_url(repo), branch, title)
        if pushed is None:
            return {"status": "no_changes"}
        pr = await provider.create_pull_request(repo, pushed, base, title, body)
        return {"status": "published", "number": pr.number, "url": pr.url, "branch": pushed}
    except (WorkspaceError, GitProviderError) as e:
        return {"status": "failed", "error": e.message}


def _pr_title(pipeline_name: str, inputs: dict[str, Any]) -> str:
    first = next((str(v) for v in inputs.values() if str(v).strip()), "")
    summary = " ".join(first.split())
    if len(summary) > 60:
        summary = summary[:59].rstrip() + "…"
    return f"{pipeline_name}: {summary}" if summary else pipeline_name


async def _run_inputs_and_outputs(
    db: AsyncSession, run: PipelineRun
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Entradas do disparo (``run_inputs`` do estado) e saídas por agente,
    lidas dos checkpoints concluídos do run (ordem cronológica)."""
    nodes = (await db.execute(
        select(PipelineNode).where(PipelineNode.pipeline_id == run.pipeline_id)
    )).scalars().all()
    names = {
        str(n.id): n.label or (n.agent_snapshot or {}).get("name") or str(n.id) for n in nodes
    }
    cps = (await db.execute(
        select(Checkpoint)
        .where(Checkpoint.run_id == run.id, Checkpoint.status == "completed")
        .order_by(Checkpoint.timestamp)
    )).scalars().all()
    inputs: dict[str, Any] = {}
    outputs: dict[str, dict[str, Any]] = {}
    for cp in cps:
        state = cp.state or {}
        inputs = state.get("run_inputs") or inputs
        out = (state.get("data") or {}).get(cp.node_id)
        if isinstance(out, dict):
            outputs[names.get(cp.node_id, cp.node_id)] = out
    return dict(inputs), outputs


async def _commit_or_gone(db: AsyncSession, run: PipelineRun) -> bool:
    """Grava o resultado da publicação. A pipeline (e, em cascata, o run)
    pode ter sido excluída enquanto o push/PR rodava: aí o UPDATE não acha a
    linha — desfaz e devolve False em vez de derrubar a requisição (500)."""
    run_id = str(run.id)  # antes do rollback, que expira os atributos
    try:
        await db.commit()
        await db.refresh(run)
        return True
    except Exception as e:  # noqa: BLE001 — StaleDataError/InvalidRequestError etc.
        await db.rollback()
        logger.warning("Run %s sumiu durante a publicação (%s)", run_id, type(e).__name__)
        return False


async def _publish(
    db: AsyncSession,
    run_id: str,
    manager: WorkspaceManager | None,
    provider_factory: Callable[[Any], Any],
) -> dict[str, Any]:
    from app.api.pipeline_runs import _run_to_dict  # import tardio: evita ciclo api<->runtime

    run = await db.get(PipelineRun, uuid.UUID(str(run_id)))
    if run is None:
        return {}
    pipeline = await db.get(Pipeline, run.pipeline_id)
    integration = None
    if pipeline is not None and pipeline.git_integration_id:
        integration = (await db.execute(
            select(Integration).where(
                Integration.id == pipeline.git_integration_id,
                Integration.owner_id == run.owner_id,
            )
        )).scalar_one_or_none()
    if (
        pipeline is None
        or not pipeline.git_integration_id
        or not pipeline.git_repository
        or not pipeline.git_base_branch
    ):
        # Sem repositório (ou a conexão Git foi removida: git_integration_id
        # NULL) não há o que publicar.
        run.publish_status = "none"
        if not await _commit_or_gone(db, run):
            return {}
        return _run_to_dict(run)

    ws = manager or WorkspaceManager()
    try:
        if integration is None:
            # Conexão Git que não é do dono do run: mesma mensagem do clone.
            raise GitProviderError("conexão Git da pipeline não encontrada")
        provider = provider_factory(integration)
        rid = str(run.id)
        if not ws.path(rid).is_dir() or not ws.has_repo(rid):
            # Revisão final I2: workspace (ou o repositório privado) purgado
            # pela retenção — nunca "sem alterações" silencioso.
            raise WorkspaceError(EXPIRED_MESSAGE)
        inputs, outputs = await _run_inputs_and_outputs(db, run)
        run_url = f"{settings.portal_base_url.rstrip('/')}/pipelines/{pipeline.id}/run"
        result = await publish_workspace(
            ws,
            provider,
            run_id=rid,
            repo=pipeline.git_repository,
            base=pipeline.git_base_branch,
            pipeline_name=pipeline.name,
            title=_pr_title(pipeline.name, inputs),
            body=build_pr_body(inputs, outputs, run_url),
        )
    except (WorkspaceError, GitProviderError) as e:
        result = {"status": "failed", "error": e.message}
    except Exception as e:  # noqa: BLE001 — a publicação nunca derruba o run
        # Só o tipo da exceção: a mensagem/traceback pode conter URL com token.
        logger.error("Falha inesperada ao publicar o run %s: %s", run.id, type(e).__name__)
        result = {"status": "failed", "error": f"erro inesperado ao publicar: {type(e).__name__}"}

    run.publish_status = result["status"]
    if result["status"] == "published":
        run.pr_url, run.pr_number, run.publish_error = result["url"], result["number"], None
    elif result["status"] == "failed":
        run.publish_error = str(result.get("error") or "falha ao publicar")[:2000]
        logger.warning("Publicação do run %s falhou: %s", run.id, run.publish_error)
    else:
        run.publish_error = None
    if not await _commit_or_gone(db, run):
        return {}

    # Status agregado (nodeId="") para o monitor recarregar o run com o PR.
    status = run.status.value if hasattr(run.status, "value") else run.status
    await ws_publish(str(run.owner_id), "pipeline:status", {
        "pipelineId": str(run.pipeline_id),
        "runId": str(run.id),
        "nodeId": "",
        "status": status,
        "at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    })
    return _run_to_dict(run)


async def publish_run(
    run_id: str,
    *,
    db: AsyncSession | None = None,
    manager: WorkspaceManager | None = None,
    provider_factory: Callable[[Any], Any] = provider_for,
) -> dict[str, Any]:
    """Publica o workspace do run (commit, push e PR) e grava o resultado no run.

    Atualiza ``publish_status`` (none|published|failed|no_changes), ``pr_url``,
    ``pr_number`` e ``publish_error``; nunca muda o ``status`` do run. Devolve
    o JSON do run (``{}`` se o run não existe).
    """
    async with _run_lock(str(run_id)):
        if db is not None:
            return await _publish(db, run_id, manager, provider_factory)
        async with async_session_factory() as session:
            return await _publish(session, run_id, manager, provider_factory)
