"""knowledge document hashes and saved conversations

Revision ID: 3b91c0d4a6e7
Revises: 8225eb7decf0
Create Date: 2026-09-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3b91c0d4a6e7"
down_revision: str | None = "8225eb7decf0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_knowledge_documents_content_hash", "knowledge_documents", ["content_hash"], unique=False
    )
    op.create_unique_constraint(
        "uq_knowledge_documents_kb_hash", "knowledge_documents", ["knowledge_base_id", "content_hash"]
    )
    op.create_table(
        "knowledge_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_bases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_conversations_knowledge_base_id"),
        "knowledge_conversations", ["knowledge_base_id"], unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_conversations_owner_id"), "knowledge_conversations", ["owner_id"], unique=False
    )
    op.create_table(
        "knowledge_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", name="knowledge_message_role", native_enum=False, length=22),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["knowledge_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_messages_conversation_id"), "knowledge_messages", ["conversation_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_messages_conversation_id"), table_name="knowledge_messages")
    op.drop_table("knowledge_messages")
    op.drop_index(op.f("ix_knowledge_conversations_owner_id"), table_name="knowledge_conversations")
    op.drop_index(op.f("ix_knowledge_conversations_knowledge_base_id"), table_name="knowledge_conversations")
    op.drop_table("knowledge_conversations")
    op.drop_constraint("uq_knowledge_documents_kb_hash", "knowledge_documents", type_="unique")
    op.drop_index("ix_knowledge_documents_content_hash", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "content_hash")
