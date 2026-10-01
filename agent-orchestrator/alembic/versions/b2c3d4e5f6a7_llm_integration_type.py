"""llm integration type (adendo 8: provedores e modelos de LLM nas integrações)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-30

Adendo 8 (2026-09-29-redesign-usabilidade): a tabela ``integrations`` ganha o
tipo ``llm``.

Nota sobre o schema: a coluna ``type`` usa ``Enum(native_enum=False)``. O
SQLAlchemy a materializa como ``VARCHAR(16)`` **sem** constraint de CHECK nem
tipo de enum nativo do Postgres (o conjunto de valores é validado na camada de
aplicação, pelo Pydantic/registry). Por isso não há ``ALTER TYPE ... ADD
VALUE`` a executar: o schema físico não muda.

Esta migration existe para (a) manter a cadeia de revisões coerente com o
model (que agora declara ``llm``) e (b) ser defensiva: se, por qualquer
motivo, existir uma constraint de CHECK na coluna ``type`` (ex.: adicionada
manualmente), ela é recriada incluindo o valor ``llm``. Sem constraint, a
migration é um no-op seguro.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_VALUES = "('github', 'azure', 'gitlab')"
_NEW_VALUES = "('github', 'azure', 'gitlab', 'llm')"


def _find_type_check_constraint(conn) -> str | None:
    """Nome da constraint de CHECK da coluna ``integrations.type`` (se houver).

    O ``Enum(native_enum=False)`` não cria constraint; esta busca é defensiva
    para o caso de uma constraint ter sido adicionada manualmente.
    """
    row = conn.execute(
        sa.text(
            "SELECT con.conname FROM pg_constraint con "
            "JOIN pg_class rel ON rel.oid = con.conrelid "
            "WHERE rel.relname = 'integrations' "
            "AND con.contype = 'c' "
            "AND con.conname LIKE 'integrations_type_%_chk' "
            "ORDER BY con.conname LIMIT 1"
        )
    ).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    constraint = _find_type_check_constraint(conn)
    if constraint is None:
        # Sem constraint de CHECK (caso normal): o schema físico não muda.
        return
    op.execute(f"ALTER TABLE integrations DROP CONSTRAINT {constraint}")
    op.execute(
        f"ALTER TABLE integrations ADD CONSTRAINT {constraint} "
        f"CHECK (type IN {_NEW_VALUES})"
    )


def downgrade() -> None:
    conn = op.get_bind()
    constraint = _find_type_check_constraint(conn)
    if constraint is None:
        return
    op.execute(f"ALTER TABLE integrations DROP CONSTRAINT {constraint}")
    op.execute(
        f"ALTER TABLE integrations ADD CONSTRAINT {constraint} "
        f"CHECK (type IN {_OLD_VALUES})"
    )
