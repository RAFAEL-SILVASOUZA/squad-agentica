"""Chat conversation state: in-memory draft sessions for agent construction.

Dono: be-agent-chat (FASE 4). Spec 10.1: sessão efêmera (draft) com draftId.
V1: in-memory (single-user). V2: Redis.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    """Uma mensagem no chat."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentDraft:
    """Draft do agente em construção (acumulado ao longo do chat)."""

    draft_id: str
    owner_id: str
    messages: list[ChatMessage] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))
        self.updated_at = time.time()

    def to_llm_messages(self) -> list[dict[str, str]]:
        """Converte as mensagens do chat para o formato OpenAI-style."""
        return [{"role": m.role, "content": m.content} for m in self.messages]


class DraftStore:
    """In-memory store de drafts de chat. Thread-safe."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._drafts: dict[str, AgentDraft] = {}

    def create(self, owner_id: str) -> AgentDraft:
        """Cria um novo draft e retorna."""
        draft_id = str(uuid.uuid4())
        draft = AgentDraft(draft_id=draft_id, owner_id=owner_id)
        with self._lock:
            self._drafts[draft_id] = draft
        return draft

    def get(self, draft_id: str, owner_id: str) -> AgentDraft | None:
        """Busca um draft por id, validando owner.

        Retorna None se não existir ou for de outro owner.
        """
        with self._lock:
            draft = self._drafts.get(draft_id)
            if draft is None:
                return None
            # TTL check.
            if time.time() - draft.updated_at > self._ttl:
                del self._drafts[draft_id]
                return None
            # Owner isolation.
            if draft.owner_id != owner_id:
                return None
            return draft

    def delete(self, draft_id: str) -> None:
        """Remove um draft (após confirmação/salvamento)."""
        with self._lock:
            self._drafts.pop(draft_id, None)

    def cleanup(self) -> None:
        """Remove todos os drafts (para testes)."""
        with self._lock:
            self._drafts.clear()


# Module-level singleton.
draft_store = DraftStore()
