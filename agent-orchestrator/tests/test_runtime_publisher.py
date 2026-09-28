"""Publicação do workspace de um run: commit, push e Pull Request (Task 7).

``publish_workspace`` usa o remote bare local (fixture ``remote`` de
``tests/conftest.py``) e um provedor fake; ``publish_run`` usa o banco de
teste (fixture ``session``) e grava ``publish_status``/``pr_url``/
``pr_number``/``publish_error`` no run.
"""

from __future__ import annotations

import asyncio
import subprocess
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Checkpoint, Integration, Pipeline, PipelineNode, PipelineRun, User
from app.integrations.git_providers import GitProviderError, PullRequest
from app.runtime.publisher import build_pr_body, publish_run, publish_workspace
from app.runtime.workspace import WorkspaceManager


class FakeProvider:
    def __init__(self, remote):
        self.remote, self.created = remote, []

    def clone_url(self, repo):
        return self.remote

    async def find_open_pull_request(self, repo, head):
        return next((pr for h, pr in self.created if h == head), None)

    async def create_pull_request(self, repo, head, base, title, body):
        pr = PullRequest(len(self.created) + 1, f"https://example/pr/{len(self.created) + 1}")
        self.created.append((head, pr))
        self.last_title, self.last_body = title, body
        return pr


@pytest.mark.asyncio
async def test_publish_creates_branch_and_pr_and_is_idempotent(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone("run-abc12345", remote, "main")
    (p / "novo.txt").write_text("x")
    prov = FakeProvider(remote)
    first = await publish_workspace(ws, prov, run_id="run-abc12345", repo="o/r", base="main",
                                    pipeline_name="Projeto X", title="Projeto X: ideia", body="b")
    assert first == {"status": "published", "number": 1, "url": "https://example/pr/1",
                     "branch": "agent-portal/projeto-x-runabc12"}
    again = await publish_workspace(ws, prov, run_id="run-abc12345", repo="o/r", base="main",
                                    pipeline_name="Projeto X", title="t", body="b")
    assert again["number"] == 1 and len(prov.created) == 1


@pytest.mark.asyncio
async def test_publish_without_changes(tmp_path, remote):
    ws = WorkspaceManager(tmp_path / "ws")
    await ws.clone("r2", remote, "main")
    res = await publish_workspace(ws, FakeProvider(remote), run_id="r2", repo="o/r", base="main",
                                  pipeline_name="P", title="t", body="b")
    assert res == {"status": "no_changes"}


def test_pr_body_has_inputs_outputs_and_link():
    body = build_pr_body(inputs={"ideia": "app"}, outputs={"Redator": {"spec": "# Spec"}},
                         run_url="http://localhost/pipelines/p/run")
    assert "app" in body and "# Spec" in body and "http://localhost/pipelines/p/run" in body


def test_pr_body_is_bounded():
    body = build_pr_body(
        inputs={"ideia": "i" * 50_000},
        outputs={f"A{i}": {"out": "o" * 50_000, "_interno": "segredo"} for i in range(40)},
        run_url="http://x",
    )
    assert len(body) <= 60_000
    assert "segredo" not in body


# ---------------------------------------------------------------------------
# publish_run (banco de teste)
# ---------------------------------------------------------------------------


async def _seed(session, user: User, *, with_repo: bool, status: str = "completed"):
    integ = None
    if with_repo:
        integ = Integration(id=uuid.uuid4(), owner_id=user.owner_id, type="github",
                            name=f"gh-{uuid.uuid4().hex[:6]}", config={"token": "tok-secreto"})
        session.add(integ)
        await session.flush()
    node_id = uuid.uuid4()
    pipe = Pipeline(
        id=uuid.uuid4(), owner_id=user.owner_id, name="Projeto X", description="",
        status="completed", entry_node_id=node_id,
        git_integration_id=integ.id if integ else None,
        git_repository="o/r" if integ else None,
        git_base_branch="main" if integ else None,
    )
    session.add(pipe)
    await session.flush()
    session.add(PipelineNode(
        id=node_id, pipeline_id=pipe.id, agent_id=uuid.uuid4(),
        agent_snapshot={"name": "Redator"}, position={"x": 0, "y": 0}, label="Redator",
    ))
    run_id = uuid.uuid4()
    run = PipelineRun(id=run_id, owner_id=user.owner_id, pipeline_id=pipe.id,
                      thread_id=f"{pipe.id}:{run_id}", status=status,
                      started_at=datetime.now(UTC))
    session.add(run)
    await session.flush()
    session.add(Checkpoint(
        id=uuid.uuid4(), owner_id=user.owner_id, pipeline_id=pipe.id, run_id=run_id,
        node_id=str(node_id), status="completed", timestamp=datetime.now(UTC), meta={},
        state={"data": {str(node_id): {"spec": "# Spec gerada"}},
               "run_inputs": {"ideia": "app de tarefas com lembretes " * 5}},
    ))
    await session.commit()
    return run


async def test_publish_run_without_repository_sets_none(session, test_user, tmp_path):
    run = await _seed(session, test_user, with_repo=False)
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        out = await publish_run(str(run.id), db=session, manager=WorkspaceManager(tmp_path))
    assert out["publishStatus"] == "none"
    assert out["prUrl"] is None


async def test_publish_run_opens_pr_and_records_it(session, test_user, tmp_path, remote):
    run = await _seed(session, test_user, with_repo=True)
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone(str(run.id), remote, "main")
    (p / "spec.md").write_text("# Spec\n")
    prov = FakeProvider(remote)
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock) as pub:
        out = await publish_run(str(run.id), db=session, manager=ws,
                                provider_factory=lambda integ: prov)
    assert out["publishStatus"] == "published"
    assert out["prUrl"] == "https://example/pr/1" and out["prNumber"] == 1
    assert out["publishError"] is None
    assert prov.last_title.startswith("Projeto X: app de tarefas")
    assert len(prov.last_title) <= len("Projeto X: ") + 61
    assert "# Spec gerada" in prov.last_body and "Redator" in prov.last_body
    assert "tok-secreto" not in prov.last_body
    # Evento agregado para o monitor recarregar o run.
    payload = pub.await_args.args[2]
    assert payload["runId"] == str(run.id) and payload["nodeId"] == ""
    await session.refresh(run)
    assert run.status == "completed" and run.publish_status == "published"


