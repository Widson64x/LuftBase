"""Adiciona preferencias de usuario e revisoes de cache.

Revisao: 20260915_0002
Anterior: 20260915_0001
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")


def upgrade() -> None:
    """Cria as estruturas novas sem modificar as 13 tabelas adotadas."""

    op.create_table(
        "tb_preferenciausuario",
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("tema", sa.String(50), server_default="luft", nullable=False),
        sa.Column("modo_tema", sa.String(10), server_default="SISTEMA", nullable=False),
        sa.Column("idioma", sa.String(10), server_default="pt-BR", nullable=False),
        sa.Column("configuracoes_json", sa.Text(), nullable=True),
        sa.Column(
            "data_atualizacao",
            postgresql.TIMESTAMP(timezone=False, precision=3),
            server_default=DATA_HORA_LOCAL,
            nullable=False,
        ),
        sa.CheckConstraint(
            "modo_tema IN ('CLARO', 'ESCURO', 'SISTEMA')",
            name="ck_core_preferenciausuario_modo_tema",
        ),
        sa.PrimaryKeyConstraint("id_usuario", name="pk_core_preferenciausuario"),
        schema="core",
    )
    op.create_table(
        "tb_revisaocache",
        sa.Column("namespace", sa.String(100), nullable=False),
        sa.Column("revisao", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "data_atualizacao",
            postgresql.TIMESTAMP(timezone=False, precision=3),
            server_default=DATA_HORA_LOCAL,
            nullable=False,
        ),
        sa.CheckConstraint(
            "revisao >= 0",
            name="ck_core_revisaocache_nao_negativa",
        ),
        sa.PrimaryKeyConstraint("namespace", name="pk_core_revisaocache"),
        schema="core",
    )


def downgrade() -> None:
    """Remove somente as duas estruturas introduzidas nesta revisao."""

    op.drop_table("tb_revisaocache", schema="core")
    op.drop_table("tb_preferenciausuario", schema="core")
