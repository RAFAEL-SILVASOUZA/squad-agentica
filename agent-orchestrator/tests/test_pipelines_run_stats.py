"""Task 12: runStats e filtros (run/since) em GET /api/pipelines.

Cobertura:
- runStats calculado sobre os últimos 10 runs (janela);
- run=never devolve só pipelines sem runs;
- since=24h exclui pipeline cujo último run tem 2 dias.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Pipeline, PipelineRun


@pytest_asyncio.fixture
async def make_pipeline(session: AsyncSession, test_user):
    """Cria uma pipeline do usuário de teste."""

    async def _make(name: str = "Pipeline"):
        p = Pipeline(
            id=uuid.uuid4(),
            owner_id=test_user.owner_id,
            name=name,
            description="",
            status="draft",
            entry_node_id=uuid.uuid4(),
        )
        session.add(p)
        await session.commit()
        await session.refresh(p)
        return p

    return _make


def _add_run(session, pipeline_id, status, started_at):
    run = PipelineRun(
        id=uuid.uuid4(),
        owner_id=None,  # preenchido abaixo
        pipeline_id=pipeline_id,
        thread_id=f"{pipeline_id}:{uuid.uuid4().hex[:8]}",
        status=status,
        started_at=started_at,
        completed_at=started_at + timedelta(minutes=1) if status != "running" else None,
    )
    session.add(run)
    return run


async def test_run_stats_window_of_last_10(full_client, session, test_user, make_pipeline):
    """12 runs (8 completed, 3 failed, 1 running) → conta só os 10 mais recentes."""
    p = await make_pipeline("Com runs")
    now = datetime.now(UTC)

    # 12 runs: o mais recente é "running", depois 7 completed e 3 failed
    # intercalados de forma que, dos 10 mais recentes, fiquem 7 completed e 2 failed.
    # Ordem por started_at (mais recente primeiro):
    #   1 running, 2 completed, 3 failed, 4 completed, 5 completed,
    #   6 failed, 7 completed, 8 completed, 9 completed, 10 failed,
    #   11 completed (fora da janela), 12 completed (fora da janela)
    statuses = [
        "running",
        "completed",
        "failed",
        "completed",
        "completed",
        "failed",
        "completed",
        "completed",
        "completed",
        "failed",
        "completed",
        "completed",
    ]
    for i, st in enumerate(statuses):
        started = now - timedelta(minutes=i)
        run = _add_run(session, p.id, st, started)
        run.owner_id = test_user.owner_id
    await session.commit()

    resp = await full_client.get("/api/pipelines")
    assert resp.status_code == 200
    items = resp.json()["items"]
    item = next(i for i in items if i["id"] == str(p.id))

    stats = item["runStats"]
    # Dos 10 mais recentes: completed = índices 1,3,4,6,7,8 = 6; failed = 2,5,9 = 3.
    # (o running não conta como succeeded nem failed)
    assert stats["recentSucceeded"] == 6
    assert stats["recentFailed"] == 3
    assert stats["lastRunStatus"] == "running"
    assert stats["lastRunAt"] is not None


async def test_run_never_filter(full_client, session, test_user, make_pipeline):
    """run=never devolve só pipelines sem runs."""
    with_runs = await make_pipeline("Com runs")
    without_runs = await make_pipeline("Sem runs")
    now = datetime.now(UTC)
    run = _add_run(session, with_runs.id, "completed", now)
    run.owner_id = test_user.owner_id
    await session.commit()

    resp = await full_client.get("/api/pipelines", params={"run": "never"})
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    assert str(without_runs.id) in ids
    assert str(with_runs.id) not in ids


async def test_since_24h_filter(full_client, session, test_user, make_pipeline):
    """since=24h exclui pipeline cujo último run tem 2 dias."""
    recent = await make_pipeline("Recente")
    old = await make_pipeline("Antiga")
    now = datetime.now(UTC)

    r1 = _add_run(session, recent.id, "completed", now - timedelta(hours=1))
    r1.owner_id = test_user.owner_id
    r2 = _add_run(session, old.id, "completed", now - timedelta(days=2))
    r2.owner_id = test_user.owner_id
    await session.commit()

    resp = await full_client.get("/api/pipelines", params={"since": "24h"})
    assert resp.status_code == 200
    ids = [i["id"] for i in resp.json()["items"]]
    assert str(recent.id) in ids
    assert str(old.id) not in ids
