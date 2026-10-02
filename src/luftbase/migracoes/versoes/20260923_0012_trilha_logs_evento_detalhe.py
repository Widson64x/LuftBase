"""Reestrutura a trilha de logs para tb_logs -> tb_logevento -> tb_logdetalhe com id_log.

Revision ID: 20260923_0012
Revises: 20260923_0011

Esta revisao reestrutura a trilha em tres camadas amarradas pelo id_log:
1. tb_logs: rotas e requisicoes HTTP (PK id_log)
2. tb_logevento: acoes e ocorrencias de negocio (PK id_logevento, FK id_log)
3. tb_logdetalhe: alteracoes detalhadas de dados antes -> depois (PK id_logdetalhe, FK id_log, FK id_logevento)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260923_0012"
down_revision = "20260923_0011"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def _identidade() -> sa.Identity:
    return sa.Identity(always=False)


def upgrade() -> None:
    """Descarta tabelas anteriores e cria tb_logs -> tb_logevento -> tb_logdetalhe."""

    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_logs CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_logdetalhe CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_logacesso CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_logevento CASCADE"))

    # 1. tb_logs (Rotas HTTP / Requisicoes)
    op.create_table(
        "tb_logs",
        sa.Column("id_log", sa.BigInteger(), _identidade(), nullable=False),
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
            name="ck_core_logs_duracao",
        ),
        sa.CheckConstraint(
            "status_http IS NULL OR status_http BETWEEN 100 AND 599",
            name="ck_core_logs_status_http",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logs_sistema",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_log"),
        sa.UniqueConstraint(
            "id_log",
            "id_sistema",
            name="uq_core_logs_id_sistema",
        ),
        schema=SCHEMA,
    )

    # 2. tb_logevento (Acoes e Eventos entre a rota e os servicos)
    op.create_table(
        "tb_logevento",
        sa.Column("id_logevento", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("id_log", sa.BigInteger()),
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
            name="ck_core_logevento_severidade",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_logevento_sistema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_log", "id_sistema"],
            ["core.tb_logs.id_log", "core.tb_logs.id_sistema"],
            name="fk_core_logevento_log",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_logevento"),
        sa.UniqueConstraint(
            "id_logevento",
            "id_sistema",
            name="uq_core_logevento_id_sistema",
        ),
        schema=SCHEMA,
    )

    # 3. tb_logdetalhe (Deltas e detalhes das alteracoes de dados antes -> depois)
    op.create_table(
        "tb_logdetalhe",
        sa.Column("id_logdetalhe", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_log", sa.BigInteger()),
        sa.Column("id_logevento", sa.BigInteger(), nullable=False),
        sa.Column("tipo_alteracao", sa.String(20), nullable=False),
        sa.Column("campos_alterados_json", sa.Text()),
        sa.Column("dados_anteriores_json", sa.Text()),
        sa.Column("dados_novos_json", sa.Text()),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.CheckConstraint(
            "tipo_alteracao IN ('CRIACAO', 'ALTERACAO', 'EXCLUSAO', 'SUBSTITUICAO')",
            name="ck_core_logdetalhe_tipo_alteracao",
        ),
        sa.ForeignKeyConstraint(
            ["id_log"],
            ["core.tb_logs.id_log"],
            name="fk_core_logdetalhe_log",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_logevento"],
            ["core.tb_logevento.id_logevento"],
            name="fk_core_logdetalhe_logevento",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_logdetalhe"),
        schema=SCHEMA,
    )

    _criar_indices()
    _conceder_privilegios()


def _criar_indices() -> None:
    comandos = (
        "CREATE INDEX ix_core_logs_data ON core.tb_logs (data_hora DESC)",
        "CREATE INDEX ix_core_logs_sistema_data ON core.tb_logs (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logs_usuario_data ON core.tb_logs (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logs_grupo_data ON core.tb_logs (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logs_correlacao ON core.tb_logs (id_sistema, id_correlacao)",
        "CREATE INDEX ix_core_logevento_log ON core.tb_logevento (id_log)",
        "CREATE INDEX ix_core_logevento_sistema_data ON core.tb_logevento (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logevento_usuario_data ON core.tb_logevento (codigo_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logevento_grupo_data ON core.tb_logevento (codigo_grupo, data_hora DESC)",
        "CREATE INDEX ix_core_logevento_correlacao ON core.tb_logevento (id_sistema, id_correlacao)",
        "CREATE INDEX ix_core_logevento_sistema_severidade_data ON core.tb_logevento (id_sistema, severidade, data_hora DESC)",
        "CREATE INDEX ix_core_logevento_recurso ON core.tb_logevento (recurso, id_recurso, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_log ON core.tb_logdetalhe (id_log)",
        "CREATE INDEX ix_core_logdetalhe_evento ON core.tb_logdetalhe (id_logevento)",
        "CREATE INDEX ix_core_logdetalhe_tipo_data ON core.tb_logdetalhe (tipo_alteracao, data_hora DESC)",
    )
    for comando in comandos:
        op.execute(sa.text(comando))


def _conceder_privilegios() -> None:
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
                        core.tb_logs,
                        core.tb_logevento,
                        core.tb_logdetalhe
                    TO luft_core_audit_write;
                    GRANT UPDATE (id_log) ON core.tb_logevento, core.tb_logdetalhe
                    TO luft_core_audit_write;
                    GRANT USAGE, SELECT ON
                        core.tb_logs_id_log_seq,
                        core.tb_logevento_id_logevento_seq,
                        core.tb_logdetalhe_id_logdetalhe_seq
                    TO luft_core_audit_write;
                END IF;
            END $$
            """
        )
    )


def downgrade() -> None:
    """Reverte para a revisao 0011."""

    op.drop_table("tb_logdetalhe", schema=SCHEMA)
    op.drop_table("tb_logevento", schema=SCHEMA)
    op.drop_table("tb_logs", schema=SCHEMA)

