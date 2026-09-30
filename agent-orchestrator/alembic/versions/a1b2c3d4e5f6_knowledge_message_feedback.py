"""knowledge message feedback

Revision ID: a1b2c3d4e5f6
Revises: 8225eb7decf0
Create Date: 2026-09-30 00:00:00.000000

Task 11 (2026-09-29-redesign-usabilidade): coluna ``feedback`` JSONB nullable
em ``knowledge_messages`` para gravar feedback de fonte (wrong: bool, at: str).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: str | None = '7d4f2a9c1e08'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_messages",
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("knowledge_messages", "feedback")
