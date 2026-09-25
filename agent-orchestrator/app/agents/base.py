"""Base agent class: receives AgentSnapshot + AgentCapabilities, calls LLM, returns output.

Dono: be-agents (FASE 4). Contrato de execução (spec 6.6, D4 4.3):
- `async def run(self, inputs: dict, capabilities: AgentCapabilities) -> dict`
- O `base.py` NÃO lê capabilities do snapshot. Recebe como parâmetro de `run()`.
- O worker (D6) baixa o .yml do agente do Garage e instancia a classe correta.
- Sem lógica de execução real aqui: monta prompt, chama LLM, retorna output.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from app.core.llm import LLMClient, get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class AgentSnapshot:
    """Snapshot do agente (dados do .yml / Postgres, spec 4.1).

    Inclui os campos de referência de capacidades (mochila) que o loader
    (D8) resolve em runtime para montar o ``AgentCapabilities``.
    """

    id: str
    name: str
    type: str
    description: str
    prompt: str
    strategy: str
    model: str
    max_iterations: int
    timeout: int
    shell_access: bool
    # Capacidades (mochila) — spec 4.1 / 6.6.
    skills: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    integrations: list[dict[str, Any]] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class AgentCapabilities:
    """Capacidades derivadas em runtime (spec 6.6).

    Montado pelo loader (D8/pe-loader) e passado como parâmetro de `run()`.
    """

    system_prompt: str
    tools: list[dict[str, Any]] = field(default_factory=list)
    mcp_tools: list[dict[str, Any]] = field(default_factory=list)
    knowledge_context: list[str] = field(default_factory=list)


class Agent:
    """Classe base do agente.

    Recebe um `AgentSnapshot` (definição persistida) e, em `run()`,
    um `AgentCapabilities` (capacidades derivadas em runtime).
    Monta o prompt, chama o LLM e retorna output estruturado.
    """

    def __init__(self, snapshot: AgentSnapshot, llm: LLMClient | None = None) -> None:
        self.snapshot = snapshot
        self._llm = llm or get_llm_client()

    async def run(self, inputs: dict[str, Any], capabilities: AgentCapabilities) -> dict[str, Any]:
        """Executa o agente: monta prompt, chama LLM, retorna output.

        Args:
            inputs: dados de entrada (chaves correspondem aos `inputs` do snapshot).
            capabilities: capacidades derivadas (system_prompt com skills injetadas,
                tools, mcp_tools, knowledge_context).

        Returns:
            dict com as chaves correspondentes aos `outputs` do snapshot +
            a chave `_action` com a action escolhida (follow/return/finalize).
        """
        # Build the user message from inputs.
        user_message = self._build_user_message(inputs)

        # Build the system prompt: base prompt + strategy + capabilities.
        system_prompt = self._build_system_prompt(capabilities)

        # Call the LLM.
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        response_text = await self._llm.chat(messages, model=self.snapshot.model)

        # Parse the response into structured output.
        output = self._parse_output(response_text)

        return output

    def _build_user_message(self, inputs: dict[str, Any]) -> str:
        """Monta a mensagem de usuário a partir dos inputs."""
        if not inputs:
            return "Execute your task."

        parts: list[str] = []
        for key, value in inputs.items():
            if isinstance(value, str):
                parts.append(f"## {key}\n{value}")
            else:
                parts.append(f"## {key}\n{json.dumps(value, ensure_ascii=False, indent=2)}")
        return "\n\n".join(parts)

    def _build_system_prompt(self, capabilities: AgentCapabilities) -> str:
        """Monta o system prompt completo: base + strategy + knowledge."""
        parts: list[str] = []

        # Base system prompt (already includes skills injected by the loader).
        if capabilities.system_prompt:
            parts.append(capabilities.system_prompt)
        elif self.snapshot.prompt:
            parts.append(self.snapshot.prompt)

        # Strategy.
        if self.snapshot.strategy:
            parts.append(f"\n## Strategy\n{self.snapshot.strategy}")

        # Knowledge context.
        if capabilities.knowledge_context:
            knowledge_block = "\n\n".join(capabilities.knowledge_context)
            parts.append(f"\n## Knowledge Context\n{knowledge_block}")

        # Output contract reminder.
        if self.snapshot.outputs:
            output_names = ", ".join(o.get("name", "?") for o in self.snapshot.outputs)
            action_list = ", ".join(self.snapshot.actions) or "follow"
            parts.append(
                f"\n## Output Contract\n"
                f"Respond with a JSON object containing these keys: {output_names}. "
                f"Also include a '_action' key with one of: {action_list}."
            )

        return "\n".join(parts)

    def _parse_output(self, response_text: str) -> dict[str, Any]:
        """Tenta parsear a resposta do LLM como JSON estruturado.

        Se não for JSON válido, retorna o texto bruto na primeira output
        declarada + action default.
        """
        try:
            # Try to parse as JSON directly.
            result = json.loads(response_text)
            if isinstance(result, dict):
                return result
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to extract JSON from markdown code blocks.
        import re

        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

        # Fallback: put the raw text in the first output field.
        fallback: dict[str, Any] = {}
        if self.snapshot.outputs:
            first_output_name = self.snapshot.outputs[0].get("name", "output")
            fallback[first_output_name] = response_text
        else:
            fallback["output"] = response_text

        # Default action.
        if "_action" not in fallback:
            fallback["_action"] = self.snapshot.actions[0] if self.snapshot.actions else "follow"

        return fallback


# ---------------------------------------------------------------------------
# Built-in agent types (spec 4.1: templates, not restrictions)
# ---------------------------------------------------------------------------

PLANNER_PROMPT = (
    "You are a planning agent. Your role is to analyze requirements and produce "
    "a detailed, actionable plan. Break down complex tasks into sequential steps, "
    "identify dependencies, and define clear acceptance criteria for each step. "
    "Output should be structured and specific."
)

DEVELOPER_PROMPT = (
    "You are a development agent. Your role is to write, modify, and debug code. "
    "Follow best practices, write clean and well-documented code, and ensure "
    "your changes are minimal and focused. Always consider edge cases and error handling."
)

REVIEWER_PROMPT = (
    "You are a code review agent. Your role is to review code changes for correctness, "
    "security, performance, and maintainability. Provide specific, actionable feedback. "
    "Identify bugs, security vulnerabilities, and style issues. Be constructive and precise."
)

DEPLOYER_PROMPT = (
    "You are a deployment agent. Your role is to manage deployments, configure "
    "infrastructure, and ensure releases are safe and reversible. Verify pre-conditions, "
    "execute deployment steps, and confirm post-deployment health checks."
)


class PlannerAgent(Agent):
    """Agente de planejamento (template built-in)."""

    def __init__(self, snapshot: AgentSnapshot, llm: LLMClient | None = None) -> None:
        if not snapshot.prompt:
            snapshot.prompt = PLANNER_PROMPT
        super().__init__(snapshot, llm)


class DeveloperAgent(Agent):
    """Agente de desenvolvimento (template built-in)."""

    def __init__(self, snapshot: AgentSnapshot, llm: LLMClient | None = None) -> None:
        if not snapshot.prompt:
            snapshot.prompt = DEVELOPER_PROMPT
        super().__init__(snapshot, llm)


class ReviewerAgent(Agent):
    """Agente de revisão (template built-in)."""

    def __init__(self, snapshot: AgentSnapshot, llm: LLMClient | None = None) -> None:
        if not snapshot.prompt:
            snapshot.prompt = REVIEWER_PROMPT
        super().__init__(snapshot, llm)


class DeployerAgent(Agent):
    """Agente de deploy (template built-in)."""

    def __init__(self, snapshot: AgentSnapshot, llm: LLMClient | None = None) -> None:
        if not snapshot.prompt:
            snapshot.prompt = DEPLOYER_PROMPT
        super().__init__(snapshot, llm)


# Registry: type name -> class.
AGENT_TYPES: dict[str, type[Agent]] = {
    "planner": PlannerAgent,
    "developer": DeveloperAgent,
    "reviewer": ReviewerAgent,
    "deployer": DeployerAgent,
}


def create_agent_from_snapshot(snapshot: AgentSnapshot, llm: LLMClient | None = None) -> Agent:
    """Fábrica: instancia a classe correta baseada no type do snapshot."""
    agent_class = AGENT_TYPES.get(snapshot.type, Agent)
    return agent_class(snapshot, llm)
