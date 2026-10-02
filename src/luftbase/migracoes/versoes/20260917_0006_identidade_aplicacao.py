"""Adiciona a identidade tecnica estavel das aplicacoes.

Revisao: 20260917_0006
Anterior: 20260916_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0006"
down_revision: str | None = "20260916_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

IDENTIFICADORES = {
    0: "luft-workspace",
    1: "luft-connectair",
    2: "luft-control",
    3: "luft-integrador",
    4: "luft-monitor-rdp",
    5: "luft-docs",
}


def upgrade() -> None:
    """Preenche o identificador antes de aplicar obrigatoriedade e unicidade."""

    op.add_column(
        "tb_sistema",
        sa.Column("identificador_aplicacao", sa.String(80), nullable=True),
        schema="core",
    )
    tabela = sa.table(
        "tb_sistema",
        sa.column("id_sistema", sa.Integer()),
        sa.column("identificador_aplicacao", sa.String(80)),
        schema="core",
    )
    for sistema_id, identificador in IDENTIFICADORES.items():
        op.execute(
            tabela.update()
            .where(tabela.c.id_sistema == sistema_id)
            .values(identificador_aplicacao=identificador)
        )

    contexto = op.get_context()
    if not contexto.as_sql:
        conexao = op.get_bind()
        pendentes = conexao.scalar(
            sa.select(sa.func.count())
            .select_from(tabela)
            .where(tabela.c.identificador_aplicacao.is_(None))
        )
        if pendentes:
            raise RuntimeError(
                "Existem sistemas sem identificador_aplicacao. "
                "Cadastre os identificadores antes de concluir a migration."
            )

    op.alter_column(
        "tb_sistema",
        "identificador_aplicacao",
        existing_type=sa.String(80),
        nullable=False,
        schema="core",
    )
    op.create_unique_constraint(
        "uq_core_sistema_identificador_aplicacao",
        "tb_sistema",
        ["identificador_aplicacao"],
        schema="core",
    )


def downgrade() -> None:
    """Remove somente a identidade tecnica introduzida nesta revisao."""

    op.drop_constraint(
        "uq_core_sistema_identificador_aplicacao",
        "tb_sistema",
        schema="core",
        type_="unique",
    )
    op.drop_column("tb_sistema", "identificador_aplicacao", schema="core")
