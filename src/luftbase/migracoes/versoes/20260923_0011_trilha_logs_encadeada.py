"""Recria a trilha de logs como acesso, detalhe e alteracao.

Revision ID: 20260923_0011
Revises: 20260922_0010

Esta revisao e intencionalmente destrutiva. As tabelas de auditoria ainda pertencem ao
ambiente de desenvolvimento do piloto e seus registros anteriores nao sao autoritativos.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260923_0011"
down_revision = "20260922_0010"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def _identidade() -> sa.Identity:
    return sa.Identity(always=False)


def upgrade() -> None:
    """Descarta os dados experimentais e cria a cadeia relacional definitiva."""

    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_logs"))
    op.drop_table("tb_logdetalhe", schema=SCHEMA)
    op.drop_table("tb_logacesso", schema=SCHEMA)

    op.create_table(
        "tb_logacesso",
        sa.Column("id_logacesso", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("codigo_grupo", sa.Integer()),
        sa.Column("nome_grupo", sa.String(100)),
        sa.Column("rota_acessada", sa.String(500), nullable=False),
        sa.Column("metodo_http", sa.String(10), nullable=False),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("permissao_exigida", sa.String(180)),
        sa.Column("acesso_permitido", sa.Boolean()),
        sa.Column("parametros_requisicao", sa.Text()),
        sa.Column("resposta_acao", sa.Text()),
        sa.Column("id_correlacao", sa.String(64), nullable=False),
        sa.Column("duracao_ms", sa.Integer(), nullable=False),
        sa.Column("status_http", sa.SmallInteger(), nullable=False),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0",
            name="ck_core_logacesso_duracao",
        ),
        sa.CheckConstraint(
            "status_http IS NULL OR status_http BETWEEN 100 AND 599",
            name="ck_core_logacesso_status_http",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logacesso_sistema",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_logacesso"),
        sa.UniqueConstraint(
            "id_logacesso",
            "id_sistema",
            name="uq_core_logacesso_id_sistema",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_logdetalhe",
        sa.Column("id_logdetalhe", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("id_logacesso", sa.BigInteger()),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("codigo_grupo", sa.Integer()),
        sa.Column("nome_grupo", sa.String(100)),
        sa.Column("acao", sa.String(80), nullable=False),
        sa.Column("recurso", sa.String(150), nullable=False),
        sa.Column("id_recurso", sa.String(150)),
        sa.Column("descricao", sa.String(1000), nullable=False),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("severidade", sa.String(20), server_default="BAIXA", nullable=False),
        sa.Column("traceback", sa.Text()),
        sa.Column("id_correlacao", sa.String(64)),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.CheckConstraint(
            "severidade IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
            name="ck_core_logdetalhe_severidade",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logdetalhe_sistema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_logacesso", "id_sistema"],
            ["core.tb_logacesso.id_logacesso", "core.tb_logacesso.id_sistema"],
            name="fk_core_logdetalhe_logacesso",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_logdetalhe"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_logs",
        sa.Column("id_logalteracao", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_logdetalhe", sa.BigInteger(), nullable=False),
        sa.Column("tipo_alteracao", sa.String(20), nullable=False),
        sa.Column("campos_alterados_json", sa.Text()),
        sa.Column("dados_anteriores_json", sa.Text()),
        sa.Column("dados_novos_json", sa.Text()),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.CheckConstraint(
            "tipo_alteracao IN ('CRIACAO', 'ALTERACAO', 'EXCLUSAO', 'SUBSTITUICAO')",
            name="ck_core_logs_tipo_alteracao",
        ),
        sa.ForeignKeyConstraint(
            ["id_logdetalhe"],
            ["core.tb_logdetalhe.id_logdetalhe"],
            name="fk_core_logs_logdetalhe",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_logalteracao"),
        schema=SCHEMA,
    )

    _criar_indices_novos()
    _conceder_privilegios_runtime()


def _criar_indices_novos() -> None:
    comandos = (
        "CREATE INDEX ix_core_logacesso_data ON core.tb_logacesso (data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_sistema_data ON core.tb_logacesso (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_usuario_data ON core.tb_logacesso (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_grupo_data ON core.tb_logacesso (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_correlacao ON core.tb_logacesso (id_sistema, id_correlacao)",
        "CREATE INDEX ix_core_logdetalhe_logacesso ON core.tb_logdetalhe (id_logacesso)",
        "CREATE INDEX ix_core_logdetalhe_sistema_data ON core.tb_logdetalhe (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_usuario_data ON core.tb_logdetalhe (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_grupo_data ON core.tb_logdetalhe (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_correlacao ON core.tb_logdetalhe (id_sistema, id_correlacao)",
        "CREATE INDEX ix_core_logdetalhe_sistema_severidade_data ON core.tb_logdetalhe (id_sistema, severidade, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_recurso ON core.tb_logdetalhe (recurso, id_recurso, data_hora DESC)",
        "CREATE INDEX ix_core_logs_logdetalhe ON core.tb_logs (id_logdetalhe)",
        "CREATE INDEX ix_core_logs_tipo_data ON core.tb_logs (tipo_alteracao, data_hora DESC)",
    )
    for comando in comandos:
        op.execute(sa.text(comando))


def _conceder_privilegios_runtime() -> None:
    """Concede apenas o necessario quando as roles corporativas ja existem."""

    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_catalog.pg_roles
                    WHERE rolname = 'luft_core_audit_write'
                ) THEN
                    GRANT SELECT, INSERT ON
                        core.tb_logacesso,
                        core.tb_logdetalhe,
                        core.tb_logs
                    TO luft_core_audit_write;
                    GRANT UPDATE (id_logacesso) ON core.tb_logdetalhe
                    TO luft_core_audit_write;
                    GRANT USAGE, SELECT ON
                        core.tb_logacesso_id_logacesso_seq,
                        core.tb_logdetalhe_id_logdetalhe_seq,
                        core.tb_logs_id_logalteracao_seq
                    TO luft_core_audit_write;
                END IF;
            END $$
            """
        )
    )


