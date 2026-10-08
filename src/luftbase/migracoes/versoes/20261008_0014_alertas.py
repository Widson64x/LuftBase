"""Cria tb_alerta e tb_alerta_controle (alertas para o desenvolvedor).

Revision ID: 20261008_0014
Revises: 20260923_0013

Migracao aditiva: so cria tabelas novas; o codigo da versao anterior continua rodando sobre este schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261008_0014"
down_revision = "20260923_0013"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def upgrade() -> None:
    op.create_table(
        "tb_alerta",
        sa.Column("id_alerta", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("chave", sa.String(400), nullable=False),
        sa.Column("regra", sa.String(40), nullable=False),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("rota", sa.String(500)),
        sa.Column("status_http", sa.SmallInteger()),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("id_correlacao", sa.String(64)),
        sa.Column("detalhe", sa.String(1000)),
        sa.Column("status", sa.String(12), nullable=False, server_default="ABERTO"),
        sa.Column("ocorrencias", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ocorrencias_notificadas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("primeira_ocorrencia", TIMESTAMP, nullable=False),
        sa.Column("ultima_ocorrencia", TIMESTAMP, nullable=False),
        sa.Column("aberto_em", TIMESTAMP, nullable=False, server_default=DATA_HORA_LOCAL),
        sa.Column("ultima_notificacao", TIMESTAMP),
        sa.Column("resolvido_em", TIMESTAMP),
        sa.Column("silenciado_ate", TIMESTAMP),
        sa.Column("texto_extra", sa.Text()),
        sa.CheckConstraint("status IN ('ABERTO', 'RESOLVIDO')", name="ck_core_alerta_status"),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_alerta_status", "tb_alerta", ["status", "ultima_ocorrencia"], schema=SCHEMA
    )
    op.create_index("ix_core_alerta_chave", "tb_alerta", ["chave", "status"], schema=SCHEMA)
    op.create_table(
        "tb_alerta_controle",
        sa.Column("chave", sa.String(50), primary_key=True),
        sa.Column("ultima_execucao_ate", TIMESTAMP),
        sa.Column("em_execucao_ate", TIMESTAMP),
        schema=SCHEMA,
    )
    # Permissoes dos papeis que existirem no ambiente (o avaliador roda a partir do Workspace).
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_workspace_app') THEN
                    GRANT SELECT, INSERT, UPDATE ON core.tb_alerta, core.tb_alerta_controle
                        TO luft_workspace_app;
                    GRANT USAGE, SELECT ON SEQUENCE core.tb_alerta_id_alerta_seq
                        TO luft_workspace_app;
                END IF;
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_core_security_admin') THEN
                    GRANT ALL PRIVILEGES ON core.tb_alerta, core.tb_alerta_controle
                        TO luft_core_security_admin;
                    GRANT USAGE, SELECT ON SEQUENCE core.tb_alerta_id_alerta_seq
                        TO luft_core_security_admin;
                END IF;
            END $$
            """
        )
    )


def downgrade() -> None:
    op.drop_table("tb_alerta_controle", schema=SCHEMA)
    op.drop_table("tb_alerta", schema=SCHEMA)
