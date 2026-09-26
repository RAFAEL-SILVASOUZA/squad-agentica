"""Cenario 8 - Resiliencia: derrubar uma replica do worker durante a execucao
(``docker stop`` numa replica) e o run concluir ou pausar retomavel.

Fontes: contrato §2.3 (retry 3x, backoff 2/4/8s; pool de workers no NGINX
:8081), spec 5.1, ADR-001/004.

As replicas sao religadas no teardown, mesmo em falha.
"""

from __future__ import annotations

import pytest

from conftest import COMPOSE_PROJECT, compose, create_agent, docker, seed_pipeline, wait_until

T = 120


def replicas() -> list[str]:
    out = compose("ps", "-a", "--format", "{{.Name}}", "agent-worker").stdout.split()
    return sorted(n for n in out if n.startswith(f"{COMPOSE_PROJECT}-agent-worker"))


@pytest.fixture
def restore_workers():
    yield
    compose("start", "agent-worker", timeout=180)
    wait_until(lambda: compose("ps", "agent-worker").stdout.count("healthy") >= 2, timeout=120, desc="workers healthy")


def _final(ws, pid):
    return [e for e in ws.of("pipeline:status", pid) if e["status"] in ("completed", "failed", "paused")]


def test_one_replica_down_run_still_finishes(user, ws_factory, restore_workers):
    names = replicas()
    assert len(names) >= 2, f"esperadas 2 replicas do worker, ha {names}"
    p = seed_pipeline(user.id, [create_agent(user, "qa-r1"), create_agent(user, "qa-r2")])
    ws = ws_factory(user.access)

    assert user.post(f"/api/pipelines/{p.id}/execute").status_code == 200
    r = docker("stop", "-t", "1", names[0])  # derruba uma replica com o run em andamento
    assert r.returncode == 0, r.stderr

    final = wait_until(lambda: _final(ws, p.id), timeout=T, desc="fim/pausa do run com 1 replica")
    status = final[-1]["status"]
    assert status in ("completed", "paused"), f"run terminou como {status} com uma replica de pe"

    # Um segundo run inteiro so com a replica restante.
    p2 = seed_pipeline(user.id, [create_agent(user, "qa-r3"), create_agent(user, "qa-r4")])
    assert user.post(f"/api/pipelines/{p2.id}/execute").status_code == 200
    final2 = wait_until(lambda: _final(ws, p2.id), timeout=T, desc="run com 1 replica")
    assert final2[-1]["status"] == "completed", final2[-1]


def test_all_replicas_down_run_pauses_and_resumes(user, ws_factory, restore_workers):
    """Sem nenhum worker o run nao pode 'falhar' definitivamente: pausa e retoma."""
    p = seed_pipeline(user.id, [create_agent(user, "qa-r5"), create_agent(user, "qa-r6")])
    ws = ws_factory(user.access)
    assert compose("stop", "agent-worker", timeout=180).returncode == 0
    assert user.post(f"/api/pipelines/{p.id}/execute").status_code == 200
    final = wait_until(lambda: _final(ws, p.id), timeout=T, desc="status do run sem workers")
    assert final[-1]["status"] == "paused", f"sem workers o run ficou {final[-1]['status']} (esperado paused retomavel)"

    compose("start", "agent-worker", timeout=180)
    wait_until(lambda: compose("ps", "agent-worker").stdout.count("healthy") >= 2, timeout=120, desc="workers healthy")
    r = user.post(f"/api/pipelines/{p.id}/resume")
    assert r.status_code == 200, r.text
    done = wait_until(lambda: [e for e in ws.of("pipeline:status", p.id) if e["status"] == "completed"], timeout=T,
                      desc="completed apos resume")
    assert done
