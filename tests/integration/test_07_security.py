"""Cenario 7 - Seguranca: isolamento entre dois usuarios em todos os recursos,
rate limits com 429 no envelope do contrato, segredos nunca retornados, worker
inacessivel pela porta 80.

Fontes: contrato §2.1/§2.3/§5/§7/§8, spec 14.1.
"""

from __future__ import annotations

import socket
import time
import uuid

import pytest
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

from conftest import (
    BASE_URL, WS_URL, assert_envelope, compose, create_agent, db_query, http, seed_pipeline, wait_until,
)

SECRET = "qa-super-secret-" + uuid.uuid4().hex[:8]


# ---------------------------------------------------------------------------
# Isolamento
# ---------------------------------------------------------------------------


@pytest.fixture
def a_resources(user):
    ag = create_agent(user, "qa-iso-agent")
    sk = user.post("/api/skills", json={"name": f"qa-iso-skill-{uuid.uuid4().hex[:4]}", "category": "docs",
                                       "definition": {"template": "t", "variables": []}}).json()
    tl = user.post("/api/tools", json={"name": f"qa-iso-tool-{uuid.uuid4().hex[:4]}",
                                      "script": "def execute():\n    return {}\n"}).json()
    mcp = user.post("/api/mcp-servers", json={"name": f"qa-iso-mcp-{uuid.uuid4().hex[:4]}", "transport": "http",
                                             "url": "http://example.invalid/mcp"}).json()
    kb = user.post("/api/knowledge", json={"name": f"qa-iso-kb-{uuid.uuid4().hex[:4]}", "scope": "global",
                                          "source": "upload"}).json()
    integ = user.post("/api/integrations", json={"type": "github", "name": f"qa-iso-gh-{uuid.uuid4().hex[:4]}", "config": {"owner": "qa"}}).json()
    p = seed_pipeline(user.id, [ag, create_agent(user, "qa-iso-agent-2")], approval_on=0)
    return {"agents": ag["id"], "skills": sk["id"], "tools": tl["id"], "mcp-servers": mcp["id"],
            "knowledge": kb["id"], "integrations": integ["id"], "pipeline": p}


@pytest.mark.parametrize("res", ["agents", "skills", "tools", "mcp-servers", "knowledge", "integrations"])
def test_crud_isolation(user, user_b, a_resources, res):
    rid = a_resources[res]
    assert_envelope(user_b.get(f"/api/{res}/{rid}"), 404)
    assert_envelope(user_b.put(f"/api/{res}/{rid}", json={"name": "hack"}), 404)
    assert_envelope(user_b.delete(f"/api/{res}/{rid}"), 404)
    items = user_b.get(f"/api/{res}").json()["items"]
    assert rid not in {str(i["id"]) for i in items}
    assert user.get(f"/api/{res}/{rid}").status_code == 200  # o dono continua vendo


def test_tool_and_mcp_actions_isolation(user_b, a_resources):
    assert_envelope(user_b.post(f"/api/tools/{a_resources['tools']}/deploy"), 404)
    assert_envelope(user_b.post(f"/api/tools/{a_resources['tools']}/test", json={"args": {}}), 404)
    assert_envelope(user_b.post(f"/api/mcp-servers/{a_resources['mcp-servers']}/test"), 404)
    r = user_b.post("/api/knowledge/query", json={"query": "x", "knowledgeBaseIds": [a_resources["knowledge"]]})
    assert r.status_code == 200 and r.json()["chunks"] == []


def test_pipeline_runtime_isolation(user, user_b, a_resources):
    """B nao pode listar, executar, pausar, parar nem ver checkpoints da pipeline de A."""
    pid = a_resources["pipeline"].id
    for method, path in (("GET", "runs"), ("GET", "checkpoints"), ("POST", "pause"), ("POST", "resume"), ("POST", "stop")):
        r = user_b.client.request(method, f"/api/pipelines/{pid}/{path}", headers=user_b.h)
        assert r.status_code == 404, f"B {method} {path}: {r.status_code} {r.text[:200]}"
    r = user_b.post(f"/api/pipelines/{pid}/execute")
    assert r.status_code == 404, f"B executou a pipeline de A: {r.status_code} {r.text[:200]}"
    assert not db_query("SELECT 1 FROM pipeline_runs WHERE pipeline_id = %s AND owner_id = %s", (pid, user_b.id))


def test_approvals_and_ws_isolation(user, user_b, a_resources, ws_factory):
    pid = a_resources["pipeline"].id
    ws_a, ws_b = ws_factory(user.access), ws_factory(user_b.access)
    assert user.post(f"/api/pipelines/{pid}/execute").status_code == 200
    wait_until(lambda: ws_a.of("pipeline:status", pid), timeout=30, desc="eventos no WS de A")
    time.sleep(1)
    assert ws_b.of("pipeline:status", pid) == [] and ws_b.of("approval:new", pid) == [], ws_b.frames
    assert user_b.get("/api/approvals").json()["total"] == 0
    for (aid,) in db_query("SELECT id FROM approval_requests WHERE pipeline_id = %s", (pid,)):
        assert_envelope(user_b.get(f"/api/approvals/{aid}"), 404)
        assert_envelope(user_b.post(f"/api/approvals/{aid}/respond", json={"decision": "approved"}), 404)
        assert_envelope(user_b.delete(f"/api/approvals/{aid}"), 404)


def test_ws_rejects_invalid_token_with_policy_violation():
    for url in (WS_URL, f"{WS_URL}?token=invalido"):
        try:
            with connect(url, open_timeout=10) as ws:
                ws.recv(timeout=5)
            pytest.fail(f"{url}: conexao aceita e mantida sem token valido")
        except ConnectionClosed as exc:
            assert exc.rcvd is not None and exc.rcvd.code == 1008, f"{url}: close code {exc.rcvd and exc.rcvd.code} (esperado 1008 policy violation)"
        except InvalidStatus:
            pass  # recusado no handshake HTTP: tambem aceitavel