async def test_publish_run_no_changes(session, test_user, tmp_path, remote):
    run = await _seed(session, test_user, with_repo=True)
    ws = WorkspaceManager(tmp_path / "ws")
    await ws.clone(str(run.id), remote, "main")
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        out = await publish_run(str(run.id), db=session, manager=ws,
                                provider_factory=lambda integ: FakeProvider(remote))
    assert out["publishStatus"] == "no_changes"


async def test_publish_run_failure_is_recorded(session, test_user, tmp_path, remote):
    run = await _seed(session, test_user, with_repo=True)

    def broken(integ):
        raise GitProviderError("Conexão Azure DevOps sem organização")

    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        out = await publish_run(str(run.id), db=session, manager=WorkspaceManager(tmp_path),
                                provider_factory=broken)
    assert out["publishStatus"] == "failed"
    assert out["publishError"] == "Conexão Azure DevOps sem organização"
    assert out["status"] == "completed"


async def test_publish_run_unexpected_error_is_recorded(session, test_user, tmp_path):
    run = await _seed(session, test_user, with_repo=True)

    def boom(integ):
        raise RuntimeError("https://x-access-token:tok-secreto@github.com")

    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        out = await publish_run(str(run.id), db=session, manager=WorkspaceManager(tmp_path),
                                provider_factory=boom)
    assert out["publishStatus"] == "failed"
    assert "tok-secreto" not in (out["publishError"] or "")


# ---------------------------------------------------------------------------
# Spec §5.9: nova tentativa depois de falha parcial
# ---------------------------------------------------------------------------


def _remote_branches(remote) -> list[str]:
    out = subprocess.run(
        ["git", "--git-dir", remote, "branch", "--format=%(refname:short)"],
        capture_output=True, text=True,
    ).stdout
    return sorted(b for b in out.split() if b)


