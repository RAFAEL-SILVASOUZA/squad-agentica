"""git workspace: repositorio no pipeline, PR no run

Revision ID: 8225eb7decf0
Revises: 36713ee2fb69
Create Date: 2026-09-28 00:00:00.000000

Task 4 (2026-09-28-projeto-git-e-usabilidade): colunas novas em ``pipelines``
(repositorio git vinculado) e ``pipeline_runs`` (PR aberto pelo worker).

Decisoes:
- ``pipelines.git_integration_id``: FK para ``integrations.id`` com
  ``ondelete='SET NULL'`` (remover a integracao nao apaga a pipeline).
- ``pipeline_runs.publish_status``: ``String(20)`` simples (nao
  ``sa.Enum(native_enum=False, ...)`` como as demais colunas de estado do
  arquivo) com ``server_default='none'`` — decisao registrada no brief da
  task (interface "none"|"published"|"failed"|"no_changes").
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '8225eb7decf0'
down_revision: str | None = '36713ee2fb69'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "pipelines",
        sa.Column(
            "git_integration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("integrations.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("pipelines", sa.Column("git_repository", sa.String(length=300), nullable=True))
    op.add_column("pipelines", sa.Column("git_base_branch", sa.String(length=200), nullable=True))

    op.add_column("pipeline_runs", sa.Column("pr_url", sa.Text(), nullable=True))
    op.add_column("pipeline_runs", sa.Column("pr_number", sa.Integer(), nullable=True))
    op.add_column(
        "pipeline_runs",
        sa.Column("publish_status", sa.String(length=20), nullable=False, server_default="none"),
    )
    op.add_column("pipeline_runs", sa.Column("publish_error", sa.Text(), nullable=True))


def downgrade() -> None:
    for col in ("publish_error", "publish_status", "pr_number", "pr_url"):
        op.drop_column("pipeline_runs", col)
    for col in ("git_base_branch", "git_repository", "git_integration_id"):
        op.drop_column("pipelines", col)
