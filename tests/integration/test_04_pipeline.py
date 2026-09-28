"""Cenario 4 - Pipeline: criar com dois agentes, validar (erros estruturados
para um grafo invalido), executar, acompanhar pelo WebSocket, checkpoints,
artefatos e resultado final.

Fontes: spec 4.2/5.1/9.1/9.7, contrato §7/§8, GUIA-API-FRONTEND "Pipelines".
CRUD/validate: PENDENCIAS B1 (endpoints ausentes). Execucao usa pipeline
semeada no banco (conftest.seed_pipeline).
"""

from __future__ import annotations

import uuid

import pytest

from conftest import assert_envelope, create_agent, db_query, seed_pipeline, snapshot_of, wait_until

RUN_TIMEOUT = 30


def graph_payload(a1, a2, *, cyclic=False, bad_entry=False):
    n1, n2 = str(uuid.uuid4()), str(uuid.uuid4())
    edges = [
        {"id": str(uuid.uuid4()), "type": "flow", "source": n1, "target": n2},
        {"id": str(uuid.uuid4()), "type": "data", "source": n1, "target": n2,
         "dataMapping": {"sourceOutput": "result", "targetInput": "spec"}},
    ]
    if cyclic:
        edges.append({"id": str(uuid.uuid4()), "type": "flow", "source": n2, "target": n1})
    return {
        "name": f"qa-pipe-{uuid.uuid4().hex[:6]}",
        "description": "qa",
        "entryNodeId": str(uuid.uuid4()) if bad_entry else n1,
        "nodes": [
            {"id": n1, "agentId": a1["id"], "agentSnapshot": snapshot_of(a1), "position": {"x": 0, "y": 0}},
            {"id": n2, "agentId": a2["id"], "agentSnapshot": snapshot_of(a2), "position": {"x": 200, "y": 0}},
        ],
        "edges": edges,
    }


# ---------------------------------------------------------------------------
# CRUD + validate (B1)
# ---------------------------------------------------------------------------


def test_pipeline_crud_two_agents(user):
    a1, a2 = create_agent(user, "qa-p1"), create_agent(user, "qa-p2")
    r = user.post("/api/pipelines", json=graph_payload(a1, a2))
    assert r.status_code == 201, f"B1: POST /api/pipelines -> {r.status_code} {r.text[:200]}"
    pid = r.json()["id"]
    assert user.get(f"/api/pipelines/{pid}").status_code == 200
    lst = user.get("/api/pipelines").json()
    assert set(lst) == {"items", "total", "page", "limit"}
    r = user.put(f"/api/pipelines/{pid}", json={"description": "editada"})
    assert r.status_code == 200, r.text


def _create_git_integration(user, name: str) -> dict:
    r = user.post("/api/integrations", json={"type": "github", "name": name, "config": {}})
    assert r.status_code == 201, r.text
    return r.json()


def test_pipeline_repository_roundtrip(user):
    """Task 4: repository no create/get/put (set e null limpa)."""
    a1, a2 = create_agent(user, "qa-repo1"), create_agent(user, "qa-repo2")
    integ = _create_git_integration(user, f"qa-git-{uuid.uuid4().hex[:6]}")
    graph = graph_payload(a1, a2)
    graph["repository"] = {"integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main"}
    created = user.post("/api/pipelines", json=graph)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["repository"] == {
        "integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main",
    }
    assert user.get(f"/api/pipelines/{pid}").json()["repository"] == created.json()["repository"]

    cleared = user.put(f"/api/pipelines/{pid}", json={"repository": None})
    assert cleared.status_code == 200 and cleared.json()["repository"] is None, cleared.text

    kept = user.put(f"/api/pipelines/{pid}", json={"description": "sem repo"})
    assert kept.json()["repository"] is None


def test_pipeline_repository_invalid_integration_rejected(user):
    a1, a2 = create_agent(user, "qa-repo3"), create_agent(user, "qa-repo4")
    graph = graph_payload(a1, a2)
    graph["repository"] = {"integrationId": str(uuid.uuid4()), "fullName": "o/r", "baseBranch": "main"}
    r = user.post("/api/pipelines", json=graph)
    assert_envelope(r, 400, "invalid_repository")


def test_pipeline_duplicate_and_delete(user):
    a1, a2 = create_agent(user, "qa-dup1"), create_agent(user, "qa-dup2")
    graph = graph_payload(a1, a2)
    graph["name"] = f"qa-dup-{uuid.uuid4().hex[:6]}"
    created = user.post("/api/pipelines", json=graph)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    dup = user.post(f"/api/pipelines/{pid}/duplicate")
    assert dup.status_code == 201, dup.text
    dup_body = dup.json()
    assert dup_body["name"] == f"{graph['name']} (cópia)"
    assert dup_body["id"] != pid
    original_ids = {n["id"] for n in created.json()["nodes"]}
    dup_ids = {n["id"] for n in dup_body["nodes"]}
    assert original_ids.isdisjoint(dup_ids)
    assert user.get(f"/api/pipelines/{dup_body['id']}/runs").json()["total"] == 0

    assert user.delete(f"/api/pipelines/{pid}").status_code == 204
    assert user.get(f"/api/pipelines/{pid}").status_code == 404
    assert user.delete(f"/api/pipelines/{dup_body['id']}").status_code == 204


