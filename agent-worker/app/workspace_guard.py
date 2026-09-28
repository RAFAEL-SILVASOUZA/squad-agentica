"""Confina as ferramentas do agente ao workspace do run (spec 14.1)."""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path

WORKSPACES_ROOT = Path(os.environ.get("WORKSPACES_DIR", "/workspaces"))
current_workspace: ContextVar[Path] = ContextVar(
    "current_workspace", default=Path(os.environ.get("AGENT_WORKSPACE", "/tmp/agent-workspace"))
)


class WorkspaceEscapeError(Exception):
    pass


def resolve_in_workspace(raw: str) -> Path:
    base = current_workspace.get().resolve()
    base.mkdir(parents=True, exist_ok=True)
    candidate = Path(raw)
    target = (candidate if candidate.is_absolute() else base / candidate).resolve()
    if target != base and base not in target.parents:
        raise WorkspaceEscapeError(f"caminho fora do workspace: {raw}")
    return target