def downgrade() -> None:
    """Recria, vazias, as duas tabelas do contrato anterior."""

    op.drop_table("tb_logs", schema=SCHEMA)
    op.drop_table("tb_logdetalhe", schema=SCHEMA)
    op.drop_table("tb_logacesso", schema=SCHEMA)
    _criar_estrutura_anterior()


def _criar_estrutura_anterior() -> None:
    op.create_table(
        "tb_logacesso",
        sa.Column("id_log", sa.Integer(), _identidade(), nullable=False),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("codigo_grupo", sa.Integer()),
        sa.Column("nome_grupo", sa.String(100)),
        sa.Column("rota_acessada", sa.String(200)),
        sa.Column("metodo_http", sa.String(10)),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("permissao_exigida", sa.String(100)),
        sa.Column("acesso_permitido", sa.Boolean()),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("parametros_requisicao", sa.Text()),
        sa.Column("resposta_acao", sa.Text()),
        sa.Column("id_correlacao", sa.String(64)),
        sa.Column("duracao_ms", sa.Integer()),
        sa.Column("status_http", sa.SmallInteger()),
        sa.CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0",
            name="ck_core_logacesso_duracao",
        ),
        sa.CheckConstraint(
            "status_http IS NULL OR status_http BETWEEN 100 AND 599",
            name="ck_core_logacesso_status_http",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logacesso_sistema",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_log"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_logdetalhe",
        sa.Column("id_logdetalhe", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("id_logacesso", sa.Integer()),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("codigo_grupo", sa.Integer()),
        sa.Column("nome_grupo", sa.String(100)),
        sa.Column("acao", sa.String(50)),
        sa.Column("recurso", sa.String(100)),
        sa.Column("id_recurso", sa.String(100)),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("dados_anteriores_json", sa.Text()),
        sa.Column("dados_novos_json", sa.Text()),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("severidade", sa.String(20), server_default="BAIXA", nullable=False),
        sa.Column("traceback", sa.Text()),
        sa.Column("id_correlacao", sa.String(64)),
        sa.CheckConstraint(
            "severidade IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
            name="ck_core_logdetalhe_severidade",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logdetalhe_sistema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_logacesso"],
            ["core.tb_logacesso.id_log"],
            name="fk_core_logdetalhe_logacesso",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id_logdetalhe"),
        schema=SCHEMA,
    )
    comandos = (
        "CREATE INDEX ix_core_logacesso_data ON core.tb_logacesso (data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_sistema_data ON core.tb_logacesso (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_usuario_data ON core.tb_logacesso (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_grupo_data ON core.tb_logacesso (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_correlacao ON core.tb_logacesso (id_correlacao)",
        "CREATE INDEX ix_core_logdetalhe_logacesso ON core.tb_logdetalhe (id_logacesso)",
        "CREATE INDEX ix_core_logdetalhe_sistema_data ON core.tb_logdetalhe (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_usuario_data ON core.tb_logdetalhe (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_grupo_data ON core.tb_logdetalhe (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_correlacao ON core.tb_logdetalhe (id_correlacao)",
        "CREATE INDEX ix_core_logdetalhe_sistema_severidade_data ON core.tb_logdetalhe (id_sistema, severidade, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_recurso ON core.tb_logdetalhe (recurso, id_recurso, data_hora DESC)",
    )
    for comando in comandos:
        op.execute(sa.text(comando))
