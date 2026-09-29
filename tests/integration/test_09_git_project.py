"""Cenario 9 - Projeto Git ponta a ponta com repositorio local (Task 13).

Pipeline vinculada a um repositorio -> run clona no workspace -> o agente mock
grava ``result.md`` (write_file) -> fim do run: commit, push da branch
``agent-portal/...`` e Pull Request no GitHub fake.

Pre-requisito (perfil ``test`` do compose; fora dele o cenario e pulado):

  docker compose -p squad-agentica --profile test up -d git-test
  GITHUB_API_BASE=http://git-test:8080 GIT_CLONE_BASE_OVERRIDE=git://git-test \\
  LLM_PROVIDER=mock EMBEDDING_PROVIDER=mock \\
    docker compose -p squad-agentica up -d --no-build orchestrator agent-worker
  docker compose -p squad-agentica restart nginx

O servico ``git-test`` roda um ``git daemon`` (repos bare em /srv/git) e o
GitHub fake ``tests/integration/fake_git_api.py`` (:8080).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest

from conftest import create_agent, docker, snapshot_of, wait_until

GIT_CONTAINER = "agent-portal-git-test"
ORCH_CONTAINER = "agent-portal-orchestrator"
REPO = "qa/projeto"
TOKEN = "qa-token-integration"

_INIT_REPO = f"""set -e
rm -rf /srv/git/{REPO}.git
git init -q --bare -b main /srv/git/{REPO}.git
tmp=$(mktemp -d); cd "$tmp"
git init -q -b main
echo '# projeto de teste' > README.md
git add README.md
git -c user.name=qa -c user.email=qa@example.com commit -qm init
git push -q /srv/git/{REPO}.git main
rm -rf "$tmp"
"""


def _git_test_exec(script: str) -> str:
    r = docker("exec", GIT_CONTAINER, "sh", "-c", script)
    assert r.returncode == 0, r.stderr or r.stdout
    return r.stdout


@dataclass
class GitTestRepo:
    full_name: str

    def branches(self) -> str:
        return _git_test_exec(
            f"git --git-dir /srv/git/{self.full_name}.git for-each-ref refs/heads "
            "--format='%(refname:short)'"
        )

    def show(self, branch: str, path: str) -> str:
        return _git_test_exec(f"git --git-dir /srv/git/{self.full_name}.git show {branch}:{path}")


def _test_profile_ready() -> str | None:
    if docker("inspect", "-f", "{{.State.Running}}", GIT_CONTAINER).stdout.strip() != "true":
        return "servico git-test (perfil test) fora do ar"
    env = docker("exec", ORCH_CONTAINER, "printenv", "GIT_CLONE_BASE_OVERRIDE").stdout.strip()
    if not env.startswith("git://git-test"):
        return "orchestrator sem GIT_CLONE_BASE_OVERRIDE=git://git-test"
    return None


@pytest.fixture(scope="module")
def git_test_repo() -> GitTestRepo:
    reason = _test_profile_ready()
    if reason:
        pytest.skip(f"{reason} (ver docstring do modulo)")
    _git_test_exec(_INIT_REPO)
    return GitTestRepo(REPO)


@dataclass
class FakeGitApi:
    def pulls(self) -> list[dict]:
        return json.loads(_git_test_exec("curl -s http://localhost:8080/_qa/pulls"))


@pytest.fixture(scope="module")
def fake_git_api(git_test_repo) -> FakeGitApi:
    _git_test_exec("curl -s -X POST http://localhost:8080/_qa/reset")
    return FakeGitApi()


def single_node_graph(agent: dict) -> dict:
    nid = str(uuid.uuid4())
    return {
        "name": f"qa-git-{uuid.uuid4().hex[:6]}",
        "description": "qa projeto git",
        "entryNodeId": nid,
        "nodes": [{"id": nid, "agentId": agent["id"], "agentSnapshot": snapshot_of(agent),
                   "position": {"x": 0, "y": 0}}],
        "edges": [],
    }


def latest_run(user, pipeline_id: str) -> dict:
    items = user.get(f"/api/pipelines/{pipeline_id}/runs").json()["items"]
    return items[0] if items else {}


def test_git_connection_test_and_repository_listing(user, fake_git_api):
    integ = user.post("/api/integrations", json={
        "type": "github", "name": f"qa-local-{uuid.uuid4().hex[:4]}", "config": {"token": TOKEN},
    }).json()
    r = user.post(f"/api/integrations/{integ['id']}/test")
    assert r.status_code == 200 and r.json() == {"ok": True, "repositories": 1}, r.text
    repos = user.get(f"/api/integrations/{integ['id']}/repositories").json()["items"]
    assert repos == [{"fullName": REPO, "defaultBranch": "main"}]
    branches = user.get(f"/api/integrations/{integ['id']}/branches", params={"repo": REPO}).json()
    assert "main" in branches["items"]

    bad = user.post("/api/integrations", json={
        "type": "github", "name": f"qa-bad-{uuid.uuid4().hex[:4]}", "config": {"token": "errado"},
    }).json()
    r = user.post(f"/api/integrations/{bad['id']}/test")
    assert r.json()["ok"] is False and "token" in r.json()["error"]
    assert "errado" not in r.text


def test_pipeline_writes_files_and_opens_pr(user, git_test_repo, fake_git_api):
    integ = user.post("/api/integrations", json={
        "type": "github", "name": f"qa-local-{uuid.uuid4().hex[:4]}", "config": {"token": TOKEN},
    }).json()
    a1 = create_agent(user, "dev", outputs=[{"name": "codigo", "type": "code", "required": True}])
    r = user.post("/api/pipelines", json={
        **single_node_graph(a1),
        "repository": {"integrationId": integ["id"], "fullName": REPO, "baseBranch": "main"},
    })
    assert r.status_code == 201, r.text
    pipe = r.json()

    r = user.post(f"/api/pipelines/{pipe['id']}/execute", json={"inputs": {"ideia": "hello"}})
    assert r.status_code == 200, r.text
    run_id = r.json()["runId"]

    wait_until(lambda: latest_run(user, pipe["id"]).get("status") == "completed",
               timeout=90, desc="run concluido")
    run = wait_until(
        lambda: (lambda x: x if x.get("publishStatus") in ("published", "failed", "no_changes")
                 else None)(latest_run(user, pipe["id"])),
        timeout=60, desc="publicacao do run",
    )

    files = user.get(f"/api/runs/{run_id}/files").json()["items"]
    paths = {f["path"] for f in files}
    assert "result.md" in paths and "README.md" in paths, files  # clone + arquivo do agente

    assert run["publishStatus"] == "published", run
    assert run["prUrl"] and run["prNumber"]

    branches = git_test_repo.branches()
    branch = next(b for b in branches.split() if b.startswith("agent-portal/"))
    assert "MOCK_LLM" in git_test_repo.show(branch, "result.md")

    pulls = fake_git_api.pulls()
    pr = next(p for p in pulls if p["html_url"] == run["prUrl"])
    assert pr["head"]["ref"] == branch and pr["base"]["ref"] == "main"
    assert "Agent Portal" in pr["body"] and "hello" in pr["body"]
    # O token nunca vai para o remoto gravado nem para o corpo do PR.
    assert TOKEN not in json.dumps(pulls)

    # Publicar de novo e idempotente: reaproveita o PR aberto.
    again = user.post(f"/api/runs/{run_id}/publish")
    assert again.status_code == 200, again.text
    assert again.json()["prUrl"] == run["prUrl"]
    assert len([p for p in fake_git_api.pulls() if p["head"]["ref"] == branch]) == 1
