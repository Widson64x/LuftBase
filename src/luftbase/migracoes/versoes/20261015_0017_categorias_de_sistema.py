"""Amplia as categorias de tb_sistema: API, FERRAMENTA, RELATORIO e INTEGRACAO.

Revision ID: 20261015_0017
Revises: 20261015_0016

Aditiva: so alarga o CHECK; as linhas atuais (HUB, APLICACAO, SERVICO) continuam validas. A lista fica
escrita aqui, e nao importada, porque uma migracao nao pode mudar quando o codigo muda.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0017"
down_revision = "20261015_0016"
branch_labels = None
depends_on = None

RESTRICAO = "ck_core_sistema_categoria"
ANTIGAS = "'HUB', 'APLICACAO', 'SERVICO'"
NOVAS = "'APLICACAO', 'API', 'SERVICO', 'FERRAMENTA', 'RELATORIO', 'INTEGRACAO', 'HUB'"


def _trocar_restricao(lista: str) -> None:
    op.execute(sa.text(f"ALTER TABLE core.tb_sistema DROP CONSTRAINT IF EXISTS {RESTRICAO}"))
    op.execute(
        sa.text(
            f"ALTER TABLE core.tb_sistema ADD CONSTRAINT {RESTRICAO} CHECK (categoria IN ({lista}))"
        )
    )


def upgrade() -> None:
    """Troca o CHECK pelo mais largo; repetir e seguro."""

    _trocar_restricao(NOVAS)


def downgrade() -> None:
    """Volta as categorias novas para APLICACAO antes de restaurar o CHECK antigo."""

    op.execute(
        sa.text(
            f"UPDATE core.tb_sistema SET categoria = 'APLICACAO' WHERE categoria NOT IN ({ANTIGAS})"
        )
    )
    _trocar_restricao(ANTIGAS)
