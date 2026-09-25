"""Tests for base agent class and built-in types (D4 4.3, 4.4).

Cobre: Agent.run com mock LLM, built-ins com prompt default não-vazio,
output estruturado.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from app.agents.base import (
    DEPLOYER_PROMPT,
    DEVELOPER_PROMPT,
    PLANNER_PROMPT,
    REVIEWER_PROMPT,
    Agent,
    AgentCapabilities,
    AgentSnapshot,
    DeployerAgent,
    DeveloperAgent,
    PlannerAgent,
    ReviewerAgent,
    create_agent_from_snapshot,
)


def _make_snapshot(
    agent_type: str = "planner",
    prompt: str = "",
    strategy: str = "Step by step",
    outputs: list[dict] | None = None,
    actions: list[str] | None = None,
) -> AgentSnapshot:
    return AgentSnapshot(
        id="test-agent-id",
        name="Test Agent",
        type=agent_type,
        description="A test agent",
        prompt=prompt,
        strategy=strategy,
        model="gpt-4o",
        max_iterations=5,
        timeout=60,
        shell_access=False,
        inputs=[{"name": "input_data", "type": "document", "required": True}],
        outputs=outputs or [{"name": "result", "type": "document", "required": False}],
        actions=actions or ["follow", "finalize"],
    )


class TestAgentBase:
    async def test_run_returns_structured_output(self):
        """Agent.run com mock LLM devolve output estruturado."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=json.dumps({"result": "Hello world", "_action": "follow"})
        )

        snapshot = _make_snapshot()
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="You are helpful.")

        output = await agent.run({"input_data": "some data"}, capabilities)
        assert output["result"] == "Hello world"
        assert output["_action"] == "follow"
        mock_llm.chat.assert_called_once()

    async def test_run_with_non_json_response(self):
        """Se o LLM não retorna JSON, o texto vai na primeira output."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value="This is plain text, not JSON.")

        snapshot = _make_snapshot()
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="test")

        output = await agent.run({"input_data": "data"}, capabilities)
        assert output["result"] == "This is plain text, not JSON."
        assert output["_action"] == "follow"  # default from actions[0]

    async def test_run_with_json_in_markdown(self):
        """Extrai JSON de bloco markdown."""
        mock_llm = AsyncMock()
        json_block = '```json\n{"result": "parsed", "_action": "finalize"}\n```'
        mock_llm.chat = AsyncMock(
            return_value=f"Here is the result:\n{json_block}"
        )

        snapshot = _make_snapshot()
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="test")

        output = await agent.run({"input_data": "data"}, capabilities)
        assert output["result"] == "parsed"
        assert output["_action"] == "finalize"

    async def test_system_prompt_includes_strategy(self):
        """O system prompt inclui a strategy do snapshot."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"result": "ok", "_action": "follow"}')

        snapshot = _make_snapshot(strategy="First do X, then do Y.")
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="Base prompt.")

        await agent.run({}, capabilities)

        # Check the system prompt passed to LLM.
        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        assert "First do X, then do Y." in system_msg

    async def test_system_prompt_includes_knowledge(self):
        """O system prompt inclui knowledge context."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"result": "ok", "_action": "follow"}')

        snapshot = _make_snapshot()
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(
            system_prompt="Base.",
            knowledge_context=["Fact 1", "Fact 2"],
        )

        await agent.run({}, capabilities)

        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        system_msg = messages[0]["content"]
        assert "Fact 1" in system_msg
        assert "Fact 2" in system_msg

    async def test_user_message_contains_inputs(self):
        """A mensagem de usuário contém os inputs."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(return_value='{"result": "ok", "_action": "follow"}')

        snapshot = _make_snapshot()
        agent = Agent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="test")

        await agent.run({"input_data": "my input value"}, capabilities)

        call_args = mock_llm.chat.call_args
        messages = call_args[0][0]
        user_msg = messages[1]["content"]
        assert "my input value" in user_msg


class TestBuiltInAgents:
    def test_planner_has_default_prompt(self):
        snapshot = _make_snapshot(agent_type="planner", prompt="")
        agent = PlannerAgent(snapshot)
        assert agent.snapshot.prompt == PLANNER_PROMPT
        assert len(PLANNER_PROMPT) > 10

    def test_developer_has_default_prompt(self):
        snapshot = _make_snapshot(agent_type="developer", prompt="")
        agent = DeveloperAgent(snapshot)
        assert agent.snapshot.prompt == DEVELOPER_PROMPT
        assert len(DEVELOPER_PROMPT) > 10

    def test_reviewer_has_default_prompt(self):
        snapshot = _make_snapshot(agent_type="reviewer", prompt="")
        agent = ReviewerAgent(snapshot)
        assert agent.snapshot.prompt == REVIEWER_PROMPT
        assert len(REVIEWER_PROMPT) > 10

    def test_deployer_has_default_prompt(self):
        snapshot = _make_snapshot(agent_type="deployer", prompt="")
        agent = DeployerAgent(snapshot)
        assert agent.snapshot.prompt == DEPLOYER_PROMPT
        assert len(DEPLOYER_PROMPT) > 10

    def test_custom_prompt_not_overridden(self):
        """Se o snapshot já tem prompt, o built-in não sobrescreve."""
        snapshot = _make_snapshot(agent_type="planner", prompt="My custom prompt")
        agent = PlannerAgent(snapshot)
        assert agent.snapshot.prompt == "My custom prompt"

    async def test_planner_executes_via_base_run(self):
        """Planner executa via base.run e retorna output estruturado."""
        mock_llm = AsyncMock()
        mock_llm.chat = AsyncMock(
            return_value=json.dumps({"plan": "Step 1, Step 2", "_action": "follow"})
        )
        snapshot = _make_snapshot(agent_type="planner")
        agent = PlannerAgent(snapshot, llm=mock_llm)
        capabilities = AgentCapabilities(system_prompt="")

        output = await agent.run({"input_data": "Build a house"}, capabilities)
        assert output["plan"] == "Step 1, Step 2"
        assert output["_action"] == "follow"


class TestFactory:
    def test_create_planner(self):
        snapshot = _make_snapshot(agent_type="planner")
        agent = create_agent_from_snapshot(snapshot)
        assert isinstance(agent, PlannerAgent)

    def test_create_developer(self):
        snapshot = _make_snapshot(agent_type="developer")
        agent = create_agent_from_snapshot(snapshot)
        assert isinstance(agent, DeveloperAgent)

    def test_create_reviewer(self):
        snapshot = _make_snapshot(agent_type="reviewer")
        agent = create_agent_from_snapshot(snapshot)
        assert isinstance(agent, ReviewerAgent)

    def test_create_deployer(self):
        snapshot = _make_snapshot(agent_type="deployer")
        agent = create_agent_from_snapshot(snapshot)
        assert isinstance(agent, DeployerAgent)

    def test_create_unknown_type_falls_back_to_base(self):
        snapshot = _make_snapshot(agent_type="custom_type")
        agent = create_agent_from_snapshot(snapshot)
        assert isinstance(agent, Agent)
        assert not isinstance(agent, PlannerAgent)