def test_pipeline_delete_conflicts_with_active_run(user, two_agent_pipeline, ws_factory):
    """DELETE com run ativo -> 409 graph_running; apos concluir, delete funciona."""
    p = two_agent_pipeline
    ws = ws_factory(user.access)
    assert user.post(f"/api/pipelines/{p.id}/execute").status_code == 200
    r = user.delete(f"/api/pipelines/{p.id}")
    assert_envelope(r, 409, "graph_running")

    wait_until(
        lambda: [e for e in ws.of("pipeline:status", p.id) if e["status"] in ("completed", "failed")],
        timeout=RUN_TIMEOUT, desc="status final no WS antes do delete",
    )
    assert user.delete(f"/api/pipelines/{p.id}").status_code == 204


def test_pipeline_validate_invalid_graph_structured_errors(user):
    a1, a2 = create_agent(user, "qa-v1"), create_agent(user, "qa-v2")
    r = user.post("/api/pipelines/validate", json=graph_payload(a1, a2, bad_entry=True))
    body = assert_envelope(r, 400, "invalid_graph")
    errors = body["details"]["errors"]
    assert errors and all(isinstance(e["rule"], int) and e["message"] for e in errors), errors


def test_pipeline_graph_update_preserves_ids_and_approval_channel(user):
    a1, a2 = create_agent(user, "qa-save1"), create_agent(user, "qa-save2")
    graph = graph_payload(a1, a2)
    created = user.post("/api/pipelines", json=graph)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    graph["edges"][0].update(requiresApproval=True, approvalChannel="in-app", approvalMessage="Revisar")
    for _ in range(2):
        saved = user.put(f"/api/pipelines/{pid}", json=graph)
        assert saved.status_code == 200, saved.text
    stored = user.get(f"/api/pipelines/{pid}").json()
    assert {n["id"] for n in stored["nodes"]} == {n["id"] for n in graph["nodes"]}
    assert len(stored["edges"]) == 2
    approval = next(e for e in stored["edges"] if e["type"] == "flow")
    assert approval["requiresApproval"] is True
    assert approval["approvalChannel"] == "in-app"


def test_editor_local_node_ids_are_translated_in_edges(user):
    """O editor cria nós com id local (node-<ts>-<rand>); as arestas que os citam
    devem seguir o UUID atribuído, não virar 422."""
    a1, a2 = create_agent(user, "qa-local1"), create_agent(user, "qa-local2")
    graph = graph_payload(a1, a2)
    created = user.post("/api/pipelines", json=graph)
    assert created.status_code == 201, created.text
    local_id = "node-1790000000000-abc123"
    old_id = graph["nodes"][1]["id"]
    graph["nodes"][1]["id"] = local_id
    for e in graph["edges"]:
        e["source"] = local_id if e["source"] == old_id else e["source"]
        e["target"] = local_id if e["target"] == old_id else e["target"]
    saved = user.put(f"/api/pipelines/{created.json()['id']}", json=graph)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    new_id = next(n["id"] for n in body["nodes"] if n["id"] != graph["nodes"][0]["id"])
    assert new_id != local_id
    assert all(e["target"] == new_id for e in body["edges"])


def test_empty_pipeline_accepts_first_graph(user):
    created = user.post("/api/pipelines", json={"name": "qa-empty", "nodes": [], "edges": []})
    assert created.status_code == 201, created.text
    empty = created.json()
    graph = graph_payload(create_agent(user, "qa-first1"), create_agent(user, "qa-first2"))
    graph["entryNodeId"] = empty["entryNodeId"]
    saved = user.put(f"/api/pipelines/{empty['id']}", json=graph)
    assert saved.status_code == 200, saved.text
    assert saved.json()["entryNodeId"] == graph["nodes"][0]["id"]


def test_pipeline_validate_valid_graph_ok(user):
    a1, a2 = create_agent(user, "qa-v3"), create_agent(user, "qa-v4")
    r = user.post("/api/pipelines/validate", json=graph_payload(a1, a2))
    assert r.status_code == 200, f"B1: {r.status_code} {r.text[:200]}"


# ---------------------------------------------------------------------------
# Execucao (pipeline semeada)
# ---------------------------------------------------------------------------


@pytest.fixture
def two_agent_pipeline(user):
    a1, a2 = create_agent(user, "qa-exec-1"), create_agent(user, "qa-exec-2")
    return seed_pipeline(user.id, [a1, a2])


def _run_row(run_id):
    rows = db_query("SELECT status, completed_at FROM pipeline_runs WHERE id = %s", (run_id,))
    return rows[0] if rows else None