class FlakyPRProvider(FakeProvider):
    """create_pull_request falha na 1ª chamada (depois do push)."""

    def __init__(self, remote):
        super().__init__(remote)
        self.fail_next = True

    async def create_pull_request(self, repo, head, base, title, body):
        if self.fail_next:
            self.fail_next = False
            raise GitProviderError("criar PR: erro 422 do provedor")
        return await super().create_pull_request(repo, head, base, title, body)


async def test_retry_after_pr_failure_publishes_on_same_branch(
    session, test_user, tmp_path, remote
):
    run = await _seed(session, test_user, with_repo=True)
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone(str(run.id), remote, "main")
    (p / "spec.md").write_text("# Spec\n")
    prov = FlakyPRProvider(remote)
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        first = await publish_run(str(run.id), db=session, manager=ws,
                                  provider_factory=lambda integ: prov)
        assert first["publishStatus"] == "failed"
        assert first["publishError"] == "criar PR: erro 422 do provedor"
        again = await publish_run(str(run.id), db=session, manager=ws,
                                  provider_factory=lambda integ: prov)
    assert again["publishStatus"] == "published" and again["prNumber"] == 1
    branch = prov.created[0][0]
    assert not branch.endswith("-2")
    assert _remote_branches(remote) == sorted(["main", branch])


class SwitchRemoteProvider(FakeProvider):
    """1ª tentativa aponta para um remoto inalcançável (push falha)."""

    def __init__(self, remote):
        super().__init__(remote)
        self.urls = ["https://127.0.0.1:9/o/r.git", remote]

    def clone_url(self, repo):
        return self.urls.pop(0) if len(self.urls) > 1 else self.urls[0]


async def test_retry_after_push_failure_publishes(session, test_user, tmp_path, remote):
    run = await _seed(session, test_user, with_repo=True)
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone(str(run.id), remote, "main")
    (p / "spec.md").write_text("# Spec\n")
    prov = SwitchRemoteProvider(remote)
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        first = await publish_run(str(run.id), db=session, manager=ws,
                                  provider_factory=lambda integ: prov)
        assert first["publishStatus"] == "failed"
        again = await publish_run(str(run.id), db=session, manager=ws,
                                  provider_factory=lambda integ: prov)
    assert again["publishStatus"] == "published" and len(prov.created) == 1


class SlowProvider(FakeProvider):
    async def find_open_pull_request(self, repo, head):
        await asyncio.sleep(0.05)
        return await super().find_open_pull_request(repo, head)


async def test_concurrent_publish_creates_one_pr(session, test_engine, test_user, tmp_path, remote):
    run = await _seed(session, test_user, with_repo=True)
    ws = WorkspaceManager(tmp_path / "ws")
    p = await ws.clone(str(run.id), remote, "main")
    (p / "spec.md").write_text("# Spec\n")
    prov = SlowProvider(remote)
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        async with factory() as other:
            a, b = await asyncio.gather(
                publish_run(str(run.id), db=session, manager=ws,
                            provider_factory=lambda integ: prov),
                publish_run(str(run.id), db=other, manager=ws,
                            provider_factory=lambda integ: prov),
            )
    assert len(prov.created) == 1
    assert a["publishStatus"] == b["publishStatus"] == "published"
    assert a["prNumber"] == b["prNumber"] == 1


async def test_missing_integration_with_repository_fails(session, test_user, tmp_path):
    run = await _seed(session, test_user, with_repo=True)
    run_id = str(run.id)
    pipe = await session.get(Pipeline, run.pipeline_id)
    integ = await session.get(Integration, pipe.git_integration_id)
    await session.delete(integ)
    await session.commit()
    session.expire_all()
    with patch("app.runtime.publisher.ws_publish", new_callable=AsyncMock):
        out = await publish_run(run_id, db=session, manager=WorkspaceManager(tmp_path))
    assert out["publishStatus"] == "failed"
    assert out["publishError"] == "conexão Git da pipeline não encontrada"
