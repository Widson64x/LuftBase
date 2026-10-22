"""Cria tb_email_fila (fila de e-mails entregue em segundo plano).

Revision ID: 20261022_0019
Revises: 20261021_0018

Migracao aditiva: so cria uma tabela nova; o codigo da versao anterior continua rodando sobre este schema.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261022_0019"
down_revision = "20261021_0018"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def upgrade() -> None:
    op.create_table(
        "tb_email_fila",
        sa.Column("id_email", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("origem", sa.String(60), nullable=False, server_default="GERAL"),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDENTE"),
        sa.Column("destinatarios", sa.Text(), nullable=False),
        sa.Column("copia", sa.Text()),
        sa.Column("assunto", sa.String(300), nullable=False),
        sa.Column("template", sa.String(200)),
        sa.Column("contexto", sa.Text()),
        sa.Column("html", sa.Text()),
        sa.Column("texto", sa.Text()),
        sa.Column("nome_remetente", sa.String(120)),
        sa.Column("responder_para", sa.String(200)),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("maximo_tentativas", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("proxima_tentativa", TIMESTAMP, nullable=False, server_default=DATA_HORA_LOCAL),
        sa.Column("bloqueado_ate", TIMESTAMP),
        sa.Column("ultimo_erro", sa.String(1000)),
        sa.Column("criado_por", sa.String(100)),
        sa.Column("criado_em", TIMESTAMP, nullable=False, server_default=DATA_HORA_LOCAL),
        sa.Column("atualizado_em", TIMESTAMP),
        sa.Column("enviado_em", TIMESTAMP),
        sa.CheckConstraint(
            "status IN ('PENDENTE', 'ENVIANDO', 'ENVIADO', 'FALHOU', 'CANCELADO')",
            name="ck_core_email_fila_status",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_email_fila_status", "tb_email_fila", ["status", "proxima_tentativa"], schema=SCHEMA
    )
    op.create_index("ix_core_email_fila_criado", "tb_email_fila", ["criado_em"], schema=SCHEMA)
    # Qualquer app pode enfileirar e o servico de envio roda em um deles: acesso para TODOS os papeis das apps.
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
                        'GRANT SELECT, INSERT, UPDATE, DELETE ON core.tb_email_fila TO %I', papel
                    );
                    EXECUTE format(
                        'GRANT USAGE, SELECT ON SEQUENCE core.tb_email_fila_id_email_seq TO %I', papel
                    );
                END LOOP;
            END $$
            """
        )
    )


def downgrade() -> None:
    op.drop_table("tb_email_fila", schema=SCHEMA)
