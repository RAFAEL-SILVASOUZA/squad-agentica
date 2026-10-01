"""mcp oauth tables (servidor MCP embutido: OAuth 2.1)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-01

Servidor MCP embutido (Task 1): cria as duas tabelas de suporte ao fluxo
OAuth 2.1 do servidor MCP do portal.

- ``mcp_oauth_clients``: clientes OAuth registrados (client_id público,
  redirect_uris e grant_types em JSONB).
- ``mcp_oauth_tokens``: tokens emitidos (jti como PK, user_id e client_id,
  scope, expires_at, revoked_at).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("client_name", sa.String(length=200), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grant_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", name="uq_mcp_oauth_clients_client_id"),
    )

    op.create_table(
        "mcp_oauth_tokens",
        sa.Column("jti", sa.String(length=200), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("scope", sa.String(length=200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["client_id"], ["mcp_oauth_clients.client_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("jti"),
    )
    op.create_index(op.f("ix_mcp_oauth_tokens_user_id"), "mcp_oauth_tokens", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_oauth_tokens_user_id"), table_name="mcp_oauth_tokens")
    op.drop_table("mcp_oauth_tokens")
    op.drop_table("mcp_oauth_clients")
