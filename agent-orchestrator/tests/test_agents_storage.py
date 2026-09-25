"""Tests for agent storage round-trip (D4 4.7).

Cobre: save_agent + get_agent round-trip retorna o mesmo conteúdo;
delete_agent remove o objeto.
"""

from __future__ import annotations

import pytest


class MockAgentStorage:
    """In-memory mock para testar o contrato de storage."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def save_agent(self, agent_id: str, agent_yaml: str) -> None:
        self.store[agent_id] = agent_yaml

    async def get_agent(self, agent_id: str) -> str:
        if agent_id not in self.store:
            raise FileNotFoundError(f"Agent {agent_id} not found")
        return self.store[agent_id]

    async def delete_agent(self, agent_id: str) -> None:
        self.store.pop(agent_id, None)


class TestStorageRoundTrip:
    async def test_save_and_get_round_trip(self):
        storage = MockAgentStorage()
        yaml_content = "name: Test Agent\ntype: planner\nprompt: Hello"

        await storage.save_agent("agent-123", yaml_content)
        result = await storage.get_agent("agent-123")
        assert result == yaml_content

    async def test_delete_removes_object(self):
        storage = MockAgentStorage()
        await storage.save_agent("agent-456", "name: X")

        await storage.delete_agent("agent-456")
        with pytest.raises(FileNotFoundError):
            await storage.get_agent("agent-456")

    async def test_get_nonexistent_raises(self):
        storage = MockAgentStorage()
        with pytest.raises(FileNotFoundError):
            await storage.get_agent("nonexistent")

    async def test_overwrite_existing(self):
        storage = MockAgentStorage()
        await storage.save_agent("agent-789", "version: 1")
        await storage.save_agent("agent-789", "version: 2")

        result = await storage.get_agent("agent-789")
        assert result == "version: 2"


class TestYamlSerialization:
    """Testa a serialização/deserialização do artefato .yml."""

    async def test_agent_to_yaml_and_back(self):
        import uuid

        from app.agents.service import agent_to_yaml, yaml_to_agent_data
        from app.db.models import Agent

        agent = Agent(
            id=uuid.uuid4(),
            owner_id=uuid.uuid4(),
            name="Test",
            type="planner",
            description="desc",
            prompt="prompt",
            strategy="strategy",
            skills=[{"skillId": "s1", "config": {}}],
            tools=[],
            mcp_servers=[],
            knowledge=[],
            integrations=[],
            inputs=[{"name": "in", "type": "document", "required": True}],
            outputs=[{"name": "out", "type": "code", "required": False}],
            actions=["follow"],
            model="gpt-4o",
            max_iterations=5,
            timeout=120,
            shell_access=False,
        )

        yaml_str = agent_to_yaml(agent)
        data = yaml_to_agent_data(yaml_str)

        assert data["name"] == "Test"
        assert data["type"] == "planner"
        assert data["prompt"] == "prompt"
        assert data["maxIterations"] == 5
        assert data["timeout"] == 120
        assert data["shellAccess"] is False
        assert data["inputs"] == [{"name": "in", "type": "document", "required": True}]
        assert data["actions"] == ["follow"]
