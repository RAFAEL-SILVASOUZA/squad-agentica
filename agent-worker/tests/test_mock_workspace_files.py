"""MockLLMClient grava result.md no workspace do run (Task 13).

Com ``LLM_PROVIDER=mock`` e um workspace de run definido, o agente mock pede
uma tool call ``write_file`` (caminho normal das ferramentas) com as saídas
em ``result.md``. Isso permite provar arquivos -> commit -> PR sem LLM real.
"""

from __future__ import annotations

from app import workspace_guard
from app.core.llm import MockLLMClient
from app.worker import execute_agent
from tests.test_worker_execute import MockArtifactClient


async def test_mock_writes_result_md_in_run_workspace(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_guard, "WORKSPACES_ROOT", tmp_path)
    ws = tmp_path / "run-1"
    ws.mkdir()

    result = await execute_agent(
        agent_id="test-agent-1",
        node_id="node-1",
        inputs={"task": "hello"},
        timeout=30,
        llm=MockLLMClient(),
        artifact_client=MockArtifactClient(),
        workspace_dir=str(ws),
    )

    assert result.status == "completed", result.error
    assert result.iterations == 2
    assert any("Tool call: write_file" in log for log in result.logs)
    written = (ws / "result.md").read_text(encoding="utf-8")
    assert "MOCK_LLM" in written and "hello" in written
    assert "MOCK_LLM" in result.outputs["result"]


async def test_mock_without_run_workspace_writes_nothing(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(workspace_guard, "WORKSPACES_ROOT", tmp_path / "root")

    result = await execute_agent(
        agent_id="test-agent-1",
        node_id="node-1",
        inputs={"task": "hello"},
        timeout=30,
        llm=MockLLMClient(),
        artifact_client=MockArtifactClient(),
    )

    assert result.status == "completed"
    assert result.iterations == 1
    assert not any("write_file" in log for log in result.logs)
