import asyncio
import os
import uuid
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.mcp.registry import MCPRegistry


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case,expected", [("echo", 200), ("no_token", 401), ("other_owner", 404), ("missing", 502)]
)
async def test_internal_mcp(full_app, session, test_user, case, expected):
    from app.api.internal_mcp import router
    from app.main import app

    assert any(route.path == "/internal/mcp/{server_id}/call" for route in app.routes)
    full_app.include_router(router)
    server = await MCPRegistry(session).create(
        owner_id=test_user.id,
        name="Echo",
        description="",
        transport="stdio",
        command="not-a-real-program"
        if case == "missing"
        else "python tests/fixtures/echo_mcp_server.py",
        env={"PRIVATE_VALUE": "never-echo-this-secret"},
    )
    async with AsyncClient(transport=ASGITransport(app=full_app), base_url="http://test") as client:
        response = await client.post(
            f"/internal/mcp/{server.id}/call",
            headers={} if case == "no_token" else {"X-Worker-Token": settings.worker_token},
            json={
                "ownerId": str(uuid.uuid4() if case == "other_owner" else test_user.id),
                "tool": "echo",
                "arguments": {"text": "Olá"},
            },
        )
    assert response.status_code == expected, response.text
    assert "never-echo-this-secret" not in response.text
    if case == "echo":
        assert response.json() == {"content": [{"type": "text", "text": "Olá"}], "isError": False}
    if case == "missing":
        assert response.json()["code"] == "mcp_call_failed"
        assert "não encontrado" in response.text


@pytest.mark.asyncio
async def test_connection_discovers_real_stdio_tools(full_app, session, test_user):
    from app.api.mcp_servers import router

    full_app.include_router(router, prefix="/api")
    server = await MCPRegistry(session).create(
        owner_id=test_user.id,
        name="Echo",
        description="",
        transport="stdio",
        command='python "tests/fixtures/echo_mcp_server.py"',
    )
    async with AsyncClient(transport=ASGITransport(app=full_app), base_url="http://test") as client:
        response = await client.post(f"/api/mcp-servers/{server.id}/test")
    assert response.json()["status"] == "connected"
    assert response.json()["discoveredTools"][0]["name"] == "echo"


@pytest.mark.asyncio
async def test_agent_artifact_materializes_owned_mcp(session, test_user, mock_agent_storage):
    import yaml

    from app.agents.service import AgentService

    server = await MCPRegistry(session).create(
        owner_id=test_user.id,
        name="Echo",
        description="",
        transport="stdio",
        command="python tests/fixtures/echo_mcp_server.py",
    )
    server.discovered_tools = [
        {"name": "echo", "description": "Eco", "inputSchema": {"type": "object"}}
    ]
    await session.commit()
    agent = await AgentService(mock_agent_storage).create_agent(
        session,
        test_user.id,
        {
            "name": "Echo agent",
            "type": "custom",
            "prompt": "Eco",
            "actions": ["finalize"],
            "mcpServers": [{"serverId": str(server.id)}],
        },
    )
    artifact = yaml.safe_load(mock_agent_storage.store[str(agent.id)])
    assert artifact["mcpServers"] == [
        {"serverId": str(server.id), "tools": server.discovered_tools}
    ]


def test_connection_error_never_contains_remote_secrets():
    from app.mcp.client import describe_connection_error

    message = describe_connection_error(
        RuntimeError("secret-value"), "http", None, "https://secret-value@example.com"
    )
    assert "secret-value" not in message


@pytest.mark.asyncio
async def test_stdio_large_result():
    from app.mcp.client import MCPClient

    client = MCPClient("stdio", "python tests/fixtures/echo_mcp_server.py")
    try:
        await client.connect()
        result = await client.call_tool("echo", {"text": "x" * 100_000})
        assert result["content"][0]["text"] == "x" * 100_000
    finally:
        await client.disconnect()


ECHO_SERVER = Path(__file__).parent / "fixtures" / "echo_mcp_server.py"
HANG_SERVER = Path(__file__).parent / "fixtures" / "hang_mcp_server.py"


