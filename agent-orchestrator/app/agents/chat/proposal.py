"""Agent proposal: builds the system prompt and parses LLM responses into config updates.

Dono: be-agent-chat (FASE 4). Spec 10.2: a IA entende intenção, sugere
skills/knowledge/integrações, define contrato, gera prompt, valida coerência.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agents.chat.conversation import AgentDraft
from app.agents.validator import validate_agent_contract

# System prompt for the construction assistant.
CONSTRUCTION_SYSTEM_PROMPT = """\
You are an agent construction assistant. Your role is to help the user
define a new agent or edit an existing one.

You MUST respond with a JSON object (no markdown, no code fences) with
these fields:
- "text": string — your conversational reply to the user (in Portuguese).
- "config": object — the updated agent configuration. Include ONLY the
  fields that changed or are now known. Valid fields:
  - "name": string (agent name)
  - "type": string (e.g. "planner", "developer", "reviewer", "deployer")
  - "description": string
  - "prompt": string (the agent's system prompt)
  - "strategy": string
  - "skills": array of objects with "id" and "name"
  - "tools": array of objects with "id" and "name"
  - "mcpServers": array of objects with "id" and "name"
  - "knowledge": array of objects with "id" and "name"
  - "integrations": array of objects with "id" and "name"
  - "inputs": array of PortDef objects:
    {"name": str, "type": "document"|"code"|"artifact"|"signal",
     "required": bool}
  - "outputs": array of PortDef objects:
    {"name": str, "type": "document"|"code"|"artifact"|"signal",
     "required": bool}
  - "actions": array of strings from ["follow", "return", "finalize"]
  - "model": string (e.g. "gpt-4o")
  - "maxIterations": integer
  - "timeout": integer (seconds)
  - "shellAccess": boolean

Rules:
- Port types MUST be one of: document, code, artifact, signal.
- Actions MUST be one of: follow, return, finalize.
- Port names must be unique within inputs and within outputs.
- Always include "text" in your response.
- If the user's message is a question or clarification, you may return an empty "config" object.
- Respond in Portuguese in the "text" field.
"""

EDIT_SYSTEM_PROMPT = """\
You are an agent editing assistant. The user wants to modify an existing
agent.

Current agent configuration:
{current_config}

You MUST respond with a JSON object (no markdown, no code fences) with
these fields:
- "text": string — your conversational reply to the user (in Portuguese).
- "config": object — the FULL updated agent configuration (all fields,
  not just changed ones).

Valid fields:
  - "name": string
  - "type": string
  - "description": string
  - "prompt": string
  - "strategy": string
  - "skills": array of objects with "id" and "name"
  - "tools": array of objects with "id" and "name"
  - "mcpServers": array of objects with "id" and "name"
  - "knowledge": array of objects with "id" and "name"
  - "integrations": array of objects with "id" and "name"
  - "inputs": array of PortDef objects:
    {{"name": str, "type": "document"|"code"|"artifact"|"signal",
     "required": bool}}
  - "outputs": array of PortDef objects:
    {{"name": str, "type": "document"|"code"|"artifact"|"signal",
     "required": bool}}
  - "actions": array of strings from ["follow", "return", "finalize"]
  - "model": string
  - "maxIterations": integer
  - "timeout": integer
  - "shellAccess": boolean

Rules:
- Port types MUST be one of: document, code, artifact, signal.
- Actions MUST be one of: follow, return, finalize.
- Always include "text" in your response.
- Respond in Portuguese in the "text" field.
"""


def build_system_prompt(mode: str, current_config: dict[str, Any] | None = None) -> str:
    """Builds the system prompt based on mode (create or edit)."""
    if mode == "edit" and current_config:
        config_json = json.dumps(current_config, ensure_ascii=False, indent=2)
        return EDIT_SYSTEM_PROMPT.format(current_config=config_json)
    return CONSTRUCTION_SYSTEM_PROMPT


def parse_llm_response(raw: str) -> tuple[str, dict[str, Any]]:
    """Parses the LLM response into (text, config).

    Handles:
    - Pure JSON
    - JSON wrapped in markdown code fences
    - Fallback: entire text as "text", empty config
    """
    # Try direct JSON parse.
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            text = data.get("text", "")
            config = data.get("config", {})
            if not isinstance(config, dict):
                config = {}
            return text, config
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract JSON from markdown code blocks.
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            if isinstance(data, dict):
                text = data.get("text", "")
                config = data.get("config", {})
                if not isinstance(config, dict):
                    config = {}
                return text, config
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: treat entire response as text.
    return raw.strip(), {}


def validate_config(config: dict[str, Any]) -> list[str]:
    """Validates the config's contract (inputs/outputs/actions). Returns list of error messages."""
    inputs = config.get("inputs", [])
    outputs = config.get("outputs", [])
    actions = config.get("actions", [])
    result = validate_agent_contract(inputs, outputs, actions)
    if result.valid:
        return []
    return [e.message for e in result.errors]


def merge_config(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merges a partial config update into the base config.

    For list fields (skills, tools, etc.), the update replaces the base.
    For scalar fields, the update overrides the base.
    """
    merged = dict(base)
    for key, value in update.items():
        if value is not None:
            merged[key] = value
    return merged


def draft_to_agent_data(draft: AgentDraft) -> dict[str, Any]:
    """Converts the draft config to the data dict for AgentService."""
    config = draft.config
    data: dict[str, Any] = {
        "name": config.get("name", "Unnamed Agent"),
        "type": config.get("type", "custom"),
        "description": config.get("description", ""),
        "prompt": config.get("prompt", ""),
        "strategy": config.get("strategy", ""),
        "skills": config.get("skills", []),
        "tools": config.get("tools", []),
        "mcpServers": config.get("mcpServers", []),
        "knowledge": config.get("knowledge", []),
        "integrations": config.get("integrations", []),
        "inputs": config.get("inputs", []),
        "outputs": config.get("outputs", []),
        "actions": config.get("actions", []),
        "model": config.get("model", "gpt-4o"),
        "maxIterations": config.get("maxIterations", 10),
        "timeout": config.get("timeout", 300),
        "shellAccess": config.get("shellAccess", False),
    }
    return data