def test_execute_response_and_run_listing(user, two_agent_pipeline):
    p = two_agent_pipeline
    r = user.post(f"/api/pipelines/{p.id}/execute")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "running" and uuid.UUID(body["runId"])
    runs = user.get(f"/api/pipelines/{p.id}/runs").json()
    assert runs["total"] == 1 and runs["items"][0]["id"] == body["runId"]


def test_execute_ws_events_use_same_run_id(user, two_agent_pipeline, ws_factory):
    """Os eventos do WebSocket devem carregar o runId devolvido pelo execute."""
    p = two_agent_pipeline
    ws = ws_factory(user.access)
    run_id = user.post(f"/api/pipelines/{p.id}/execute").json()["runId"]
    wait_until(lambda: ws.of("pipeline:status", p.id), timeout=RUN_TIMEOUT, desc="pipeline:status")
    run_ids = {e["runId"] for e in ws.of("pipeline:status", p.id)}
    assert run_ids == {run_id}, f"runId do execute={run_id}, runIds no WS={run_ids}"


def test_execute_completes_with_node_events_and_final_status(user, two_agent_pipeline, ws_factory):
    p = two_agent_pipeline
    ws = ws_factory(user.access)
    r = user.post(f"/api/pipelines/{p.id}/execute")
    assert r.status_code == 200, r.text
    final = wait_until(
        lambda: [e for e in ws.of("pipeline:status", p.id) if e["status"] in ("completed", "failed")],
        timeout=RUN_TIMEOUT, desc="status final no WS",
    )
    assert final[-1]["status"] == "completed", f"run terminou {final[-1]}; logs WS: {ws.of('pipeline:log', p.id)[:3]}"
    # Status por no (contrato §7: nodeId em pipeline:status) e output de cada agente.
    node_events = {e["nodeId"] for e in ws.of("pipeline:status", p.id) if e["nodeId"]}
    assert set(p.nodes) <= node_events, f"eventos por no ausentes: {node_events}"
    outputs = {e["nodeId"] for e in ws.of("agent:output", p.id)}
    assert set(p.nodes) <= outputs, f"agent:output ausente: {outputs}"
    for f in ws.frames:
        assert set(f) == {"channel", "data"}, f


def test_run_persisted_as_completed(user, two_agent_pipeline):
    p = two_agent_pipeline
    run_id = user.post(f"/api/pipelines/{p.id}/execute").json()["runId"]
    row = wait_until(lambda: (r := _run_row(run_id)) and r[0] != "running" and r, timeout=RUN_TIMEOUT,
                     desc="pipeline_runs.status != running")
    assert row[0] == "completed" and row[1] is not None, row
    item = user.get(f"/api/pipelines/{p.id}/runs").json()["items"][0]
    assert item["status"] == "completed" and item["completedAt"].endswith("Z"), item
    # Task 4: campos de publicação de PR (sem repositório configurado -> "none"/null).
    assert item["publishStatus"] == "none"
    assert item["prUrl"] is None and item["prNumber"] is None and item["publishError"] is None


def test_checkpoints_listed_after_run(user, two_agent_pipeline):
    p = two_agent_pipeline
    run_id = user.post(f"/api/pipelines/{p.id}/execute").json()["runId"]
    cps = wait_until(lambda: user.get(f"/api/pipelines/{p.id}/checkpoints").json()["items"], timeout=RUN_TIMEOUT,
                     desc="checkpoints")
    assert {c["nodeId"] for c in cps} & set(p.nodes), cps
    cp = cps[-1]
    r = user.post(f"/api/pipelines/{p.id}/checkpoints/{cp['id']}/resume")
    assert r.status_code == 200 and r.json()["runId"] != run_id, r.text


def test_artifacts_endpoint_available(user, two_agent_pipeline):
    """Spec 9.1: GET /api/artifacts/:id devolve o Artifact com content."""
    p = two_agent_pipeline
    run_id = user.post(f"/api/pipelines/{p.id}/execute").json()["runId"]
    rows = wait_until(lambda: db_query("SELECT id FROM artifacts WHERE run_id = %s", (run_id,)), timeout=RUN_TIMEOUT,
                      desc="artefatos do run")
    r = user.get(f"/api/artifacts/{rows[0][0]}")
    assert r.status_code == 200 and "content" in r.json(), r.text


def test_final_result_has_agent_outputs(user, two_agent_pipeline, ws_factory):
    """Resultado final: o no 2 recebeu o output do no 1 (data edge result -> spec)."""
    p = two_agent_pipeline
    ws = ws_factory(user.access)
    user.post(f"/api/pipelines/{p.id}/execute")
    outs = wait_until(lambda: [e for e in ws.of("agent:output", p.id) if e["nodeId"] == p.nodes[1]],
                      timeout=RUN_TIMEOUT, desc="agent:output do no 2")
    assert outs[-1]["output"], outs


def test_execute_unknown_pipeline_404(user):
    assert_envelope(user.post(f"/api/pipelines/{uuid.uuid4()}/execute"), 404, "pipeline_not_found")