async def _post_call(full_app, server_id, owner_id, tool, arguments, **extra):
    from app.api.internal_mcp import router

    full_app.include_router(router)
    headers = extra.pop("headers", {"X-Worker-Token": settings.worker_token})
    async with AsyncClient(transport=ASGITransport(app=full_app), base_url="http://test") as client:
        return await client.post(
            f"/internal/mcp/{server_id}/call",
            headers=headers,
            json={"ownerId": str(owner_id), "tool": tool, "arguments": arguments, **extra},
        )


async def _echo_server(session, test_user):
    return await MCPRegistry(session).create(
        owner_id=test_user.id,
        name="Echo",
        description="",
        transport="stdio",
        command=f'python "{ECHO_SERVER}"',
    )


@pytest.mark.asyncio
async def test_stdio_server_runs_in_run_workspace(
    full_app, session, test_user, tmp_path, monkeypatch
):
    root = tmp_path / "workspaces"
    workspace = root / "run-1"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(settings, "workspaces_dir", str(root))
    server = await _echo_server(session, test_user)

    response = await _post_call(
        full_app, server.id, test_user.id, "cwd", {}, workspaceDir=str(workspace)
    )
    assert response.status_code == 200, response.text
    assert response.json()["content"][0]["text"] == str(workspace.resolve())

    # Sem workspace: cwd padrão do orchestrator (sem 422).
    response = await _post_call(full_app, server.id, test_user.id, "cwd", {})
    assert response.status_code == 200, response.text
    assert response.json()["content"][0]["text"] == os.getcwd()


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["outside", "traversal", "root", "missing"])
async def test_workspace_outside_root_is_rejected(
    full_app, session, test_user, tmp_path, monkeypatch, where
):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setattr(settings, "workspaces_dir", str(root))
    workspace_dir = {
        "outside": str(tmp_path),
        "traversal": str(root / "run-1" / ".." / ".."),
        "root": str(root),
        "missing": str(root / "run-inexistente"),
    }[where]
    server = await _echo_server(session, test_user)

    response = await _post_call(
        full_app, server.id, test_user.id, "cwd", {}, workspaceDir=workspace_dir
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_mcp_path"


@pytest.mark.asyncio
async def test_non_ascii_token_is_unauthorized(full_app, session, test_user):
    server = await _echo_server(session, test_user)
    response = await _post_call(
        full_app,
        server.id,
        test_user.id,
        "echo",
        {"text": "x"},
        headers={"X-Worker-Token": "tökén-inválido".encode("latin-1")},
    )
    assert response.status_code == 401


def _alive(pid: int) -> bool:
    """Vivo = existe e não é zumbi (o PID 1 do container pode não reaper)."""
    try:
        with open(f"/proc/{pid}/stat") as fh:
            return fh.read().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


@pytest.mark.asyncio
async def test_call_timeout_kills_whole_process_group(tmp_path, monkeypatch):
    import app.mcp.client as client_module

    monkeypatch.setattr(client_module, "CALL_TIMEOUT", 0.5)
    pid_file = tmp_path / "child.pid"
    client = client_module.MCPClient("stdio", f'python "{HANG_SERVER}" "{pid_file}"')
    await client.connect()
    leader = client._process.pid
    child = int(pid_file.read_text())
    try:
        with pytest.raises(TimeoutError):
            await client.call_tool("anything", {})
    finally:
        await client.disconnect()
    await asyncio.sleep(0.2)
    assert not _alive(leader)
    assert not _alive(child)


@pytest.mark.asyncio
async def test_cancelled_disconnect_still_kills_group(tmp_path):
    from app.mcp.client import MCPClient

    pid_file = tmp_path / "child.pid"
    client = MCPClient("stdio", f'python "{HANG_SERVER}" "{pid_file}"')
    await client.connect()
    leader = client._process.pid
    child = int(pid_file.read_text())
    # O servidor ignora SIGTERM: o disconnect fica na espera de 5 s e é
    # cancelado no meio; o SIGKILL do grupo ainda precisa acontecer.
    task = asyncio.create_task(client.disconnect())
    await asyncio.sleep(0.3)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.2)
    assert not _alive(leader)
    assert not _alive(child)


