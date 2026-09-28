import os

import pytest

from app import worker
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
