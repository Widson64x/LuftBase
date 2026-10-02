"""Invalida a revisao quando estruturas de autorizacao mudam.

Revisao: 20260916_0003
Anterior: 20260915_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0003"
down_revision: str | None = "20260915_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = (
    "tb_sistema",
    "tb_permissao",
    "tb_permissaogrupo",
    "tb_permissaousuario",
)


def upgrade() -> None:
    """Cria contador e triggers PostgreSQL para invalidacao automatica."""

    op.execute(
        sa.text(
            """
            INSERT INTO core.tb_revisaocache (namespace, revisao)
            VALUES ('autorizacao', 0)
            ON CONFLICT (namespace) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION core.fn_incrementar_revisao_autorizacao()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                INSERT INTO core.tb_revisaocache (namespace, revisao, data_atualizacao)
                VALUES (
                    'autorizacao',
                    1,
                    CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo'
                )
                ON CONFLICT (namespace) DO UPDATE
                SET revisao = core.tb_revisaocache.revisao + 1,
                    data_atualizacao = EXCLUDED.data_atualizacao;
                RETURN NULL;
            END;
            $$
            """
        )
    )
    for tabela in _TABELAS:
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER trg_revisao_autorizacao_{tabela}
                AFTER INSERT OR UPDATE OR DELETE ON core.{tabela}
                FOR EACH STATEMENT
                EXECUTE FUNCTION core.fn_incrementar_revisao_autorizacao()
                """
            )
        )


def downgrade() -> None:
    """Remove somente triggers, funcao e namespace criados nesta revisao."""

    for tabela in reversed(_TABELAS):
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_revisao_autorizacao_{tabela} ON core.{tabela}")
        )
    op.execute(sa.text("DROP FUNCTION IF EXISTS core.fn_incrementar_revisao_autorizacao()"))
    op.execute(sa.text("DELETE FROM core.tb_revisaocache WHERE namespace = 'autorizacao'"))