@pytest.mark.asyncio
async def test_resolve_mcp_refs_skips_invalid_and_deleted(session, test_user):
    from app.mcp.registry import resolve_mcp_refs

    registry = MCPRegistry(session)
    kept = await registry.create(
        owner_id=test_user.id, name="Kept", description="", transport="stdio", command="x"
    )
    kept.discovered_tools = [{"name": "echo", "description": "", "inputSchema": {}}]
    await session.commit()
    gone = await registry.create(
        owner_id=test_user.id, name="Gone", description="", transport="stdio", command="x"
    )
    gone_id = gone.id
    await registry.delete(gone_id, test_user.id)

    servers, warnings = await resolve_mcp_refs(
        session,
        test_user.id,
        [{"serverId": str(kept.id)}, {"serverId": str(gone_id)}, {"serverId": "not-a-uuid"}, {}],
    )
    assert servers == [{"serverId": str(kept.id), "tools": kept.discovered_tools}]
    assert len(warnings) == 3
    assert any(str(gone_id) in w for w in warnings)


@pytest.mark.asyncio
async def test_worker_client_sends_resolved_mcp_servers():
    import json

    import httpx

    from tests.test_rt_worker_client import _make_client

    refs = [{"serverId": "s1", "tools": [{"name": "echo"}]}]

    def handle(request):
        body = json.loads(request.content)
        assert body["ownerId"] == "owner-1"
        assert body["mcpServers"] == refs
        return httpx.Response(
            200, json={"status": "completed", "outputs": {}, "action": "finalize"}
        )

    client = _make_client(handle)
    result = await client.execute("a", "n", {}, owner_id="owner-1", mcp_servers=refs)
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_run_with_deleted_mcp_server_still_executes(
    session, test_user, mock_agent_storage, monkeypatch, caplog
):
    """Servidor removido depois de salvo no agente: o run segue sem as tools dele."""
    import logging
    from contextlib import asynccontextmanager
    from unittest.mock import AsyncMock, patch

    from langgraph.checkpoint.memory import MemorySaver

    import app.runtime.executor as executor_module
    from app.agents.service import AgentService
    from app.compiler.graph_builder import (
        AgentSnapshot,
        Pipeline,
        PipelineNode,
        WorkerResponse,
    )

    registry = MCPRegistry(session)
    kept = await registry.create(
        owner_id=test_user.id, name="Kept", description="", transport="stdio", command="x"
    )
    kept.discovered_tools = [{"name": "echo", "description": "Novo", "inputSchema": {}}]
    await session.commit()
    gone = await registry.create(
        owner_id=test_user.id, name="Gone", description="", transport="stdio", command="x"
    )
    agent = await AgentService(mock_agent_storage).create_agent(
        session,
        test_user.id,
        {
            "name": "MCP agent",
            "type": "custom",
            "actions": ["finalize"],
            "mcpServers": [{"serverId": str(kept.id)}, {"serverId": str(gone.id)}],
        },
    )
    gone_id = gone.id
    await registry.delete(gone_id, test_user.id)

    calls: list[dict] = []

    class Worker:
        async def execute(self, agent_id, node_id, inputs, **kwargs):
            calls.append(kwargs)
            return WorkerResponse(status="completed", outputs={}, action="finalize", iterations=1)

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(executor_module, "async_session_factory", factory)
    pipeline = Pipeline(
        id=f"p-{uuid.uuid4()}",
        name="mcp",
        entry_node_id="A",
        nodes=[
            PipelineNode(
                id="A",
                agent_id=str(agent.id),
                agent_snapshot=AgentSnapshot(
                    agent_id=str(agent.id), name="MCP agent", actions=["finalize"]
                ),
            )
        ],
        edges=[],
    )
    executor = executor_module.PipelineExecutor(worker_client=Worker(), checkpointer=MemorySaver())
    caplog.set_level(logging.WARNING)
    with (
        patch.object(executor_module, "_db_available", AsyncMock(return_value=False)),
        patch.object(executor_module, "ws_publish", new_callable=AsyncMock),
        patch.object(executor_module, "publish_run", new_callable=AsyncMock),
    ):
        await executor.execute(pipeline, owner_id=str(test_user.id))
        active = executor_module.get_active_run(pipeline.id)
        await asyncio.wait_for(active.task, timeout=10)

    assert calls[0]["owner_id"] == str(test_user.id)
    assert calls[0]["mcp_servers"] == [{"serverId": str(kept.id), "tools": kept.discovered_tools}]
    assert any(str(gone_id) in r.getMessage() for r in caplog.records)
    assert not any(r.exc_info for r in caplog.records)
    executor_module.clear_active_runs()
