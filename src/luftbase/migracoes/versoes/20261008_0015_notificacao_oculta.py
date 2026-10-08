"""Cria tb_notificacao_oculta: o usuario limpa a notificacao da propria lista sem apagá-la para os demais.

Revision ID: 20261008_0015
Revises: 20261008_0014

Aditiva: so cria uma tabela nova. Codigo de versoes anteriores ignora a tabela e continua funcionando.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261008_0015"
down_revision = "20261008_0014"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def upgrade() -> None:
    """Cria a tabela e concede acesso aos papeis das aplicacoes, quando existirem."""

    op.create_table(
        "tb_notificacao_oculta",
        sa.Column("id_notificacao", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("data_ocultacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint("id_notificacao", "id_usuario", name="pk_core_notificacao_oculta"),
        sa.ForeignKeyConstraint(
            ["id_notificacao"],
            ["core.tb_notificacao.id_notificacao"],
            name="fk_core_notificacaooculta_notificacao",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_usuario"],
            ["core.tb_usuario.codigo_usuario"],
            name="fk_core_notificacaooculta_usuario",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )
    # Todo app le notificacoes, e o filtro de visibilidade consulta esta tabela: sem permissao ela quebraria a lista
    # nos sistemas satelites. Por isso o acesso vai para TODOS os papeis `luft_<sistema>_app`, nao so o do Workspace.
    op.execute(
        sa.text(
            r"""
            DO $$
            DECLARE papel text;
            BEGIN
                FOR papel IN
                    SELECT rolname FROM pg_catalog.pg_roles
                    WHERE rolname LIKE 'luft\_%\_app' OR rolname = 'luft_core_security_admin'
                LOOP
                    EXECUTE format(
                        'GRANT SELECT, INSERT, UPDATE, DELETE ON core.tb_notificacao_oculta TO %I',
                        papel
                    );
                END LOOP;
            END $$
            """
        )
    )


def downgrade() -> None:
    """Remove a tabela."""

    op.drop_table("tb_notificacao_oculta", schema=SCHEMA)
