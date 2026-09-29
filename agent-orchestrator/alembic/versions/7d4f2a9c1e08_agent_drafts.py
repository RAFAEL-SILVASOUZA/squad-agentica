"""agent drafts (rascunho persistente do chat de construção)

Revision ID: 7d4f2a9c1e08
Revises: 3b91c0d4a6e7
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7d4f2a9c1e08"
down_revision: str | None = "3b91c0d4a6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("messages", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_drafts_owner_id"), "agent_drafts", ["owner_id"], unique=False)
    # O purge periódico filtra por updated_at.
    op.create_index("ix_agent_drafts_updated_at", "agent_drafts", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_agent_drafts_updated_at", table_name="agent_drafts")
    op.drop_index(op.f("ix_agent_drafts_owner_id"), table_name="agent_drafts")
    op.drop_table("agent_drafts")
