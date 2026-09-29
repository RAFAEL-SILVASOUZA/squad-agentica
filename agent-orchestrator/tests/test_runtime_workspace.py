"""Testes do ``WorkspaceManager`` (Task 5): clone, alterações, diff, zip, push.

Usa um repositório bare local (fixture ``remote``, em ``tests/conftest.py``,
compartilhado com a Task 7) como "remote" — evita depender de rede/GitHub
real nos testes.
"""

import io
import subprocess
import zipfile

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


# ---------------------------------------------------------------------------
# Fix round 1 (code review): symlink leaks, quoted/renamed paths no
# changed_files, ls-remote failure handling, path/run_id hardening, etc.
# ---------------------------------------------------------------------------


def test_tree_and_zip_skip_symlink_to_file_outside_workspace(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    p = ws.create_empty("r1")
    secret = tmp_path / "secret.txt"
    secret.write_text("SEGREDO_ORCH")
    (p / "normal.txt").write_text("ok")
    (p / "leak").symlink_to(secret)

    tree = ws.tree("r1")
    paths = {item["path"] for item in tree}
    assert "leak" not in paths
    assert "normal.txt" in paths

    names = zipfile.ZipFile(io.BytesIO(ws.zip_bytes("r1"))).namelist()
    assert "leak" not in names
    assert "normal.txt" in names

    with pytest.raises(WorkspaceError):
        ws.read_file("r1", "leak")


def test_tree_does_not_walk_symlinked_directory(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    p = ws.create_empty("r1")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("SEGREDO_DIR")
    (p / "linkdir").symlink_to(outside, target_is_directory=True)

    tree = ws.tree("r1")
    assert not any(item["path"].startswith("linkdir") for item in tree)
    assert not any("secret.txt" in item["path"] for item in tree)


async def test_changed_files_accented_name_and_rename(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "old.txt").write_text("conteudo\n")
    await ws.commit_and_push("run1", remote, "agent-portal/tmp", "add old")

    subprocess.run(
        ["git", f"--git-dir={ws.git_dir('run1')}", f"--work-tree={p}", "mv", "old.txt", "novo.txt"],
        cwd=p, check=True, capture_output=True,
    )
    (p / "especificação.md").write_text("x")

    changed = await ws.changed_files("run1")
    paths = {c["path"] for c in changed}
    assert "novo.txt" in paths
    assert "old.txt" not in paths
    assert "old.txt -> novo.txt" not in paths
    assert {"path": "especificação.md", "status": "added"} in changed


async def test_commit_and_push_unreachable_remote_raises_and_hides_credentials(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "f.txt").write_text("x")
    bad_url = "https://user:SEGREDO@127.0.0.1:9/o/r.git"
    with pytest.raises(WorkspaceError) as exc:
        await ws.commit_and_push("run1", bad_url, "agent-portal/x", "m")
    assert "SEGREDO" not in exc.value.message
    assert "não foi possível consultar o repositório remoto" in exc.value.message


def test_path_rejects_unsafe_run_id(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    for bad in ("../x", "a/b", "a\\b", "", "..", "x/../y"):
        with pytest.raises(WorkspaceError):
            ws.path(bad)


async def test_commit_and_push_without_git_returns_none(tmp_path):
    ws = WorkspaceManager(tmp_path / "ws")
    p = ws.create_empty("r1")
    (p / "f.txt").write_text("x")
    assert await ws.commit_and_push("r1", "https://example.invalid/o/r.git", "b", "m") is None


async def test_clone_into_existing_workspace_raises(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    ws.create_empty("r1")
    with pytest.raises(WorkspaceError) as exc:
        await ws.clone("r1", remote, "main")
    assert "já existe" in exc.value.message


async def test_git_env_passes_through_proxy_and_ssl_vars(tmp_path, monkeypatch):
    import app.runtime.workspace as wsmod

    captured: dict = {}

    class _FakeProc:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*args, **kwargs):
        captured.update(kwargs)
        return _FakeProc()

    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/certs/ca.pem")
    monkeypatch.setattr(wsmod.asyncio, "create_subprocess_exec", fake_exec)

    await wsmod._git(tmp_path, "status")
    env = captured["env"]
    assert env["HTTPS_PROXY"] == "http://proxy:3128"
    assert env["NO_PROXY"] == "localhost"
    assert env["SSL_CERT_FILE"] == "/etc/ssl/certs/ca.pem"


def _remote_branches(remote) -> list[str]:
    out = subprocess.run(
        ["git", "--git-dir", remote, "branch", "--format=%(refname:short)"],
        capture_output=True, text=True,
    ).stdout
    return sorted(b for b in out.split() if b)


async def test_retry_after_push_failure_publishes_committed_changes(tmp_path, remote):
    """Spec §5.9: a 1ª tentativa commitou e falhou no push; a nova tentativa
    (árvore limpa, HEAD à frente da base) ainda publica."""
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "f.txt").write_text("x")
    with pytest.raises(WorkspaceError):
        await ws.commit_and_push("run1", "https://127.0.0.1:9/o/r.git", "agent-portal/x", "m")
    # Commitado mas não publicado: continua listado contra a base.
    assert await ws.changed_files("run1") == [{"path": "f.txt", "status": "added"}]
    assert await ws.commit_and_push("run1", remote, "agent-portal/x", "m") == "agent-portal/x"
    assert "agent-portal/x" in _remote_branches(remote)


async def test_retry_after_successful_push_reuses_branch(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "f.txt").write_text("x")
    assert await ws.commit_and_push("run1", remote, "agent-portal/x", "m") == "agent-portal/x"
    assert await ws.commit_and_push("run1", remote, "agent-portal/x", "m") == "agent-portal/x"
    assert _remote_branches(remote) == ["agent-portal/x", "main"]


async def test_new_changes_after_push_go_to_suffixed_branch(tmp_path, remote):
    """Branch remota com outro SHA (novas alterações): sufixo, sem sobrescrever."""
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "f.txt").write_text("x")
    await ws.commit_and_push("run1", remote, "agent-portal/x", "m")
    (p / "g.txt").write_text("y")
    assert await ws.commit_and_push("run1", remote, "agent-portal/x", "m2") == "agent-portal/x-2"


# ---------------------------------------------------------------------------
# Revisão final C1: gitdir privado (fora do workspace) e git endurecido
# ---------------------------------------------------------------------------


def _evil_script(tmp_path, marker):
    script = tmp_path / "evil.sh"
    script.write_text(f"#!/bin/sh\ntouch {marker}\ncat\n")
    script.chmod(0o755)
    return script


def _plant_malicious_git(p, tmp_path, script, source_gitdir=None):
    """O que um agente conseguiria escrever no workspace: um ``.git`` VÁLIDO
    (cópia de um repositório) com config de fsmonitor/hooks/drivers e um
    .gitattributes pedindo esses drivers."""
    import shutil

    hooks = tmp_path / "evil-hooks"
    hooks.mkdir(exist_ok=True)
    for name in ("pre-commit", "commit-msg", "post-commit", "pre-push", "post-checkout",
                 "reference-transaction", "fsmonitor-watchman"):
        (hooks / name).write_text(script.read_text())
        (hooks / name).chmod(0o755)
    dotgit = p / ".git"
    if source_gitdir is not None:
        shutil.copytree(source_gitdir, dotgit)
    else:
        dotgit.mkdir()
        (dotgit / "HEAD").write_text("ref: refs/heads/main\n")
    (dotgit / "config").write_text(
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        "\tbare = false\n"
        f"\tfsmonitor = {script}\n"
        f"\thooksPath = {hooks}\n"
        "[diff]\n"
        f"\texternal = {script}\n"
        '[diff "evil"]\n'
        f"\ttextconv = {script}\n"
        f"\tcommand = {script}\n"
        '[filter "evil"]\n'
        f"\tclean = {script}\n"
        f"\tsmudge = {script}\n"
    )
    (p / ".gitattributes").write_text("* filter=evil diff=evil merge=evil\n")


async def test_private_gitdir_is_outside_workspace(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    gd = ws.git_dir("r1")
    assert (gd / "HEAD").is_file()
    assert ws.root.resolve() not in gd.resolve().parents
    # O workspace não aponta para o repositório (nem arquivo .git).
    assert not (p / ".git").exists()
    assert (gd / "info" / "attributes").read_text().startswith("* !filter !diff !merge")
    assert ".git" in (gd / "info" / "exclude").read_text().split()
    assert "node_modules/" in (gd / "info" / "exclude").read_text()


async def test_malicious_workspace_git_config_never_executes(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    marker = tmp_path / "PWNED"
    script = _evil_script(tmp_path, marker)
    _plant_malicious_git(p, tmp_path, script, source_gitdir=ws.git_dir("r1"))
    # Controle: o .git plantado É um repositório válido — um git "ingênuo"
    # rodando no workspace (o comportamento anterior) executaria o fsmonitor.
    subprocess.run(["git", "-c", "safe.directory=*", "status"], cwd=p, capture_output=True)
    assert marker.exists()
    marker.unlink()
    (p / "README.md").write_text("# alterado\n")
    (p / "novo.txt").write_text("conteudo\n")

    changed = {c["path"] for c in await ws.changed_files("r1")}
    assert {"README.md", "novo.txt", ".gitattributes"} <= changed
    assert not any(c.startswith(".git/") for c in changed)
    diff = await ws.diff("r1")
    assert "+conteudo" in diff
    branch = await ws.commit_and_push("r1", remote, "agent-portal/x", "m")
    assert branch == "agent-portal/x"
    assert not marker.exists(), "código do workspace executou no orchestrator"

    # O .git plantado nunca vai para o commit.
    files = subprocess.run(
        ["git", "--git-dir", remote, "ls-tree", "-r", "--name-only", "agent-portal/x"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert "novo.txt" in files
    assert not any(f == ".git" or f.startswith(".git/") for f in files)


def _plant_nested_repo(p, script, name="sub"):
    """Repositório ANINHADO no workspace (``sub/.git`` criado por um agente
    com shell): config com ``filter.evil.clean``, ``info/attributes`` pedindo
    o filtro e um arquivo rastreado "sujo" (stat alterado) — um git filho
    rodando dentro de ``sub/`` executaria o filtro."""
    import os
    import time

    sub = p / name
    sub.mkdir(parents=True)
    run = lambda *a: subprocess.run(  # noqa: E731
        ["git", "-c", "safe.directory=*", "-c", "user.name=t", "-c", "user.email=t@t", *a],
        cwd=sub, capture_output=True, check=True,
    )
    run("init", "-q", "-b", "main")
    (sub / "f.txt").write_text("sub\n")
    run("add", "f.txt")
    run("commit", "-q", "-m", "sub")
    run("config", "filter.evil.clean", f"{script}")
    (sub / ".git" / "info").mkdir(exist_ok=True)
    (sub / ".git" / "info" / "attributes").write_text("* filter=evil\n")
    # Stat-dirty: mesmo conteúdo, mtime diferente -> o git filho re-hasheia
    # (e passa pelo filtro clean).
    later = time.time() + 10
    os.utime(sub / "f.txt", (later, later))
    return sub


async def test_nested_repo_never_executes_and_never_becomes_gitlink(tmp_path, remote):
    """Revisão final 2 (Crítico): ``sub/.git`` aninhado não vira gitlink e
    nenhum git filho roda dentro de ``sub/`` (status/diff/commit)."""
    import os
    import shutil

    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    marker = tmp_path / "PWNED"
    script = _evil_script(tmp_path, marker)
    _plant_nested_repo(p, script)

    # Controle: sem o endurecimento novo, ``add -A`` registra ``sub`` como
    # gitlink e o ``git status`` seguinte roda um git filho em ``sub/`` que
    # executa o filtro da config do repositório aninhado.
    ctl_index = tmp_path / "ctl-index"
    shutil.copyfile(ws.git_dir("r1") / "index", ctl_index)
    plain = ["git", "-c", "safe.directory=*", f"--git-dir={ws.git_dir('r1')}", f"--work-tree={p}"]
    env = {**os.environ, "GIT_INDEX_FILE": str(ctl_index)}
    subprocess.run([*plain, "add", "-A"], cwd=p, env=env, capture_output=True, check=True)
    subprocess.run([*plain, "status"], cwd=p, env=env, capture_output=True)
    assert marker.exists(), "controle: o ataque deveria funcionar sem o endurecimento"
    marker.unlink()

    (p / "novo.txt").write_text("conteudo\n")
    changed = {c["path"] for c in await ws.changed_files("r1")}
    assert "novo.txt" in changed
    assert not any(c == "sub" or c.startswith("sub/") for c in changed)
    assert "+conteudo" in await ws.diff("r1")
    branch = await ws.commit_and_push("r1", remote, "agent-portal/x", "m")
    assert branch == "agent-portal/x"
    # Depois do commit (índice real atualizado), status/diff de novo.
    (p / "outro.txt").write_text("y\n")
    await ws.changed_files("r1")
    await ws.diff("r1")
    assert not marker.exists(), "filtro do repositório aninhado executou no orchestrator"

    tree = subprocess.run(
        ["git", "--git-dir", remote, "ls-tree", "-r", "agent-portal/x"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "160000" not in tree
    assert not any(line.split("\t", 1)[1].startswith("sub") for line in tree.splitlines())
    # O índice real também não guarda gitlink.
    staged = subprocess.run(
        ["git", f"--git-dir={ws.git_dir('r1')}", "ls-files", "-s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "160000" not in staged


async def test_nested_repo_defense_layers_work_independently(tmp_path, remote, monkeypatch):
    """Nome com caracteres especiais do gitignore é excluído literalmente; e,
    mesmo sem o exclude (camada 1 desligada), o gitlink é removido do índice
    antes do commit e nenhum git filho roda (camadas 2 e 3)."""
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    marker = tmp_path / "PWNED"
    script = _evil_script(tmp_path, marker)
    _plant_nested_repo(p, script, name="pasta [x]*! #")
    (p / "novo.txt").write_text("x\n")
    changed = {c["path"] for c in await ws.changed_files("r1")}
    assert changed == {"novo.txt"}

    monkeypatch.setattr(WorkspaceManager, "_exclude_nested_repos", _noop_exclude)
    ws._write_info("r1")  # exclude sem os repositórios aninhados
    _plant_nested_repo(p, script, name="outro")
    assert await ws.commit_and_push("r1", remote, "agent-portal/l", "m") == "agent-portal/l"
    (p / "mais.txt").write_text("y\n")
    await ws.changed_files("r1")
    await ws.diff("r1")
    assert not marker.exists()
    tree = subprocess.run(
        ["git", "--git-dir", remote, "ls-tree", "-r", "agent-portal/l"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "160000" not in tree


async def _noop_exclude(self, run_id):
    return None


async def test_existing_submodule_gitlink_is_preserved(tmp_path, remote):
    """Um gitlink que JÁ existe na base (submódulo legítimo do repositório)
    não é removido na publicação — só gitlinks novos/alterados."""
    seed = tmp_path / "seed"
    fake_sha = "1" * 40
    subprocess.run(
        ["git", "update-index", "--add", "--cacheinfo", f"160000,{fake_sha},lib"],
        cwd=seed, check=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "sm"],
        cwd=seed, check=True,
    )
    subprocess.run(["git", "push", "-q", "origin", "main"], cwd=seed, check=True)

    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    (p / "novo.txt").write_text("x\n")
    assert await ws.commit_and_push("r1", remote, "agent-portal/sm", "m") == "agent-portal/sm"
    tree = subprocess.run(
        ["git", "--git-dir", remote, "ls-tree", "agent-portal/sm"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert f"160000 commit {fake_sha}\tlib" in tree


async def test_info_attributes_neutralizes_worktree_filter_driver(tmp_path, remote):
    """Mesmo com um driver filter/diff DEFINIDO na config, o
    ``<gitdir>/info/attributes`` anula o .gitattributes do workspace."""
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    marker = tmp_path / "PWNED"
    script = _evil_script(tmp_path, marker)
    (p / ".gitattributes").write_text("* filter=evil diff=evil\n")
    (p / "a.txt").write_text("x\n")
    await ws._rgit(
        "r1", "-c", f"filter.evil.clean={script}", "-c", f"diff.evil.textconv={script}",
        "add", "-A",
    )
    await ws._rgit("r1", "-c", f"diff.evil.textconv={script}", "diff", "--cached")
    assert not marker.exists()


async def test_dotgit_file_pointing_elsewhere_is_ignored(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    (p / ".git").write_text(f"gitdir: {tmp_path / 'nao-existe'}\n")
    (p / "f.txt").write_text("x")
    assert {"path": "f.txt", "status": "added"} in await ws.changed_files("r1")
    assert ".git" not in {i["path"] for i in ws.tree("r1")}


async def test_remove_and_copy_handle_private_gitdir(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    (p / "f.txt").write_text("x")
    ws.copy("r1", "r2")
    assert ws.has_repo("r2")
    assert ws.git_dir("r2") != ws.git_dir("r1")
    assert {"path": "f.txt", "status": "added"} in await ws.changed_files("r2")
    # Cópia independente: commitar no r2 não mexe no r1.
    assert await ws.commit_and_push("r2", remote, "agent-portal/r2", "m") == "agent-portal/r2"
    assert {"path": "f.txt", "status": "added"} in await ws.changed_files("r1")
    ws.remove("r1")
    assert not ws.path("r1").exists() and not ws.git_dir("r1").exists()
    assert ws.has_repo("r2")


async def test_diff_uses_temporary_index(tmp_path, remote):
    """``diff`` não mexe no índice real (sem disputa de index.lock com a
    publicação): arquivo novo aparece no diff mas continua não rastreado."""
    import asyncio

    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", remote, "main")
    (p / "novo.txt").write_text("ola\n")
    index = ws.git_dir("r1") / "index"
    before = index.read_bytes()
    diffs = await asyncio.gather(*(ws.diff("r1") for _ in range(4)))
    assert all("+ola" in d for d in diffs)
    assert index.read_bytes() == before
    assert not (ws.git_dir("r1") / "index.lock").exists()


def test_purge_skips_active_runs_and_uses_newest_mtime(tmp_path):
    import os
    import time

    ws = WorkspaceManager(tmp_path / "ws")
    old = time.time() - 30 * 86400
    for rid in ("active", "stale", "nested-recent"):
        p = ws.create_empty(rid)
        (p / "sub").mkdir()
        f = p / "sub" / "f.txt"
        f.write_text("x")
        for node in (f, p / "sub", p):
            os.utime(node, (old, old))
    # Arquivo aninhado editado agora: o topo continua "velho".
    os.utime(ws.path("nested-recent") / "sub" / "f.txt", None)
    # Gitdir órfão velho (workspace já removido) também é limpo.
    orphan = ws.git_dir("orphan")
    orphan.mkdir(parents=True)
    os.utime(orphan, (old, old))

    removed = ws.purge_older_than(7, active={"active"})
    assert removed == 2
    assert ws.path("active").exists()
    assert ws.path("nested-recent").exists()
    assert not ws.path("stale").exists()
    assert not orphan.exists()


def test_tree_limited_and_zip_cap(tmp_path):
    from app.runtime.workspace import ArchiveTooLargeError

    ws = WorkspaceManager(tmp_path / "ws")
    ws.create_empty("r1")
    for i in range(12):
        (ws.path("r1") / f"f{i:02d}.txt").write_text("x" * 100)
    items, truncated = ws.tree_limited("r1", 5)
    assert len(items) == 5 and truncated is True
    items, truncated = ws.tree_limited("r1", 50)
    assert len(items) == 12 and truncated is False
    with pytest.raises(ArchiveTooLargeError):
        ws.zip_to_file("r1", tmp_path / "out.zip", max_bytes=500)
    out = ws.zip_to_file("r1", tmp_path / "ok.zip", max_bytes=10_000)
    assert len(zipfile.ZipFile(out).namelist()) == 12


@pytest.fixture
def http_git_server(tmp_path, remote):
    """Servidor git smart-HTTP local (``git http-backend`` via CGI) que exige
    Basic auth ``x-access-token:<token>`` — o mesmo formato de URL do GitHub."""
    import base64
    import http.server
    import os
    import threading
    from pathlib import Path

    token = "SEGREDO_TOKEN_HTTP_123"
    expected = "Basic " + base64.b64encode(f"x-access-token:{token}".encode()).decode()
    project_root = str(Path(remote).parent)

    class Handler(http.server.BaseHTTPRequestHandler):
        def _serve(self):
            if self.headers.get("Authorization") != expected:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="git"')
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            path, _, query = self.path.partition("?")
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "GIT_PROJECT_ROOT": project_root,
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(len(body)),
                "REMOTE_USER": "x-access-token",
                "REMOTE_ADDR": "127.0.0.1",
                "GIT_CONFIG_NOSYSTEM": "1",
            }
            if self.headers.get("Content-Encoding"):
                env["HTTP_CONTENT_ENCODING"] = self.headers["Content-Encoding"]
            out = subprocess.run(
                ["git", "http-backend"], input=body, env=env, capture_output=True
            ).stdout
            sep = b"\r\n\r\n" if b"\r\n\r\n" in out else b"\n\n"
            head, _, content = out.partition(sep)
            status = 200
            headers = []
            for line in head.decode("latin-1").splitlines():
                k, _, v = line.partition(":")
                if k.lower() == "status":
                    status = int(v.strip().split()[0])
                elif k:
                    headers.append((k, v.strip()))
            self.send_response(status)
            for k, v in headers:
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        do_GET = _serve  # noqa: N815
        do_POST = _serve  # noqa: N815

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        yield f"http://x-access-token:{token}@127.0.0.1:{port}/{Path(remote).name}", token
    finally:
        server.shutdown()
        thread.join()


async def test_credentialed_http_clone_leaves_no_token_in_gitdir_or_logs(
    tmp_path, http_git_server, caplog
):
    import logging

    url, token = http_git_server
    caplog.set_level(logging.DEBUG)
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("r1", url, "main")
    assert (p / "README.md").read_text() == "# base\n"
    (p / "novo.txt").write_text("x\n")
    assert await ws.commit_and_push("r1", url, "agent-portal/http", "m") == "agent-portal/http"

    config = (ws.git_dir("r1") / "config").read_text()
    assert token not in config
    assert "url = http://127.0.0.1:" in config
    for base in (ws.git_dir("r1"), p):
        for f in base.rglob("*"):
            if f.is_file():
                assert token.encode() not in f.read_bytes(), f"token em {f}"
    assert token not in caplog.text


async def test_changed_files_and_diff_after_publish_compare_against_base(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "README.md").write_text("# alterado\n")
    (p / "novo.txt").write_text("novo\n")
    await ws.commit_and_push("run1", remote, "agent-portal/base", "m")

    changed = {c["path"]: c["status"] for c in await ws.changed_files("run1")}
    assert changed["README.md"] == "modified"
    assert changed["novo.txt"] == "added"
    diff = await ws.diff("run1")
    assert "+# alterado" in diff and "+novo" in diff

    # Alteração não commitada depois de publicar também aparece.
    (p / "depois.txt").write_text("extra\n")
    (p / "novo.txt").unlink()
    changed = {c["path"]: c["status"] for c in await ws.changed_files("run1")}
    assert changed["depois.txt"] == "added"
    assert "novo.txt" not in changed  # criado e removido desde a base
    assert "+extra" in await ws.diff("run1")


async def test_changed_files_after_publish_reports_deleted(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run1", remote, "main")
    (p / "README.md").unlink()
    await ws.commit_and_push("run1", remote, "agent-portal/del", "m")
    changed = {c["path"]: c["status"] for c in await ws.changed_files("run1")}
    assert changed == {"README.md": "deleted"}
    assert "-" in await ws.diff("run1")