def test_ws_rejects_refresh_token(user):
    with pytest.raises((ConnectionClosed, InvalidStatus)):
        with connect(f"{WS_URL}?token={user.refresh}", open_timeout=10) as ws:
            ws.recv(timeout=5)


# ---------------------------------------------------------------------------
# Segredos
# ---------------------------------------------------------------------------


def test_secrets_never_returned(user):
    r = user.post("/api/mcp-servers", json={"name": f"qa-sec-mcp-{uuid.uuid4().hex[:4]}", "transport": "http",
                                           "url": "http://example.invalid/mcp", "env": {"API_KEY": SECRET}})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    r2 = user.post("/api/integrations", json={"type": "github", "name": "qa-sec-gh",
                                              "config": {"owner": "qa", "token": SECRET}})
    assert r2.status_code == 201, r2.text
    iid = r2.json()["id"]
    leaks = []
    for label, resp in (
        ("POST mcp", r), ("GET mcp", user.get(f"/api/mcp-servers/{mid}")), ("LIST mcp", user.get("/api/mcp-servers")),
        ("POST integ", r2), ("GET integ", user.get(f"/api/integrations/{iid}")), ("LIST integ", user.get("/api/integrations")),
    ):
        if SECRET in resp.text:
            leaks.append(label)
    assert not leaks, f"segredo devolvido em: {leaks}"


def test_auth_responses_have_no_password_hash(user):
    for resp in (user.get("/api/auth/me"),):
        assert "password" not in resp.text.lower() and "$2b$" not in resp.text


def test_tokens_not_logged(user, ws_factory):
    """Contrato §8: logs sem segredos (nunca token)."""
    ws_factory(user.access)
    time.sleep(1)
    logs = compose("logs", "--since", "2m", "orchestrator", "nginx").stdout
    assert user.access not in logs, "access token (query string do WebSocket) aparece nos logs"
    assert user.access[:40] not in logs


# ---------------------------------------------------------------------------
# Worker inacessivel pela :80
# ---------------------------------------------------------------------------


def test_worker_not_reachable_from_port_80():
    c = http()
    for path in ("/execute", "/api/execute", "/worker/execute", "/api/worker/execute"):
        r = c.post(path, json={"agentId": str(uuid.uuid4()), "nodeId": "n", "inputs": {}, "timeout": 5},
                   headers={"X-Worker-Token": "x"})
        assert "worker_token_invalid" not in r.text and "agent_not_found" not in r.text, (path, r.status_code, r.text[:200])
        # /execute cai no portal (redirect para /login) ou em 404/405; nunca no worker.
        assert r.status_code in (302, 307, 401, 404, 405), (path, r.status_code)


def test_internal_ports_not_published():
    host = BASE_URL.split("://", 1)[1].split(":")[0].split("/")[0]
    for port in (8081, 9000, 8000, 3000):
        s = socket.socket(socket.AF_INET6 if host == "localhost" else socket.AF_INET)
        s.settimeout(2)
        try:
            rc = s.connect_ex(("::1" if host == "localhost" else host, port))
        finally:
            s.close()
        assert rc != 0, f"porta interna {port} acessivel do host"


# ---------------------------------------------------------------------------
# Rate limits (429 no envelope). Login por ultimo: bloqueia o login por 60s.
# ---------------------------------------------------------------------------


def _assert_429(resp):
    body = assert_envelope(resp, 429, "rate_limited")
    assert isinstance(body.get("details", {}).get("retryAfter"), int) and body["details"]["retryAfter"] > 0, body


def test_rate_limit_execute_5_per_min(user):
    p = seed_pipeline(user.id, [create_agent(user, "qa-rl-1"), create_agent(user, "qa-rl-2")])
    codes = []
    for _ in range(7):
        r = user.post(f"/api/pipelines/{p.id}/execute")
        codes.append(r.status_code)
        if r.status_code == 429:
            _assert_429(r)
            break
        time.sleep(0.3)
    assert 429 in codes, codes
    assert codes.index(429) == 5, f"429 deveria vir na 6a chamada: {codes}"
    assert db_query("SELECT count(*) FROM pipeline_runs WHERE pipeline_id = %s", (p.id,))[0][0] == 5


def test_rate_limit_chat_30_per_min(user):
    codes = []
    for _ in range(32):
        r = user.post("/api/agents/chat", json={"message": "oi"})
        codes.append(r.status_code)
        if r.status_code == 429:
            _assert_429(r)
            break
    assert codes.count(200) == 30 and codes[-1] == 429, codes


def test_rate_limit_upload_10_per_min_per_kb(user):
    kb = user.post("/api/knowledge", json={"name": "qa-rl-kb", "scope": "global", "source": "upload"}).json()
    codes = []
    for i in range(12):
        r = user.post(f"/api/knowledge/{kb['id']}/upload", files={"file": (f"f{i}.txt", b"x", "text/plain")})
        codes.append(r.status_code)
        if r.status_code == 429:
            _assert_429(r)
            break
    assert codes.index(429) == 10, codes


def test_rate_limit_login_429_envelope(user):
    time.sleep(61)  # janela limpa, independente dos testes anteriores
    c = http()
    codes = []
    for _ in range(7):
        r = c.post("/api/auth/login", json={"email": user.email, "password": "errada-123456"})
        codes.append(r.status_code)
        if r.status_code == 429:
            _assert_429(r)
            break
    assert codes == [401] * 5 + [429], codes
