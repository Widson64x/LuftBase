"""Adiciona o retrato historico de grupo e indices analiticos da auditoria.

Revision ID: 20260922_0010
Revises: 20260922_0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260922_0010"
down_revision = "20260922_0009"
branch_labels = None
depends_on = None

SCHEMA = "core"


def upgrade() -> None:
    """Inclui o grupo vigente no momento do evento sem consultar o diretorio."""

    for tabela in ("tb_logacesso", "tb_logdetalhe"):
        op.add_column(tabela, sa.Column("codigo_grupo", sa.Integer()), schema=SCHEMA)
        op.add_column(tabela, sa.Column("nome_grupo", sa.String(100)), schema=SCHEMA)

    op.create_index(
        "ix_core_logacesso_grupo_data",
        "tb_logacesso",
        ["codigo_grupo", sa.text("data_hora DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_logdetalhe_grupo_data",
        "tb_logdetalhe",
        ["codigo_grupo", sa.text("data_hora DESC")],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_logdetalhe_sistema_severidade_data",
        "tb_logdetalhe",
        ["id_sistema", "severidade", sa.text("data_hora DESC")],
        schema=SCHEMA,
    )


def downgrade() -> None:
    """Remove somente os campos e indices introduzidos nesta revisao."""

    op.drop_index(
        "ix_core_logdetalhe_sistema_severidade_data",
        table_name="tb_logdetalhe",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_core_logdetalhe_grupo_data",
        table_name="tb_logdetalhe",
        schema=SCHEMA,
    )
    op.drop_index(
        "ix_core_logacesso_grupo_data",
        table_name="tb_logacesso",
        schema=SCHEMA,
    )
    for tabela in ("tb_logdetalhe", "tb_logacesso"):
        op.drop_column(tabela, "nome_grupo", schema=SCHEMA)
        op.drop_column(tabela, "codigo_grupo", schema=SCHEMA)
