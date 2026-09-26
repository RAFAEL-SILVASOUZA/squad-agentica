"""Cenario 5 - HITL: pipeline com aprovacao, ``approval:new``, aprovar,
rejeitar com loop back, argumentar, dupla resposta 409.

Fontes: spec 5.3/9.6/9.7, contrato §7/§8, ADR-006/009.
Pipeline semeada (B1): no1 --(requiresApproval, rejectTarget=no1)--> no2.
"""

from __future__ import annotations

import uuid

import pytest

from conftest import assert_envelope, create_agent, seed_pipeline, wait_until

T = 30


@pytest.fixture
def hitl(user, ws_factory):
    a1, a2 = create_agent(user, "qa-h1"), create_agent(user, "qa-h2")
    p = seed_pipeline(user.id, [a1, a2], approval_on=0, reject_to_source=True)
    ws = ws_factory(user.access)
    r = user.post(f"/api/pipelines/{p.id}/execute")
    assert r.status_code == 200, r.text
    return p, ws, r.json()["runId"]


def pending(user, pid):
    r = user.get("/api/approvals", params={"status": "pending", "pipelineId": pid})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def test_approval_new_event_and_pending_request(user, hitl):
    p, ws, run_id = hitl
    ev = wait_until(lambda: ws.of("approval:new", p.id), timeout=T, desc="approval:new")[0]
    assert set(ev) >= {"approvalId", "pipelineId", "runId", "nodeId", "message", "at"}
    assert ev["message"] == "QA: aprovar a passagem?"
    waiting = [e for e in ws.of("pipeline:status", p.id) if e["status"] == "waiting_approval"]
    assert waiting, ws.frames

    items = wait_until(lambda: pending(user, p.id), timeout=T, desc="ApprovalRequest pendente em GET /api/approvals")
    assert len(items) == 1
    ap = items[0]
    assert ap["id"] == ev["approvalId"], f"approvalId do WS ({ev['approvalId']}) != id da API ({ap['id']})"
    assert ap["runId"] == run_id == ev["runId"]
    assert user.get(f"/api/approvals/{ap['id']}").status_code == 200


def test_approve_resumes_and_double_response_409(user, hitl):
    p, ws, _ = hitl
    ap = wait_until(lambda: pending(user, p.id), timeout=T, desc="aprovacao pendente")[0]
    r = user.post(f"/api/approvals/{ap['id']}/respond", json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    res = wait_until(lambda: ws.of("approval:resolved", p.id), timeout=T, desc="approval:resolved")
    assert res[0]["approvalId"] == ap["id"] and res[0]["decision"] == "approved"

    r2 = user.post(f"/api/approvals/{ap['id']}/respond", json={"decision": "rejected"})
    assert_envelope(r2, 409, "already_responded")

    # Retomada: o no 2 roda e o run termina.
    final = wait_until(lambda: [e for e in ws.of("pipeline:status", p.id) if e["status"] in ("completed", "failed")],
                       timeout=T, desc="fim do run apos aprovar")
    assert final[-1]["status"] == "completed", final


def test_reject_loops_back_to_source(user, hitl):
    p, ws, _ = hitl
    ap = wait_until(lambda: pending(user, p.id), timeout=T, desc="aprovacao pendente")[0]
    r = user.post(f"/api/approvals/{ap['id']}/respond", json={"decision": "rejected", "response": "refaca"})
    assert r.status_code == 200, r.text
    # Loop back: o no 1 roda de novo e pede nova aprovacao.
    second = wait_until(lambda: [a for a in pending(user, p.id) if a["id"] != ap["id"]], timeout=T,
                        desc="nova aprovacao apos rejeitar (loop back)")
    assert second[0]["nodeId"] == ap["nodeId"]


def test_revise_argument_is_stored(user, hitl):
    p, ws, _ = hitl
    ap = wait_until(lambda: pending(user, p.id), timeout=T, desc="aprovacao pendente")[0]
    r = user.post(f"/api/approvals/{ap['id']}/respond", json={"decision": "revised", "response": "inclua testes"})
    assert r.status_code == 200, r.text
    got = user.get(f"/api/approvals/{ap['id']}").json()
    assert got["status"] == "revised" and got["response"] == "inclua testes" and got["respondedAt"]


def test_invalid_decision_and_unknown_approval(user):
    assert_envelope(user.post(f"/api/approvals/{uuid.uuid4()}/respond", json={"decision": "approved"}), 404)
    r = user.post(f"/api/approvals/{uuid.uuid4()}/respond", json={"decision": "talvez"})
    assert_envelope(r, 400, "invalid_decision")


def test_approvals_list_shape(user):
    r = user.get("/api/approvals", params={"status": "pending"})
    assert r.status_code == 200
    assert set(r.json()) >= {"items", "total", "page", "limit"}
