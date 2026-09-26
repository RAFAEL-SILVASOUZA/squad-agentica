"""Cenario 6 - Ciclo de vida: pause, resume, stop, 409 de execucao
concorrente, 409 de edicao durante execucao.

Fontes: spec 5.1 (Pause e Resume), 9.1, 14.1 (Concorrencia), contrato §8.

Para ter um run realmente "running" por varios segundos com LLM mock (que
responde na hora), a fixture ``slow_run`` para as duas replicas do worker: o
worker_client do orchestrator fica em retry (backoff 2s/4s/8s, contrato §2.3)
e o no fica em execucao por ~14s. As replicas sao religadas no teardown.
"""

from __future__ import annotations

import time

import pytest

from conftest import assert_envelope, compose, create_agent, db_query, seed_pipeline, wait_until


def _workers(action: str) -> None:
    r = compose(action, "agent-worker", timeout=180)
    assert r.returncode == 0, r.stderr


@pytest.fixture
def slow_run(user, ws_factory):
    a1, a2 = create_agent(user, "qa-l1"), create_agent(user, "qa-l2")
    p = seed_pipeline(user.id, [a1, a2])
    ws = ws_factory(user.access)
    _workers("stop")
    try:
        r = user.post(f"/api/pipelines/{p.id}/execute")
        assert r.status_code == 200, r.text
        yield p, ws, r.json()["runId"]
    finally:
        _workers("start")
        wait_until(lambda: "healthy" in compose("ps", "agent-worker").stdout, timeout=90, desc="workers healthy")


def run_statuses(pid):
    return [r[0] for r in db_query("SELECT status FROM pipeline_runs WHERE pipeline_id = %s ORDER BY started_at", (pid,))]


def test_concurrent_execute_409_without_orphan_run(user, slow_run):
    p, _, run_id = slow_run
    r = user.post(f"/api/pipelines/{p.id}/execute")
    body = assert_envelope(r, 409, "pipeline_already_running")
    assert body.get("details", {}).get("runId") == run_id, body
    assert len(run_statuses(p.id)) == 1, f"409 deixou run orfao: {run_statuses(p.id)}"


def test_edit_during_run_409(user, slow_run):
    p, _, _ = slow_run
    r = user.put(f"/api/pipelines/{p.id}", json={"description": "editando durante o run"})
    assert_envelope(r, 409, "graph_running")


def test_pause_then_resume(user, slow_run):
    p, ws, run_id = slow_run
    time.sleep(1)
    r = user.post(f"/api/pipelines/{p.id}/pause")
    assert r.status_code == 200, r.text
    assert r.json() == {"runId": run_id, "status": "paused"}, r.json()
    assert run_statuses(p.id) == ["paused"]
    assert db_query("SELECT status FROM pipelines WHERE id = %s", (p.id,))[0][0] == "paused"
    wait_until(lambda: [e for e in ws.of("pipeline:status", p.id) if e["status"] == "paused"], timeout=10,
               desc="pipeline:status paused")

    r = user.post(f"/api/pipelines/{p.id}/resume")
    assert r.status_code == 200, r.text
    assert r.json()["runId"] == run_id and r.json()["status"] == "running"
    assert run_statuses(p.id) == ["running"]


def test_resume_without_paused_run_404(user):
    a1, a2 = create_agent(user, "qa-l3"), create_agent(user, "qa-l4")
    p = seed_pipeline(user.id, [a1, a2])
    assert_envelope(user.post(f"/api/pipelines/{p.id}/resume"), 404)
    assert_envelope(user.post(f"/api/pipelines/{p.id}/pause"), 404)
    assert_envelope(user.post(f"/api/pipelines/{p.id}/stop"), 404)


def test_stop_cancels_run(user, slow_run):
    p, ws, run_id = slow_run
    r = user.post(f"/api/pipelines/{p.id}/stop")
    assert r.status_code == 200 and r.json() == {"runId": run_id, "status": "cancelled"}, r.text
    assert run_statuses(p.id) == ["cancelled"]
    # Depois do stop a pipeline aceita um novo execute (nao fica presa em 409).
    r = user.post(f"/api/pipelines/{p.id}/execute")
    assert r.status_code == 200, r.text


def test_stop_cancels_pending_approvals(user, ws_factory):
    a1, a2 = create_agent(user, "qa-l5"), create_agent(user, "qa-l6")
    p = seed_pipeline(user.id, [a1, a2], approval_on=0)
    ws = ws_factory(user.access)
    assert user.post(f"/api/pipelines/{p.id}/execute").status_code == 200
    wait_until(lambda: ws.of("approval:new", p.id), timeout=30, desc="approval:new")
    wait_until(lambda: user.get("/api/approvals", params={"status": "pending", "pipelineId": p.id}).json()["items"],
               timeout=15, desc="aprovacao pendente")
    r = user.post(f"/api/pipelines/{p.id}/stop")
    assert r.status_code == 200, r.text
    items = user.get("/api/approvals", params={"status": "cancelled", "pipelineId": p.id}).json()["items"]
    assert len(items) == 1
