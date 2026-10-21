"""Conteudo rico nas publicacoes: formato do texto e imagens do editor.

Revision ID: 20261021_0018
Revises: 20261015_0017

Aditiva: uma coluna com padrao `MARKDOWN` (o conteudo existente continua valendo) e uma tabela nova.
Codigo de versoes anteriores ignora ambos e continua funcionando.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261021_0018"
down_revision = "20261015_0017"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def upgrade() -> None:
    """Adiciona `formato_conteudo`, cria `tb_publicacaoimagem` e libera o acesso aos papeis das apps."""

    op.add_column(
        "tb_publicacao",
        sa.Column("formato_conteudo", sa.String(10), server_default="MARKDOWN", nullable=False),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_core_publicacao_formato",
        "tb_publicacao",
        "formato_conteudo IN ('MARKDOWN', 'HTML')",
        schema=SCHEMA,
    )
    op.create_table(
        "tb_publicacaoimagem",
        sa.Column("id_imagem", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("id_publicacao", sa.BigInteger(), nullable=True),
        sa.Column("tipo_mime", sa.String(50), nullable=False),
        sa.Column("nome_arquivo", sa.String(255), nullable=True),
        sa.Column("tamanho", sa.Integer(), nullable=False),
        sa.Column("hash_sha256", sa.String(64), nullable=False),
        sa.Column("dados", sa.LargeBinary(), nullable=False),
        sa.Column("criado_por", sa.String(150), nullable=False),
        sa.Column("data_criacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint("id_imagem", name="pk_core_publicacaoimagem"),
        sa.ForeignKeyConstraint(
            ["id_publicacao"],
            ["core.tb_publicacao.id_publicacao"],
            name="fk_core_publicacaoimagem_publicacao",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "tipo_mime IN ('image/png', 'image/jpeg', 'image/gif', 'image/webp')",
            name="ck_core_publicacaoimagem_mime",
        ),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_core_publicacaoimagem_publicacao",
        "tb_publicacaoimagem",
        ["id_publicacao"],
        schema=SCHEMA,
    )
    # Toda app exibe publicacoes globais (e as imagens delas): o acesso vai para TODOS os papeis das apps.
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
                        'GRANT SELECT, INSERT, UPDATE, DELETE ON core.tb_publicacaoimagem TO %I',
                        papel
                    );
                END LOOP;
            END $$
            """
        )
    )


def downgrade() -> None:
    """Remove a tabela de imagens e a coluna de formato."""

    op.drop_index("ix_core_publicacaoimagem_publicacao", table_name="tb_publicacaoimagem", schema=SCHEMA)
    op.drop_table("tb_publicacaoimagem", schema=SCHEMA)
    op.drop_constraint("ck_core_publicacao_formato", "tb_publicacao", schema=SCHEMA, type_="check")
    op.drop_column("tb_publicacao", "formato_conteudo", schema=SCHEMA)
