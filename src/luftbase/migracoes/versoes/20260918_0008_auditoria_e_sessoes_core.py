"""Refatora auditoria e cria tabelas de sessoes no schema core.

Revision ID: 20260918_0008
Revises: 20260917_0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260918_0008"
down_revision = "20260917_0007"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def upgrade() -> None:
    """Aplica renomeacao de usuario, inclusao de user_agent e tabelas de sessoes."""

    # 1. Refatoração tb_logacesso
    op.alter_column(
        "tb_logacesso",
        "id_usuario",
        new_column_name="codigo_usuario",
        schema=SCHEMA,
    )
    op.alter_column(
        "tb_logacesso",
        "nome_usuario",
        new_column_name="login_usuario",
        type_=sa.String(100),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_logacesso",
        sa.Column("user_agent", sa.String(500), nullable=True),
        schema=SCHEMA,
    )

    op.drop_index("ix_core_logacesso_usuario_data", table_name="tb_logacesso", schema=SCHEMA)
    op.execute(
        "CREATE INDEX ix_core_logacesso_usuario_data ON core.tb_logacesso (codigo_usuario, data_hora DESC)"
    )

    # 2. Refatoração tb_logdetalhe
    op.alter_column(
        "tb_logdetalhe",
        "id_usuario",
        new_column_name="codigo_usuario",
        schema=SCHEMA,
    )
    op.alter_column(
        "tb_logdetalhe",
        "nome_usuario",
        new_column_name="login_usuario",
        type_=sa.String(100),
        schema=SCHEMA,
    )

    op.drop_index("ix_core_logdetalhe_usuario_data", table_name="tb_logdetalhe", schema=SCHEMA)
    op.execute(
        "CREATE INDEX ix_core_logdetalhe_usuario_data ON core.tb_logdetalhe (codigo_usuario, data_hora DESC)"
    )

    # 3. Criação de tb_sessao
    op.create_table(
        "tb_sessao",
        sa.Column("id_sessao", sa.String(128), primary_key=True),
        sa.Column(
            "id_sistema",
            sa.Integer(),
            sa.ForeignKey("core.tb_sistema.id_sistema", name="fk_core_sessao_sistema"),
            nullable=True,
        ),
        sa.Column("codigo_usuario", sa.Integer(), nullable=True),
        sa.Column("login_usuario", sa.String(100), nullable=True),
        sa.Column("ip_origem", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("dados_sessao", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'ATIVA'"),
        ),
        sa.Column(
            "total_renovacoes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "criada_em",
            TIMESTAMP,
            nullable=False,
            server_default=DATA_HORA_LOCAL,
        ),
        sa.Column(
            "ultima_atividade",
            TIMESTAMP,
            nullable=False,
            server_default=DATA_HORA_LOCAL,
        ),
        sa.Column("expira_em", TIMESTAMP, nullable=False),
        sa.Column("encerrada_em", TIMESTAMP, nullable=True),
        sa.Column("motivo_encerramento", sa.String(100), nullable=True),
        sa.CheckConstraint(
            "status IN ('ATIVA', 'FINALIZADA', 'EXPIRADA', 'REVOGADA')",
            name="ck_core_sessao_status",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_core_sessao_status_expira",
        "tb_sessao",
        ["status", "expira_em"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_sessao_usuario",
        "tb_sessao",
        ["codigo_usuario"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_sessao_sistema",
        "tb_sessao",
        ["id_sistema"],
        schema=SCHEMA,
    )
    op.execute(
        "CREATE INDEX ix_core_sessao_ultima_atividade ON core.tb_sessao (ultima_atividade DESC)"
    )

    # 4. Criação de tb_sessao_evento
    op.create_table(
        "tb_sessao_evento",
        sa.Column(
            "id_evento_sessao",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "id_sessao",
            sa.String(128),
            sa.ForeignKey(
                "core.tb_sessao.id_sessao",
                name="fk_core_sessaoevento_sessao",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column(
            "id_sistema",
            sa.Integer(),
            sa.ForeignKey("core.tb_sistema.id_sistema", name="fk_core_sessaoevento_sistema"),
            nullable=True,
        ),
        sa.Column("codigo_usuario", sa.Integer(), nullable=True),
        sa.Column("login_usuario", sa.String(100), nullable=True),
        sa.Column("tipo_evento", sa.String(50), nullable=False),
        sa.Column("ip_origem", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "data_hora",
            TIMESTAMP,
            nullable=False,
            server_default=DATA_HORA_LOCAL,
        ),
        sa.Column("detalhes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "tipo_evento IN ('INICIO', 'RENOVACAO', 'LOGOUT', 'TIMEOUT', 'REVOGACAO')",
            name="ck_core_sessaoevento_tipo",
        ),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_core_sessaoevento_sessao",
        "tb_sessao_evento",
        ["id_sessao"],
        schema=SCHEMA,
    )
    op.execute(
        "CREATE INDEX ix_core_sessaoevento_usuario_data ON core.tb_sessao_evento (codigo_usuario, data_hora DESC)"
    )
    op.execute("CREATE INDEX ix_core_sessaoevento_data ON core.tb_sessao_evento (data_hora DESC)")


def downgrade() -> None:
    """Reverte as alteracoes tecnicas."""

    op.drop_table("tb_sessao_evento", schema=SCHEMA)
    op.drop_table("tb_sessao", schema=SCHEMA)

    op.drop_index("ix_core_logdetalhe_usuario_data", table_name="tb_logdetalhe", schema=SCHEMA)
    op.alter_column(
        "tb_logdetalhe",
        "login_usuario",
        new_column_name="nome_usuario",
        type_=sa.String(255),
        schema=SCHEMA,
    )
    op.alter_column(
        "tb_logdetalhe",
        "codigo_usuario",
        new_column_name="id_usuario",
        schema=SCHEMA,
    )
    op.execute(
        "CREATE INDEX ix_core_logdetalhe_usuario_data ON core.tb_logdetalhe (id_usuario, data_hora DESC)"
    )

    op.drop_index("ix_core_logacesso_usuario_data", table_name="tb_logacesso", schema=SCHEMA)
    op.drop_column("tb_logacesso", "user_agent", schema=SCHEMA)
    op.alter_column(
        "tb_logacesso",
        "login_usuario",
        new_column_name="nome_usuario",
        type_=sa.String(150),
        schema=SCHEMA,
    )
    op.alter_column(
        "tb_logacesso",
        "codigo_usuario",
        new_column_name="id_usuario",
        schema=SCHEMA,
    )
    op.execute(
        "CREATE INDEX ix_core_logacesso_usuario_data ON core.tb_logacesso (id_usuario, data_hora DESC)"
    )
