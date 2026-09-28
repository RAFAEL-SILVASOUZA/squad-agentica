"""API de arquivos do run: listagem, conteúdo, diff e zip (Task 8).

Dono: rt-executor. GET /api/runs/:runId/{files,files/content,diff,archive}.
Todos exigem que o run pertença ao usuário autenticado (404 ``run_not_found``);
workspace ausente (ex.: purgado) responde vazio/404 conforme o endpoint.
"""

from __future__ import annotations

import io
import os
import re
import time
import zipfile


async def test_files_content_diff_and_zip(full_client, make_run_with_workspace):
    run_id, path = await make_run_with_workspace()
    (path / "src").mkdir()
    (path / "src" / "a.py").write_text("print(1)\n")
    (path / "logo.png").write_bytes(b"\x89PNG\x00")

    files = (await full_client.get(f"/api/runs/{run_id}/files")).json()["items"]
    assert {f["path"] for f in files} == {"src/a.py", "logo.png"}
    assert next(f for f in files if f["path"] == "logo.png")["binary"] is True

    content = (
        await full_client.get(f"/api/runs/{run_id}/files/content", params={"path": "src/a.py"})
    ).json()
    assert content["content"] == "print(1)\n"
    bad = await full_client.get(
        f"/api/runs/{run_id}/files/content", params={"path": "../../etc/passwd"}
    )
    assert bad.status_code == 400
    assert bad.json()["code"] == "invalid_path"
    assert bad.json()["error"] == "validation error"

    z = await full_client.get(f"/api/runs/{run_id}/archive")
    assert z.status_code == 200, z.text
    assert z.headers["content-type"] == "application/zip"
    assert "attachment;" in z.headers["content-disposition"]
    assert "src/a.py" in zipfile.ZipFile(io.BytesIO(z.content)).namelist()


async def test_files_content_missing_file_404(full_client, make_run_with_workspace):
    run_id, _path = await make_run_with_workspace()
    resp = await full_client.get(
        f"/api/runs/{run_id}/files/content", params={"path": "nope.txt"}
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "file_not_found"


async def test_diff_empty_without_git_repo(full_client, make_run_with_workspace):
    run_id, path = await make_run_with_workspace()
    (path / "a.txt").write_text("x")
    resp = await full_client.get(f"/api/runs/{run_id}/diff")
    assert resp.status_code == 200
    assert resp.json() == {"diff": "", "truncated": False}


async def test_diff_small_change_is_not_truncated(full_client, make_run_with_git_workspace):
    run_id, path = await make_run_with_git_workspace()
    (path / "novo.txt").write_text("ola\n")

    resp = await full_client.get(f"/api/runs/{run_id}/diff")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["truncated"] is False
    assert "+ola" in data["diff"]


async def test_diff_large_change_is_truncated_at_line_boundary(
    full_client, make_run_with_git_workspace
):
    from app.runtime.workspace import DIFF_MAX_CHARS

    run_id, path = await make_run_with_git_workspace()
    # Diff bem maior que o limite (cada linha nova conta como uma linha do
    # diff, prefixada com "+"): força o truncamento.
    (path / "grande.txt").write_text(
        "\n".join(f"linha numero {i:06d} de conteudo bem grande" for i in range(20_000)) + "\n"
    )

    resp = await full_client.get(f"/api/runs/{run_id}/diff")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["truncated"] is True
    assert len(data["diff"]) <= DIFF_MAX_CHARS
    # Cortado numa quebra de linha: a última linha do texto truncado (se for
    # uma linha de conteúdo, não um cabeçalho do diff) está completa, nunca
    # partida no meio.
    last_line = data["diff"].splitlines()[-1] if data["diff"] else ""
    if last_line.startswith("+linha numero"):
        assert re.fullmatch(r"\+linha numero \d{6} de conteudo bem grande", last_line)


async def test_diff_binary_file_does_not_dump_bytes(full_client, make_run_with_git_workspace):
    run_id, path = await make_run_with_git_workspace()
    (path / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x01\x02\x03\x04\x05")

    resp = await full_client.get(f"/api/runs/{run_id}/diff")
    assert resp.status_code == 200, resp.text
    diff = resp.json()["diff"]
    assert "Binary files" in diff
    assert "\x89PNG" not in diff
    assert "\x00" not in diff


async def test_missing_workspace_responses(full_client, make_run_with_workspace):
    run_id, path = await make_run_with_workspace()
    # Workspace purgado: diretório removido, run continua no banco.
    import shutil

    shutil.rmtree(path)

    files = await full_client.get(f"/api/runs/{run_id}/files")
    assert files.status_code == 200 and files.json() == {"items": []}

    diff = await full_client.get(f"/api/runs/{run_id}/diff")
    assert diff.status_code == 200 and diff.json() == {"diff": "", "truncated": False}

    archive = await full_client.get(f"/api/runs/{run_id}/archive")
    assert archive.status_code == 404
    assert archive.json()["code"] == "workspace_not_found"

    content = await full_client.get(
        f"/api/runs/{run_id}/files/content", params={"path": "a.txt"}
    )
    assert content.status_code == 404
    assert content.json()["code"] == "file_not_found"


async def test_other_owner_gets_404(client_other_user, make_run_with_workspace):
    run_id, _ = await make_run_with_workspace()
    resp = await client_other_user.get(f"/api/runs/{run_id}/files")
    assert resp.status_code == 404
    assert resp.json()["code"] == "run_not_found"


async def test_run_workspace_purge_removes_expired(tmp_path, monkeypatch):
    """``app.main._run_workspace_purge``: uma rodada da limpeza por retenção
    (a função chamada no startup e a cada 24h pelo loop do lifespan) — testa
    só a iteração, sem tocar no ``asyncio.sleep`` do loop."""
    import app.main as main_module
    from app.core.config import settings
    from app.runtime.workspace import WorkspaceManager

    monkeypatch.setattr(settings, "workspaces_dir", str(tmp_path))
    monkeypatch.setattr(settings, "workspace_retention_days", 7)
    wm = WorkspaceManager(tmp_path)
    wm.create_empty("expired-run")
    wm.create_empty("fresh-run")
    old = time.time() - 8 * 86400
    os.utime(tmp_path / "expired-run", (old, old))

    removed = await main_module._run_workspace_purge()

    assert removed == 1
    assert not (tmp_path / "expired-run").exists()
    assert (tmp_path / "fresh-run").exists()
