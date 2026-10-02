"""Remove a identidade duplicada de core.tb_sistema.

Revision ID: 20260917_0007
Revises: 20260917_0006
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260917_0007"
down_revision = "20260917_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Mantem id_sistema como unica identidade persistida do sistema."""

    op.drop_constraint(
        "uq_core_sistema_identificador_aplicacao",
        "tb_sistema",
        schema="core",
        type_="unique",
    )
    op.drop_column("tb_sistema", "identificador_aplicacao", schema="core")


def downgrade() -> None:
    """Recria a coluna apenas para permitir rollback tecnico controlado."""

    op.add_column(
        "tb_sistema",
        sa.Column("identificador_aplicacao", sa.String(80), nullable=True),
        schema="core",
    )
    op.create_unique_constraint(
        "uq_core_sistema_identificador_aplicacao",
        "tb_sistema",
        ["identificador_aplicacao"],
        schema="core",
    )
