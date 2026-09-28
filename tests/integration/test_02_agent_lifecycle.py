"""Cenario 2 - Ciclo de vida de agente: contrato de ports, skill, tool custom
(deploy e teste no sandbox), servidor MCP (fake da propria suite) e integracao
GitHub.

Fontes: spec 4.1/6.x/9.x, GUIA-API-FRONTEND (Agentes, Skills, Tools, MCP,
Integrations), contrato §8.
"""

from __future__ import annotations

import pathlib
import time
import uuid

import pytest

from conftest import COMPOSE_PROJECT, assert_envelope, create_agent, agent_body, docker

HERE = pathlib.Path(__file__).parent
NETWORK = f"{COMPOSE_PROJECT}_default"
ORCH_IMAGE = f"{COMPOSE_PROJECT}-orchestrator"


# ---------------------------------------------------------------------------
# Agente + contrato de ports
# ---------------------------------------------------------------------------


def test_agent_crud_with_port_contract(user):
    ag = create_agent(user, "qa-planner")
    assert ag["ownerId"] == user.id
    assert ag["inputs"][0]["name"] == "spec" and ag["outputs"][0]["type"] == "document"
    assert ag["actions"] == ["follow", "finalize"]
    for k in ("createdAt", "updatedAt"):
        assert ag[k], k

    got = user.get(f"/api/agents/{ag['id']}")
    assert got.status_code == 200 and got.json()["id"] == ag["id"]

    lst = user.get("/api/agents", params={"page": 1, "limit": 10}).json()
    assert set(lst) == {"items", "total", "page", "limit"}
    assert any(a["id"] == ag["id"] for a in lst["items"])

    upd = user.put(f"/api/agents/{ag['id']}", json={"description": "editado", "actions": ["follow", "return", "finalize"]})
    assert upd.status_code == 200, upd.text
    assert upd.json()["description"] == "editado"
    assert "return" in upd.json()["actions"]

    assert user.delete(f"/api/agents/{ag['id']}").status_code == 204
    assert_envelope(user.get(f"/api/agents/{ag['id']}"), 404)


@pytest.mark.parametrize(
    "override,rule",
    [
        ({"actions": ["jump"]}, "action_whitelist"),
        ({"inputs": [{"name": "x", "type": "planilha", "required": True}]}, "port_type_whitelist"),
        ({"outputs": [{"name": "r", "type": "document", "required": True}, {"name": "r", "type": "code", "required": False}]}, "port_name_unique"),
    ],
)
def test_agent_invalid_contract_structured_400(user, override, rule):
    r = user.post("/api/agents", json=agent_body(f"qa-bad-{uuid.uuid4().hex[:4]}", **override))
    body = assert_envelope(r, 400)
    rules = [e.get("rule") for e in body.get("details", {}).get("errors", [])]
    assert rule in rules, body


def test_agent_duplicate_name_409(user):
    name = f"qa-dup-{uuid.uuid4().hex[:6]}"
    assert user.post("/api/agents", json=agent_body(name)).status_code == 201
    r = user.post("/api/agents", json=agent_body(name))
    assert_envelope(r, 409)


def test_agent_build_chat_mock(user):
    """Chat de construcao (SSE) com LLM mock devolve um draft."""
    r = user.post("/api/agents/chat", json={"message": "Quero um agente revisor de PRs em Python"})
    assert r.status_code == 200, r.text[:300]
    assert len(r.text) > 0


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------


def test_skill_crud_and_attach_to_agent(user):
    builtins = user.get("/api/skills/builtins")
    assert builtins.status_code == 200 and isinstance(builtins.json()["items"], list)

    body = {
        "name": f"qa-skill-{uuid.uuid4().hex[:6]}",
        "description": "skill de teste",
        "category": "code",
        "definition": {"template": "Revise {{code}}", "variables": ["code"]},
        "inputs": [{"name": "code", "type": "code", "required": True}],
        "outputs": [{"name": "review", "type": "document", "required": True}],
    }
    r = user.post("/api/skills", json=body)
    assert r.status_code == 201, r.text
    sk = r.json()
    assert user.get(f"/api/skills/{sk['id']}").status_code == 200
    r = user.put(f"/api/skills/{sk['id']}", json={"description": "editada"})
    assert r.status_code == 200 and r.json()["description"] == "editada"

    ag = create_agent(user, "qa-with-skill", skills=[{"id": sk["id"], "name": sk["name"]}])
    assert ag["skills"][0]["id"] == sk["id"]

    assert user.delete(f"/api/skills/{sk['id']}").status_code == 204
    assert_envelope(user.get(f"/api/skills/{sk['id']}"), 404)


