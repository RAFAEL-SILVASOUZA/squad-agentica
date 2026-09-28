import json

import httpx
import pytest

from app.worker import WorkerLoader, execute_tool, snapshot_from_yaml


@pytest.mark.asyncio
async def test_mcp_dispatch(monkeypatch):
    def handle(request):
        assert str(request.url) == "http://orchestrator:8000/internal/mcp/server-1/call"
        assert request.headers["X-Worker-Token"] == "test-token"
        assert json.loads(request.content) == {
            "ownerId": "owner-1",
            "tool": "echo",
            "arguments": {"text": "Oi"},
        }
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "Oi"}, {"type": "image"}], "isError": False},
        )

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(handle), **kw)
    )
    monkeypatch.setenv("WORKER_TOKEN", "test-token")
    result = await execute_tool(
        "echo", {"text": "Oi"}, owner_id="owner-1", mcp_routes={"echo": "server-1"}
    )
    assert result == "Oi\n[image]"


@pytest.mark.asyncio
async def test_loader_native_collision(caplog):
    snapshot = snapshot_from_yaml(
        "id: a\n"
        "mcpServers:\n"
        "  - serverId: s\n"
        "    tools:\n"
        "      - name: read_file\n"
        "      - name: echo\n"
    )
    loader = WorkerLoader(artifact_client=object())
    capabilities = await loader.load(snapshot)
    assert [t["name"] for t in capabilities.mcp_tools] == ["echo"]
    assert capabilities.mcp_routes == {"echo": "s"}
    assert "read_file" in caplog.text
