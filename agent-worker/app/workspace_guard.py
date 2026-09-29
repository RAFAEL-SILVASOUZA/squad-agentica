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


def _is_run_workspace(base: Path) -> bool:
    """True se ``base`` é o workspace de um run (dentro de WORKSPACES_DIR)."""
    return WORKSPACES_ROOT.resolve() in base.parents


def ensure_workspace() -> Path:
    """Workspace atual, resolvido.

    Workspace de run (dentro de WORKSPACES_DIR) é criado pelo orchestrator; se
    ele não existe (expirou/foi removido), o worker NÃO o recria — recriar
    daria um diretório vazio que o run "publicaria" como se fosse o resultado.
    O workspace padrão (fora de WORKSPACES_DIR, sem run) continua sendo criado.
    """
    base = current_workspace.get().resolve()
    if _is_run_workspace(base):
        if not base.is_dir():
            raise WorkspaceEscapeError(
                "o workspace deste run não existe mais (expirou ou foi removido)"
            )
    else:
        base.mkdir(parents=True, exist_ok=True)
    return base


def resolve_in_workspace(raw: str) -> Path:
    base = ensure_workspace()
    # Caminho malformado (byte nulo, None, não-string) vira erro de ferramenta
    # em vez de derrubar a execução do agente.
    try:
        candidate = Path(raw)
        target = (candidate if candidate.is_absolute() else base / candidate).resolve()
    except (ValueError, TypeError, OSError):
        raise WorkspaceEscapeError(f"caminho inválido: {raw!r}") from None
    if target != base and base not in target.parents:
        raise WorkspaceEscapeError(f"caminho fora do workspace: {raw}")
    # Revisão final C1: nenhum segmento ``.git`` — o repositório do run é do
    # orchestrator; um ``.git/config`` escrito pelo agente seria configuração
    # (hooks, fsmonitor, drivers) de um git alheio.
    if ".git" in target.relative_to(base).parts or ".git" in Path(str(raw)).parts:
        raise WorkspaceEscapeError(
            f"caminho não permitido: {raw} (diretórios .git são reservados ao sistema)"
        )
    return target
