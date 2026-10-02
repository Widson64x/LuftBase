"""Adiciona correlacao e metricas basicas aos logs do core.

Revisao: 20260916_0004
Anterior: 20260916_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0004"
down_revision: str | None = "20260916_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Amplia os logs sem alterar ou reconstruir dados migrados."""

    op.add_column(
        "tb_logacesso",
        sa.Column("id_correlacao", sa.String(64)),
        schema="core",
    )
    op.add_column(
        "tb_logacesso",
        sa.Column("duracao_ms", sa.Integer()),
        schema="core",
    )
    op.add_column(
        "tb_logacesso",
        sa.Column("status_http", sa.SmallInteger()),
        schema="core",
    )
    op.create_check_constraint(
        "ck_core_logacesso_duracao",
        "tb_logacesso",
        "duracao_ms IS NULL OR duracao_ms >= 0",
        schema="core",
    )
    op.create_check_constraint(
        "ck_core_logacesso_status_http",
        "tb_logacesso",
        "status_http IS NULL OR status_http BETWEEN 100 AND 599",
        schema="core",
    )
    op.create_index(
        "ix_core_logacesso_correlacao",
        "tb_logacesso",
        ["id_correlacao"],
        schema="core",
    )

    op.add_column(
        "tb_logdetalhe",
        sa.Column("id_correlacao", sa.String(64)),
        schema="core",
    )
    op.create_index(
        "ix_core_logdetalhe_correlacao",
        "tb_logdetalhe",
        ["id_correlacao"],
        schema="core",
    )


def downgrade() -> None:
    """Remove somente colunas, checks e indices desta revisao."""

    op.drop_index("ix_core_logdetalhe_correlacao", table_name="tb_logdetalhe", schema="core")
    op.drop_column("tb_logdetalhe", "id_correlacao", schema="core")

    op.drop_index("ix_core_logacesso_correlacao", table_name="tb_logacesso", schema="core")
    op.drop_constraint(
        "ck_core_logacesso_status_http",
        "tb_logacesso",
        schema="core",
        type_="check",
    )
    op.drop_constraint(
        "ck_core_logacesso_duracao",
        "tb_logacesso",
        schema="core",
        type_="check",
    )
    op.drop_column("tb_logacesso", "status_http", schema="core")
    op.drop_column("tb_logacesso", "duracao_ms", schema="core")
    op.drop_column("tb_logacesso", "id_correlacao", schema="core")
