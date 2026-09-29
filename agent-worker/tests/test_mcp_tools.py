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


def _mock_orchestrator(monkeypatch, response):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: original(transport=httpx.MockTransport(lambda request: response), **kw),
    )


@pytest.mark.asyncio
async def test_mcp_error_message_reaches_llm(monkeypatch):
    _mock_orchestrator(
        monkeypatch,
        httpx.Response(
            502,
            json={"error": "O servidor MCP excedeu o tempo limite.", "code": "mcp_call_failed"},
        ),
    )
    result = await execute_tool("echo", {}, owner_id="o", mcp_routes={"echo": "s"})
    assert result == {"error": "O servidor MCP excedeu o tempo limite."}


@pytest.mark.asyncio
async def test_mcp_error_without_json_body_is_generic(monkeypatch):
    _mock_orchestrator(monkeypatch, httpx.Response(500, text="boom"))
    result = await execute_tool("echo", {}, owner_id="o", mcp_routes={"echo": "s"})
    assert result == {"error": "Não foi possível executar a ferramenta MCP"}


@pytest.mark.asyncio
async def test_mcp_non_dict_content_items(monkeypatch):
    _mock_orchestrator(
        monkeypatch,
        httpx.Response(200, json={"content": ["solto", {"type": "text", "text": "ok"}]}),
    )
    result = await execute_tool("echo", {}, owner_id="o", mcp_routes={"echo": "s"})
    assert result == "[unknown]\nok"


@pytest.mark.asyncio
async def test_loader_custom_tool_collision_uses_definition_name():
    snapshot = snapshot_from_yaml(
        "id: a\n"
        "tools:\n"
        "  - toolId: t1\n"
        "    definition:\n"
        "      name: echo\n"
        "      description: custom\n"
        "mcpServers:\n"
        "  - serverId: s\n"
        "    tools:\n"
        "      - name: echo\n"
        "      - name: other\n"
    )
    capabilities = await WorkerLoader(artifact_client=object()).load(snapshot)
    assert capabilities.mcp_routes == {"other": "s"}
