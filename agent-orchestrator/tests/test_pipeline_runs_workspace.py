"""Workspace do run no disparo da pipeline e publicação manual do PR (Task 7).

- execute: clona o repositório da pipeline (ou cria workspace vazio) e passa
  ``workspace_dir`` ao executor; falha de clone grava o run como ``failed``
  sem chamar agentes;
- time travel (``checkpoints/:cpId/resume``): copia o workspace do run de
  origem para o novo run;
- ``POST /api/runs/:runId/publish``: dono do run, 409 ``run_not_completed``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.db.models import Checkpoint, PipelineRun, User


@pytest.fixture
def ws_root(monkeypatch, tmp_path):
    root = tmp_path / "workspaces"
    monkeypatch.setattr(settings, "workspaces_dir", str(root))
    return root


@pytest.fixture
def fake_executor():
    ex = MagicMock()
    ex.execute = AsyncMock(side_effect=lambda pipeline, **kw: kw["run_id"])
    with patch("app.api.pipeline_runs._get_executor", AsyncMock(return_value=ex)), \
         patch("app.api.pipeline_runs.ws_publish", new_callable=AsyncMock):
        yield ex


async def _make_pipeline(full_client, make_agent, repository=None) -> str:
    agent = await make_agent(f"A-{uuid.uuid4().hex[:6]}")
    node_id = str(uuid.uuid4())
    body = {
        "name": f"Projeto {uuid.uuid4().hex[:6]}",
        "nodes": [{
            "id": node_id, "agentId": agent["id"], "position": {"x": 0, "y": 0}, "label": "A",
            "agentSnapshot": {"agentId": agent["id"], "name": "A", "inputs": [], "outputs": [],
                              "actions": ["finalize"]},
        }],
        "edges": [],
    }
    if repository:
        body["repository"] = repository
    resp = await full_client.post("/api/pipelines", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


class _Prov:
    def __init__(self, url):
        self.url = url

    def clone_url(self, repo):
        return self.url


async def test_execute_without_repository_creates_empty_workspace(
    full_client, make_agent, ws_root, fake_executor
):
    pid = await _make_pipeline(full_client, make_agent)
    resp = await full_client.post(f"/api/pipelines/{pid}/execute", json={"inputs": {}})
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["runId"]
    kwargs = fake_executor.execute.await_args.kwargs
    assert kwargs["workspace_dir"] == str(ws_root / run_id)
    assert (ws_root / run_id).is_dir()


async def test_execute_clones_repository(
    full_client, make_agent, make_git_integration, ws_root, fake_executor, remote
):
    integ = await make_git_integration()
    pid = await _make_pipeline(full_client, make_agent, {
        "integrationId": integ["id"], "fullName": "o/r", "baseBranch": "main"})
    with patch("app.api.pipeline_runs.provider_for", return_value=_Prov(remote)):
        resp = await full_client.post(f"/api/pipelines/{pid}/execute", json={})
    assert resp.status_code == 200, resp.text
    run_id = resp.json()["runId"]
    assert (ws_root / run_id / "README.md").read_text() == "# base\n"
    assert fake_executor.execute.await_args.kwargs["workspace_dir"] == str(ws_root / run_id)


async def test_execute_clone_failure_marks_run_failed(
    full_client, make_agent, make_git_integration, ws_root, fake_executor, session, tmp_path
):
    integ = await make_git_integration()
    pid = await _make_pipeline(full_client, make_agent, {
        "integrationId": integ["id"], "fullName": "o/r", "baseBranch": "nao-existe"})
    missing = str(tmp_path / "nao-existe.git")
    with patch("app.api.pipeline_runs.provider_for", return_value=_Prov(missing)):
        resp = await full_client.post(f"/api/pipelines/{pid}/execute", json={})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "failed" and data["error"]
    fake_executor.execute.assert_not_awaited()
    run = await session.get(PipelineRun, uuid.UUID(data["runId"]))
    await session.refresh(run)
    assert run.status == "failed" and run.error == data["error"]
    assert not (ws_root / data["runId"]).exists()


async def test_time_travel_copies_source_workspace(
    full_client, make_agent, ws_root, fake_executor, session, test_user: User
):
    pid = await _make_pipeline(full_client, make_agent)
    src_run = PipelineRun(id=uuid.uuid4(), owner_id=test_user.owner_id,
                          pipeline_id=uuid.UUID(pid), thread_id=f"{pid}:src",
                          status="completed", started_at=datetime.now(UTC))
    session.add(src_run)
    await session.flush()
    cp = Checkpoint(id=uuid.uuid4(), owner_id=test_user.owner_id, pipeline_id=uuid.UUID(pid),
                    run_id=src_run.id, node_id="n", state={"data": {}}, status="completed",
                    timestamp=datetime.now(UTC), meta={})
    session.add(cp)
    await session.commit()
    src_dir = ws_root / str(src_run.id)
    (src_dir / "src").mkdir(parents=True)
    (src_dir / "src" / "a.py").write_text("print(1)\n")

    resp = await full_client.post(f"/api/pipelines/{pid}/checkpoints/{cp.id}/resume")
    assert resp.status_code == 200, resp.text
    new_id = resp.json()["runId"]
    assert (ws_root / new_id / "src" / "a.py").read_text() == "print(1)\n"
    assert fake_executor.execute.await_args.kwargs["workspace_dir"] == str(ws_root / new_id)


async def test_publish_endpoint(full_client, make_agent, session, test_user: User):
    pid = await _make_pipeline(full_client, make_agent)
    run = PipelineRun(id=uuid.uuid4(), owner_id=test_user.owner_id, pipeline_id=uuid.UUID(pid),
                      thread_id=f"{pid}:r", status="running", started_at=datetime.now(UTC))
    session.add(run)
    await session.commit()

    missing = await full_client.post(f"/api/runs/{uuid.uuid4()}/publish")
    assert missing.status_code == 404

    busy = await full_client.post(f"/api/runs/{run.id}/publish")
    assert busy.status_code == 409
    assert "run_not_completed" in busy.text

    run.status = "completed"
    await session.commit()
    fake = AsyncMock(return_value={"id": str(run.id), "publishStatus": "published"})
    with patch("app.api.pipeline_runs.publish_run", fake):
        ok = await full_client.post(f"/api/runs/{run.id}/publish")
    assert ok.status_code == 200, ok.text
    assert ok.json()["publishStatus"] == "published"
    assert fake.await_args.args[0] == str(run.id)


async def test_publish_endpoint_other_owner_404(full_client, make_agent, session):
    other = User(id=uuid.uuid4(), email=f"o-{uuid.uuid4().hex[:6]}@x.com", name="O",
                 password_hash="h")
    other.owner_id = other.id
    session.add(other)
    await session.flush()
    from app.db.models import Pipeline

    pipe = Pipeline(id=uuid.uuid4(), owner_id=other.owner_id, name="alheia", description="",
                    status="completed", entry_node_id=uuid.uuid4())
    session.add(pipe)
    await session.flush()
    run = PipelineRun(id=uuid.uuid4(), owner_id=other.owner_id, pipeline_id=pipe.id,
                      thread_id=f"{pipe.id}:r", status="completed", started_at=datetime.now(UTC))
    session.add(run)
    await session.commit()
    resp = await full_client.post(f"/api/runs/{run.id}/publish")
    assert resp.status_code == 404