def test_skill_invalid_category_422(user):
    r = user.post("/api/skills", json={"name": "x", "category": "banana", "definition": {"template": "t", "variables": []}})
    assert_envelope(r, 422)


# ---------------------------------------------------------------------------
# Tool custom: deploy e teste no sandbox
# ---------------------------------------------------------------------------

GOOD_SCRIPT = "def execute(text):\n    return {'upper': text.upper(), 'len': len(text)}\n"


def test_tool_create_deploy_and_sandbox_test(user):
    body = {
        "name": f"qa-tool-{uuid.uuid4().hex[:6]}",
        "description": "upper",
        "script": GOOD_SCRIPT,
        "inputs": [{"name": "text", "type": "string", "required": True}],
        "outputs": [{"name": "upper", "type": "string"}],
    }
    r = user.post("/api/tools", json=body)
    assert r.status_code == 201, r.text
    tool = r.json()
    assert tool["status"] == "draft"

    r = user.post(f"/api/tools/{tool['id']}/deploy")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "deployed"
    assert r.json()["version"] == tool["version"] + 1

    r = user.post(f"/api/tools/{tool['id']}/test", json={"args": {"text": "abc"}, "timeout": 20})
    assert r.status_code == 200, r.text
    result = r.json()["result"]
    assert "ABC" in str(result), result

    ag = create_agent(user, "qa-with-tool", tools=[{"id": tool["id"], "name": tool["name"]}])
    assert ag["tools"][0]["id"] == tool["id"]

    assert user.delete(f"/api/tools/{tool['id']}").status_code == 204


def test_tool_deploy_invalid_script_422(user):
    r = user.post("/api/tools", json={"name": f"qa-bad-tool-{uuid.uuid4().hex[:4]}", "script": "def nope(:\n  pass"})
    assert r.status_code == 201, r.text
    r = user.post(f"/api/tools/{r.json()['id']}/deploy")
    body = assert_envelope(r, 422)
    assert body.get("details", {}).get("errors"), body


def test_tool_sandbox_error_and_timeout_are_structured(user):
    script = "import time\ndef execute(mode):\n    if mode == 'boom':\n        raise RuntimeError('kaboom')\n    time.sleep(30)\n    return {}\n"
    r = user.post("/api/tools", json={"name": f"qa-tool-err-{uuid.uuid4().hex[:4]}", "script": script})
    tid = r.json()["id"]
    r = user.post(f"/api/tools/{tid}/test", json={"args": {"mode": "boom"}, "timeout": 10})
    assert r.status_code == 200, r.text
    assert "kaboom" in str(r.json()["result"].get("error", "")), r.json()
    t0 = time.time()
    r = user.post(f"/api/tools/{tid}/test", json={"args": {"mode": "slow"}, "timeout": 2})
    assert r.status_code == 200, r.text
    assert time.time() - t0 < 15
    assert "error" in r.json()["result"], r.json()


def test_tool_sandbox_does_not_leak_orchestrator_secrets(user):
    """Spec 6.4: sandbox sem acesso aos segredos do orchestrator."""
    script = "import os\ndef execute():\n    return {k: v for k, v in os.environ.items()}\n"
    r = user.post("/api/tools", json={"name": f"qa-tool-env-{uuid.uuid4().hex[:4]}", "script": script})
    r = user.post(f"/api/tools/{r.json()['id']}/test", json={"args": {}, "timeout": 10})
    assert r.status_code == 200, r.text
    env = r.json()["result"]
    leaked = [k for k in ("JWT_SECRET", "WORKER_TOKEN", "DATABASE_URL", "MINIO_ROOT_PASSWORD", "NEXTAUTH_SECRET") if k in env]
    assert not leaked, f"segredos visiveis no sandbox: {leaked}"


# ---------------------------------------------------------------------------
# MCP server (fake da propria suite)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def mcp_fake():
    name = f"qa-mcp-fake-{uuid.uuid4().hex[:6]}"
    code = (HERE / "fake_mcp_server.py").read_text(encoding="utf-8")
    r = docker("run", "-d", "--rm", "--name", name, "--network", NETWORK, "--entrypoint", "python", ORCH_IMAGE, "-c", code)
    if r.returncode != 0:
        pytest.fail(f"nao subiu o MCP fake: {r.stderr}")
    time.sleep(2)
    yield f"http://{name}:8765/mcp"
    docker("rm", "-f", name)


