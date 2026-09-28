import uuid

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
@pytest.mark.parametrize("path", ["../outside.xlsx", "/etc/passwd", "link/book.xlsx"])
async def test_excel_path_confined_to_run(
    full_app, session, test_user, tmp_path, monkeypatch, path
):
    from app.api.internal_mcp import router

    full_app.include_router(router)
    root = tmp_path / "workspaces"
    workspace = root / "run-1"
    workspace.mkdir(parents=True)
    (workspace / "link").symlink_to(tmp_path, target_is_directory=True)
    monkeypatch.setattr(settings, "workspaces_dir", str(root))
    server = await MCPRegistry(session).create(
        owner_id=test_user.id,
        name="Excel",
        description="",
        transport="stdio",
        command="npx -y @negokaz/excel-mcp-server",
    )
    async with AsyncClient(transport=ASGITransport(app=full_app), base_url="http://test") as client:
        response = await client.post(
            f"/internal/mcp/{server.id}/call",
            headers={"X-Worker-Token": settings.worker_token},
            json={
                "ownerId": str(test_user.id),
                "tool": "excel_read_sheet",
                "arguments": {"fileAbsolutePath": path},
                "workspaceDir": str(workspace),
            },
        )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_mcp_path"


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


@pytest.mark.asyncio
async def test_dispatch_materializes_legacy_refs(
    session, test_user, mock_agent_storage, monkeypatch
):
    import json
    from contextlib import asynccontextmanager

    import httpx

    import app.runtime.worker_client as worker_client_module
    from app.agents.service import AgentService
    from tests.test_rt_worker_client import _make_client

    server = await MCPRegistry(session).create(
        owner_id=test_user.id, name="Legacy", description="", transport="stdio", command="echo"
    )
    agent = await AgentService(mock_agent_storage).create_agent(
        session,
        test_user.id,
        {
            "name": "Legacy",
            "type": "custom",
            "actions": ["finalize"],
            "mcpServers": [{"serverId": str(server.id)}],
        },
    )
    server.discovered_tools = [{"name": "echo", "description": "New discovery", "inputSchema": {}}]
    await session.commit()

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr(worker_client_module, "async_session_factory", factory)

    def handle(request):
        body = json.loads(request.content)
        assert body["ownerId"] == str(test_user.id)
        assert body["mcpServers"] == [
            {"serverId": str(server.id), "tools": server.discovered_tools}
        ]
        return httpx.Response(
            200, json={"status": "completed", "outputs": {}, "action": "finalize"}
        )

    client = _make_client(handle)
    result = await client.execute(str(agent.id), "n", {}, owner_id=str(test_user.id))
    assert result.status == "completed"
