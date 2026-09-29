"""Chat conversation state: persistent draft sessions for agent construction.

Dono: be-agent-chat (FASE 4). Spec 10.1: sessão do draft com draftId.
V1 era in-memory; a partir da Task 3 (redesign de usabilidade) o draft é
persistido no banco (tabela ``agent_drafts``): sobrevive a restart do
processo e pode ser restaurado a partir da config da tela (rota restore).

Isolamento por dono: ``get`` valida o owner; draft alheio retorna None
(a rota responde 404 ``draft_not_found``, nunca a config de outro usuário).

TTL de 24h: ``purge_expired_drafts`` roda no loop periódico de ``main.py``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentDraft as AgentDraftRow


@dataclass
class ChatMessage:
    """Uma mensagem no chat."""

    role: str  # "user" | "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AgentDraft:
    """Draft do agente em construção (acumulado ao longo do chat).

    Objeto em memória espelhado na tabela ``agent_drafts``. O id é o
    ``draftId`` exposto na API.
    """

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

    @classmethod
    def from_row(cls, row: AgentDraftRow) -> AgentDraft:
        """Hidrata o draft em memória a partir da linha do banco."""
        messages = [
            ChatMessage(
                role=m.get("role", "user"),
                content=m.get("content", ""),
                timestamp=float(m.get("timestamp") or 0.0),
            )
            for m in (row.messages or [])
            if isinstance(m, dict)
        ]
        return cls(
            draft_id=str(row.id),
            owner_id=str(row.owner_id),
            messages=messages,
            config=dict(row.config or {}),
        )


# TTL do rascunho: 24h (ruling da Task 3).
DRAFT_TTL_HOURS = 24


async def purge_expired_drafts(db: AsyncSession, ttl_hours: int = DRAFT_TTL_HOURS) -> int:
    """Remove drafts com ``updated_at`` mais antigo que o TTL.

    Roda no loop periódico de ``main.py``. Retorna quantas linhas removeu.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=ttl_hours)
    result = await db.execute(
        delete(AgentDraftRow).where(AgentDraftRow.updated_at < cutoff)
    )
    await db.commit()
    return int(result.rowcount or 0)


class DraftStore:
    """Store assíncrono de drafts de chat, apoiado no banco (agent_drafts)."""

    async def create(
        self, db: AsyncSession, owner_id: str, config: dict[str, Any] | None = None
    ) -> AgentDraft:
        """Cria um novo draft no banco e retorna o objeto em memória."""
        row = AgentDraftRow(
            id=uuid.uuid4(),
            owner_id=uuid.UUID(owner_id),
            messages=[],
            config=config or {},
        )
        db.add(row)
        await db.flush()
        return AgentDraft.from_row(row)

    async def get(
        self, db: AsyncSession, draft_id: str, owner_id: str
    ) -> AgentDraft | None:
        """Busca um draft por id, validando o dono.

        Retorna None se não existir ou for de outro owner (isolamento:
        a rota responde 404, nunca a config de outro usuário).
        """
        try:
            uid = uuid.UUID(draft_id)
            oid = uuid.UUID(owner_id)
        except (ValueError, TypeError, AttributeError):
            return None
        row = (
            await db.execute(
                select(AgentDraftRow).where(
                    AgentDraftRow.id == uid,
                    AgentDraftRow.owner_id == oid,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        return AgentDraft.from_row(row)

    async def save(self, db: AsyncSession, draft: AgentDraft) -> None:
        """Persiste o estado atual do draft (messages + config).

        Toca ``updated_at`` (renova o TTL).
        """
        await db.execute(
            update(AgentDraftRow)
            .where(
                AgentDraftRow.id == uuid.UUID(draft.draft_id),
                AgentDraftRow.owner_id == uuid.UUID(draft.owner_id),
            )
            .values(
                messages=[m.__dict__ for m in draft.messages],
                config=dict(draft.config),
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()

    async def delete(self, db: AsyncSession, draft_id: str) -> None:
        """Remove um draft (após confirmação/salvamento)."""
        try:
            uid = uuid.UUID(draft_id)
        except (ValueError, TypeError):
            return
        await db.execute(delete(AgentDraftRow).where(AgentDraftRow.id == uid))
        await db.commit()


# Module-level singleton (stateless: o estado vive no banco).
draft_store = DraftStore()
