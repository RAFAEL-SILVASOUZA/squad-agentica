"""Agent preview: builds a summary of the current draft for the UI.

Dono: be-agent-chat (FASE 4). Spec 10.1: preview do agente (identidade + contrato).
"""

from __future__ import annotations

from typing import Any

from app.agents.chat.conversation import AgentDraft


def build_preview(draft: AgentDraft) -> dict[str, Any]:
    """Builds a preview dict from the draft's current config.

    Returns a dict suitable for the `config_update` SSE event data field.
    Only includes fields that have been set (non-empty).
    """
    config = draft.config
    preview: dict[str, Any] = {}

    if config.get("name"):
        preview["name"] = config["name"]
    if config.get("type"):
        preview["type"] = config["type"]
    if config.get("description"):
        preview["description"] = config["description"]
    if config.get("prompt"):
        preview["prompt"] = config["prompt"]
    if config.get("strategy"):
        preview["strategy"] = config["strategy"]
    if config.get("skills"):
        preview["skills"] = config["skills"]
    if config.get("tools"):
        preview["tools"] = config["tools"]
    if config.get("mcpServers"):
        preview["mcpServers"] = config["mcpServers"]
    if config.get("knowledge"):
        preview["knowledge"] = config["knowledge"]
    if config.get("integrations"):
        preview["integrations"] = config["integrations"]
    if config.get("inputs"):
        preview["inputs"] = config["inputs"]
    if config.get("outputs"):
        preview["outputs"] = config["outputs"]
    if config.get("actions"):
        preview["actions"] = config["actions"]
    if config.get("model"):
        preview["model"] = config["model"]
    if config.get("maxIterations") is not None:
        preview["maxIterations"] = config["maxIterations"]
    if config.get("timeout") is not None:
        preview["timeout"] = config["timeout"]
    if config.get("shellAccess") is not None:
        preview["shellAccess"] = config["shellAccess"]

    return preview