def test_mcp_server_connect_discover_and_attach(user, mcp_fake):
    body = {"name": f"qa-mcp-{uuid.uuid4().hex[:6]}", "description": "fake", "transport": "http", "url": mcp_fake,
            "env": {"QA_MCP_TOKEN": "mcp-secret-value-123"}}
    r = user.post("/api/mcp-servers", json=body)
    assert r.status_code == 201, r.text
    srv = r.json()

    r = user.post(f"/api/mcp-servers/{srv['id']}/test")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "connected", r.json()
    assert [t["name"] for t in r.json()["discoveredTools"]] == ["qa_echo"]

    got = user.get(f"/api/mcp-servers/{srv['id']}").json()
    assert got["status"] == "connected" and got["lastConnectedAt"]
    assert got["discoveredTools"][0]["name"] == "qa_echo"

    ag = create_agent(user, "qa-with-mcp", mcpServers=[{"id": srv["id"], "name": srv["name"]}])
    assert ag["mcpServers"][0]["id"] == srv["id"]

    assert user.delete(f"/api/mcp-servers/{srv['id']}").status_code == 204


def test_mcp_server_unreachable_reports_error(user):
    r = user.post("/api/mcp-servers", json={"name": f"qa-mcp-dead-{uuid.uuid4().hex[:4]}", "transport": "http",
                                            "url": "http://qa-host-inexistente:9/mcp"})
    assert r.status_code == 201, r.text
    r = user.post(f"/api/mcp-servers/{r.json()['id']}/test")
    assert r.status_code == 200 and r.json()["status"] == "error", r.text


def test_mcp_server_invalid_config_rejected(user):
    r = user.post("/api/mcp-servers", json={"name": "qa-mcp-inv", "transport": "stdio"})
    assert r.status_code in (400, 422), r.text
    assert_envelope(r, r.status_code)


# ---------------------------------------------------------------------------
# Integracao GitHub
# ---------------------------------------------------------------------------


def test_github_integration_crud(user):
    r = user.post("/api/integrations", json={"type": "github", "name": f"qa-gh-{uuid.uuid4().hex[:4]}", "config": {"owner": "qa-org"}})
    assert r.status_code == 201, r.text
    integ = r.json()
    assert integ["type"] == "github" and integ["ownerId"] == user.id
    r = user.put(f"/api/integrations/{integ['id']}", json={"status": "disabled"})
    assert r.status_code == 200 and r.json()["status"] == "disabled"
    # GitHub without owner now succeeds (owner is optional)
    r = user.post("/api/integrations", json={"type": "github", "name": "qa-gh-2", "config": {}})
    assert r.status_code == 201, r.text
    gh_no_owner = r.json()
    assert user.delete(f"/api/integrations/{gh_no_owner['id']}").status_code == 204
    # Azure without organization should fail with invalid_config
    r = user.post("/api/integrations", json={"type": "azure", "name": "qa-az-invalid", "config": {}})
    assert_envelope(r, 400, "invalid_config")
    assert user.delete(f"/api/integrations/{integ['id']}").status_code == 204


def test_github_endpoints_structured_errors(user):
    """Sem integracao: 404 estruturado. Com integracao e sem GITHUB_TOKEN: 502 github_error."""
    r = user.get("/api/integrations/github/repos")
    assert_envelope(r, 404)
    user.post("/api/integrations", json={"type": "github", "name": f"qa-gh-e-{uuid.uuid4().hex[:4]}", "config": {"owner": "qa-org"}})
    r = user.get("/api/integrations/github/repos")
    assert r.status_code in (200, 502), r.text
    if r.status_code == 502:
        assert_envelope(r, 502, "github_error")


def test_github_with_mocked_api():
    """Integracao GitHub com API mockada (cenario 2).

    F17 corrigido: ``GITHUB_API_BASE`` (settings) permite apontar o orchestrator
    para um GitHub fake; a URL repassada e coberta em
    ``agent-orchestrator/tests/test_integrations_github_mock.py``. Contra o stack
    compartilhado continua pulado: exigiria subir o orchestrator com
    ``GITHUB_API_BASE`` de um servidor fake alcancavel pela rede do compose.
    """
    pytest.skip("requer stack com GITHUB_API_BASE apontando para um GitHub fake (coberto no unit test)")
