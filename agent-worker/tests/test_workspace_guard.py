import os

import pytest
from fastapi.testclient import TestClient

from app import worker
from app.main import WORKER_TOKEN, app
from app.workspace_guard import WorkspaceEscapeError, current_workspace, resolve_in_workspace


@pytest.fixture
def ws(tmp_path):
    token = current_workspace.set(tmp_path)
    yield tmp_path
    current_workspace.reset(token)


def test_relative_and_absolute_inside(ws):
    assert resolve_in_workspace("src/a.py") == ws / "src" / "a.py"
    assert resolve_in_workspace(str(ws / "b.txt")) == ws / "b.txt"


@pytest.mark.parametrize("raw", ["/etc/passwd", "../fora.txt", "src/../../fora.txt"])
def test_escape_is_refused(ws, raw):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace(raw)


def test_symlink_out_is_refused(ws, tmp_path_factory):
    outside = tmp_path_factory.mktemp("out") / "secret.txt"
    outside.write_text("x")
    os.symlink(outside, ws / "link.txt")
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace("link.txt")


@pytest.mark.asyncio
async def test_tools_write_and_shell_use_run_workspace(ws):
    assert (await worker.execute_tool("write_file", {"path": "a.txt", "content": "oi"}))["success"]
    assert (ws / "a.txt").read_text() == "oi"
    res = await worker.execute_tool("read_file", {"path": "/etc/hostname"})
    assert "fora do workspace" in res["error"]
    shell = await worker.execute_tool("shell", {"command": "ls"})
    assert "a.txt" in shell["stdout"]


@pytest.mark.parametrize("raw", ["a\x00b.txt", None])
def test_invalid_path_raises_escape_error(ws, raw):
    with pytest.raises(WorkspaceEscapeError):
        resolve_in_workspace(raw)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_null_byte_path_returns_tool_error(ws):
    res = await worker.execute_tool("read_file", {"path": "a\x00b.txt"})
    assert "error" in res and "caminho inválido" in res["error"]
    res = await worker.execute_tool("write_file", {"path": None, "content": "x"})
    assert "error" in res


# --- /execute: workspaceDir precisa ser descendente ESTRITO de WORKSPACES_DIR ---


@pytest.mark.parametrize(
    "workspace_dir", ["/workspaces", "/workspaces/", "/workspaces-evil/x", "/workspaces/../etc"]
)
def test_execute_rejects_workspace_outside_root(workspace_dir):
    client = TestClient(app)
    resp = client.post(
        "/execute",
        json={"agentId": "a", "nodeId": "n", "inputs": {}, "timeout": 30,
              "workspaceDir": workspace_dir},
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_workspace"


def test_execute_passes_resolved_workspace(monkeypatch, tmp_path):
    from app import main as worker_main
    from app import workspace_guard

    root = tmp_path / "workspaces"
    (root / "r2").mkdir(parents=True)
    monkeypatch.setattr(worker_main, "WORKSPACES_ROOT", root)
    monkeypatch.setattr(workspace_guard, "WORKSPACES_ROOT", root)
    captured = {}

    async def fake_execute_agent(**kwargs):
        captured.update(kwargs)
        return worker.ExecutionResult(status="completed", outputs={}, action="follow",
                                      iterations=1, logs=[])

    monkeypatch.setattr(worker_main, "execute_agent", fake_execute_agent)
    client = TestClient(app)
    resp = client.post(
        "/execute",
        json={"agentId": "a", "nodeId": "n", "inputs": {}, "timeout": 30,
              "workspaceDir": f"{root}/r1/../r2", "runId": "r2", "mcpCapability": "cap"},
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert resp.status_code == 200, resp.text
    assert captured["workspace_dir"] == str((root / "r2").resolve())
    # Capacidade MCP do run repassada ao executor do agente (revisão final I4).
    assert captured["mcp_capability"] == "cap" and captured["run_id"] == "r2"


# --- Revisão final: .git reservado, workspace de run inexistente, HOME ---


@pytest.mark.parametrize(
    "raw", [".git/config", ".git", "sub/.git/hooks/pre-commit", "./.git/HEAD", "a/../.git/x"]
)
def test_dotgit_segments_are_refused(ws, raw):
    with pytest.raises(WorkspaceEscapeError) as exc:
        resolve_in_workspace(raw)
    assert ".git" in str(exc.value)


@pytest.mark.asyncio
async def test_write_to_dotgit_config_is_a_tool_error(ws):
    res = await worker.execute_tool(
        "write_file", {"path": ".git/config", "content": "[core]\n\tfsmonitor = /tmp/x\n"}
    )
    assert "error" in res and ".git" in res["error"]
    assert not (ws / ".git").exists()
    # Nome parecido (não é segmento .git) continua permitido.
    assert (await worker.execute_tool("write_file", {"path": ".gitignore", "content": "x"}))[
        "success"
    ]


@pytest.fixture
def run_root(tmp_path, monkeypatch):
    from app import main as worker_main
    from app import workspace_guard

    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(worker_main, "WORKSPACES_ROOT", root)
    monkeypatch.setattr(workspace_guard, "WORKSPACES_ROOT", root)
    return root


@pytest.mark.asyncio
async def test_missing_run_workspace_is_never_created(run_root):
    gone = run_root / "run-expirado"
    token = current_workspace.set(gone)
    try:
        res = await worker.execute_tool("write_file", {"path": "a.txt", "content": "x"})
        assert "error" in res and "não existe mais" in res["error"]
        shell = await worker.execute_tool("shell", {"command": "echo oi"})
        assert "error" in shell and "não existe mais" in shell["error"]
    finally:
        current_workspace.reset(token)
    assert not gone.exists()


def test_execute_rejects_missing_run_workspace(run_root):
    client = TestClient(app)
    resp = client.post(
        "/execute",
        json={"agentId": "a", "nodeId": "n", "inputs": {}, "timeout": 30,
              "workspaceDir": str(run_root / "run-expirado")},
        headers={"X-Worker-Token": WORKER_TOKEN},
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "invalid_workspace"
    assert not (run_root / "run-expirado").exists()


@pytest.mark.asyncio
async def test_shell_home_is_outside_workspace(ws):
    res = await worker.execute_tool("shell", {"command": 'echo "$HOME"; touch "$HOME/.cache-x"'})
    home = res["stdout"].strip()
    assert home and not home.startswith(str(ws))
    assert not (ws / ".cache-x").exists()
    # Diretório temporário removido depois do comando.
    assert not os.path.exists(home)
