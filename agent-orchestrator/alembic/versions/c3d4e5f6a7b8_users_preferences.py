"""users.preferences (adendo 8: preferências de LLM por usuário)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-30

Adendo 8 (2026-09-29-redesign-usabilidade): a tabela ``users`` ganha a coluna
``preferences`` (JSONB, nullable). Ela guarda as escolhas padrão do usuário:
``default_llm_integration_id`` e ``default_embedding_integration_id`` (UUIDs de
integrações tipo ``llm``). Nullable: usuário sem preferências usa o padrão do
ambiente.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: str | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "preferences")
