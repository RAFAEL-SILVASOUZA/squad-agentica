"""mcp oauth codes table (código de autorização OAuth 2.1)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-02

Servidor MCP embutido (Task 4): cria a tabela de códigos de autorização
OAuth 2.1 (uso único, expira em 5 minutos).

- ``mcp_oauth_codes``: código de autorização gerado no consent, trocado
  por tokens no token endpoint. code (uuid4 string) é a PK. used_at
  marca o uso (single-use).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_oauth_codes",
        sa.Column("code", sa.String(length=200), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", sa.String(length=200), nullable=False),
        sa.Column("redirect_uri", sa.String(length=500), nullable=False),
        sa.Column("code_challenge", sa.String(length=500), nullable=False),
        sa.Column(
            "code_challenge_method",
            sa.String(length=10),
            nullable=False,
            server_default="S256",
        ),
        sa.Column("scope", sa.String(length=200), nullable=False, server_default="mcp:full"),
        sa.Column("resource", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["client_id"], ["mcp_oauth_clients.client_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    op.create_index(
        op.f("ix_mcp_oauth_codes_user_id"),
        "mcp_oauth_codes",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_oauth_codes_user_id"), table_name="mcp_oauth_codes")
    op.drop_table("mcp_oauth_codes")
