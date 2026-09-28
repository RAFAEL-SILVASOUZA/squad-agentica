"""Testes do ``WorkspaceManager`` (Task 5): clone, alterações, diff, zip, push.

Usa um repositório bare local (fixture ``remote``, em ``tests/conftest.py``,
compartilhado com a Task 7) como "remote" — evita depender de rede/GitHub
real nos testes.
"""

import subprocess

import pytest

from app.runtime.workspace import WorkspaceError, WorkspaceManager, slugify_branch


def test_slugify_branch():
    assert (
        slugify_branch("Especificação & Código!", "abcdef123456")
        == "agent-portal/especificacao-codigo-abcdef12"
    )
    assert slugify_branch("   ", "abcdef123456") == "agent-portal/pipeline-abcdef12"


async def test_clone_change_commit_push(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    path = await ws.clone("run1", remote, "main")
    (path / "src").mkdir()
    (path / "src" / "app.py").write_text("print('oi')\n")
    (path / "README.md").write_text("# alterado\n")
    changed = await ws.changed_files("run1")
    assert {"path": "src/app.py", "status": "added"} in changed
    assert {"path": "README.md", "status": "modified"} in changed
    assert "+print('oi')" in await ws.diff("run1")
    branch = await ws.commit_and_push("run1", remote, "agent-portal/x-run1", "msg")
    assert branch == "agent-portal/x-run1"
    out = subprocess.run(
        ["git", "--git-dir", remote, "branch"], capture_output=True, text=True
    ).stdout
    assert "agent-portal/x-run1" in out


async def test_existing_branch_gets_suffix_and_no_changes_returns_none(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    for run in ("r1", "r2"):
        p = await ws.clone(run, remote, "main")
        (p / f"{run}.txt").write_text(run)
        branch = await ws.commit_and_push(run, remote, "agent-portal/x", "m")
    assert branch == "agent-portal/x-2"
    await ws.clone("r3", remote, "main")
    assert await ws.commit_and_push("r3", remote, "agent-portal/y", "m") is None


async def test_clone_errors_are_clear_and_hide_credentials(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r1", remote, "nao-existe")
    assert "branch 'nao-existe' não existe" in exc.value.message
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r2", "https://user:SEGREDO@127.0.0.1:9/x.git", "main")
    assert "SEGREDO" not in exc.value.message


async def test_clone_invalid_token_message_hides_credentials(tmp_path, remote):
    """Ruling: token revogado/inválido -> mensagem clara, sem credencial exposta.

    Simula 401/403 do provedor git: usa um servidor HTTP local que sempre
    responde 401 numa URL com credenciais embutidas (user:pass@).
    """
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (assinatura da stdlib)
            self.send_response(401)
            self.end_headers()

        def log_message(self, *args):  # silencia stderr do servidor de teste
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        url = f"http://user:SEGREDO_TOKEN@127.0.0.1:{port}/o/r.git"
        ws = WorkspaceManager(tmp_path / "ws")
        with pytest.raises(WorkspaceError) as exc:
            await ws.clone("r1", url, "main")
        assert "SEGREDO_TOKEN" not in exc.value.message
        assert "token inválido ou sem acesso ao repositório" in exc.value.message
    finally:
        server.shutdown()
        thread.join()


async def test_clone_empty_repo_nonexistent_base_branch_message(tmp_path):
    """Ruling: repo vazio (sem nenhum branch) -> mesma mensagem clara de branch inexistente."""
    bare = tmp_path / "empty.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(bare)], check=True, capture_output=True
    )
    ws = WorkspaceManager(tmp_path / "ws")
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r1", str(bare), "main")
    assert "branch 'main' não existe no repositório" in exc.value.message


def test_slugify_branch_accents_and_symbols():
    assert slugify_branch("Fluxo: Atendimento & Vendas (v2)!!", "abcdef123456").startswith(
        "agent-portal/fluxo-atendimento-vendas-v2"
    )
    # Só símbolos/acentos que colapsam para vazio -> fallback "pipeline".
    assert slugify_branch("!!!???", "abcdef123456") == "agent-portal/pipeline-abcdef12"


def test_read_file_binary_large_and_escape(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    p = ws.create_empty("r1")
    (p / "img.png").write_bytes(b"\x89PNG\x00\x01")
    (p / "big.txt").write_text("x" * 20)
    assert ws.read_file("r1", "img.png")["binary"] is True
    assert ws.read_file("r1", "big.txt", max_bytes=10)["tooLarge"] is True
    with pytest.raises(WorkspaceError):
        ws.read_file("r1", "../../etc/passwd")


def test_remove_many_and_purge_older_than(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    ws.create_empty("r1")
    ws.create_empty("r2")
    ws.remove_many(["r1", "r2"])
    assert not ws.path("r1").exists()
    assert not ws.path("r2").exists()

    p3 = ws.create_empty("r3")
    import os
    import time

    old = time.time() - 8 * 86400
    os.utime(p3, (old, old))
    assert ws.purge_older_than(7) == 1
    assert not p3.exists()
