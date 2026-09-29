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
    assert files.status_code == 200 and files.json() == {"items": [], "truncated": False}

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


async def test_run_workspace_purge_removes_expired(
    tmp_path, monkeypatch, session, test_engine, test_user
):
    """``app.main._run_workspace_purge``: uma rodada da limpeza por retenção
    (a função chamada no startup e a cada 24h pelo loop do lifespan) — testa
    só a iteração, sem tocar no ``asyncio.sleep`` do loop. Revisão final I2:
    runs running/paused (no banco) nunca são removidos."""
    import uuid
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    import app.db.session as db_session_module
    import app.main as main_module
    from app.core.config import settings
    from app.db.models import Pipeline, PipelineRun
    from app.runtime.workspace import WorkspaceManager

    monkeypatch.setattr(settings, "workspaces_dir", str(tmp_path / "ws"))
    monkeypatch.setattr(settings, "git_dirs_dir", str(tmp_path / "gd"))
    monkeypatch.setattr(settings, "workspace_retention_days", 7)
    monkeypatch.setattr(
        db_session_module, "async_session_factory",
        async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False),
    )
    pipeline = Pipeline(
        id=uuid.uuid4(), owner_id=test_user.owner_id, name="P", description="",
        status="running", entry_node_id=uuid.uuid4(),
    )
    session.add(pipeline)
    await session.flush()
    ids = {}
    for name, status in (("expired", "completed"), ("paused", "paused"), ("running", "running")):
        rid = uuid.uuid4()
        ids[name] = str(rid)
        session.add(PipelineRun(
            id=rid, owner_id=test_user.owner_id, pipeline_id=pipeline.id,
            thread_id=f"{pipeline.id}:{rid}", status=status, started_at=datetime.now(UTC),
        ))
    await session.commit()

    wm = WorkspaceManager()
    old = time.time() - 8 * 86400
    for rid in (*ids.values(), "fresh-run"):
        p = wm.create_empty(rid)
        if rid != "fresh-run":
            os.utime(p, (old, old))

    removed = await main_module._run_workspace_purge()

    assert removed == 1
    assert not wm.path(ids["expired"]).exists()
    assert wm.path(ids["paused"]).exists()
    assert wm.path(ids["running"]).exists()
    assert wm.path("fresh-run").exists()


# ---------------------------------------------------------------------------
# Revisão final I1: listagem limitada, zip em arquivo com teto, diff com erro
# ---------------------------------------------------------------------------


async def test_files_listing_is_capped_and_flags_truncated(
    full_client, make_run_with_workspace, monkeypatch
):
    import app.api.workspaces as workspaces_module

    monkeypatch.setattr(workspaces_module, "TREE_MAX_ENTRIES", 3)
    run_id, path = await make_run_with_workspace()
    for i in range(5):
        (path / f"f{i}.txt").write_text("x")
    data = (await full_client.get(f"/api/runs/{run_id}/files")).json()
    assert len(data["items"]) == 3
    assert data["truncated"] is True


async def test_archive_too_large_is_413(full_client, make_run_with_workspace, monkeypatch):
    import app.runtime.workspace as ws_module

    monkeypatch.setattr(ws_module, "ARCHIVE_MAX_BYTES", 10)
    # O default do parâmetro foi fixado na definição: reaplica o teto.
    original = ws_module.WorkspaceManager.zip_to_file

    def capped(self, run_id, dest, max_bytes=10):
        return original(self, run_id, dest, max_bytes=max_bytes)

    monkeypatch.setattr(ws_module.WorkspaceManager, "zip_to_file", capped)
    run_id, path = await make_run_with_workspace()
    (path / "grande.bin").write_bytes(b"x" * 100)
    resp = await full_client.get(f"/api/runs/{run_id}/archive")
    assert resp.status_code == 413
    assert resp.json()["code"] == "archive_too_large"
    assert "200 MB" in resp.json()["details"]["message"]


async def test_archive_temp_file_is_removed_after_download(
    full_client, make_run_with_workspace, monkeypatch, tmp_path
):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmpzip"))
    (tmp_path / "tmpzip").mkdir()
    run_id, path = await make_run_with_workspace()
    (path / "a.txt").write_text("oi")
    resp = await full_client.get(f"/api/runs/{run_id}/archive")
    assert resp.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(resp.content)).namelist() == ["a.txt"]
    assert list((tmp_path / "tmpzip").iterdir()) == []


async def test_diff_git_error_is_409_ptbr(full_client, make_run_with_git_workspace, monkeypatch):
    from app.runtime.workspace import WorkspaceError, WorkspaceManager

    async def boom(self, run_id):
        raise WorkspaceError("fatal: Unable to create index.lock")

    monkeypatch.setattr(WorkspaceManager, "diff", boom)
    run_id, _path = await make_run_with_git_workspace()
    resp = await full_client.get(f"/api/runs/{run_id}/diff")
    assert resp.status_code == 409
    assert resp.json()["code"] == "diff_unavailable"
    assert "index.lock" not in resp.text
