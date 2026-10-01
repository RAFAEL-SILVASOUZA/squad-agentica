"""agents.llm (adendo 8: escolha de LLM por agente)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-30

Adendo 8 (2026-09-29-redesign-usabilidade): a tabela ``agents`` ganha a coluna
``llm`` (JSONB, nullable) com a escolha opcional de LLM por agente:
``{integrationId, model}``. O campo ``model`` continua válido; sem ``llm`` vale
o padrão do usuário e, depois, o padrão do ambiente (precedência:
agente > usuário > ambiente). Nullable: agente sem escolha usa o padrão.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("llm", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "llm")
