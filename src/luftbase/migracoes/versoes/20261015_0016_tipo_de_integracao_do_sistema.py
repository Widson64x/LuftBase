"""Acrescenta a tb_sistema a integracao com o LuftBase, o tipo de acesso e a URL de download.

Revision ID: 20261015_0016
Revises: 20261008_0015

Aditiva: as colunas tem valor padrao que reproduz o comportamento atual (sistema integrado, acessado
pela web), entao codigo de versoes anteriores continua lendo e gravando `tb_sistema` sem mudanca.
Sistemas externos (C#, executaveis, ferramentas de terceiros) passam a ter card e link sem schema,
role nem segredo no Vault.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261015_0016"
down_revision = "20261008_0015"
branch_labels = None
depends_on = None

SCHEMA = "core"
TABELA = "tb_sistema"
RESTRICAO_ACESSO = "ck_core_sistema_tipo_acesso"
RESTRICAO_DOWNLOAD = "ck_core_sistema_url_download"


def upgrade() -> None:
    """Cria as colunas e as restricoes; tolera quem ja rodou o script SQL equivalente.

    O script `tools/sql/20261015_tb_sistema_tipo_de_integracao.sql` aplica o mesmo DDL a mao em
    homologacao e producao, por isso cada passo verifica antes de criar.
    """

    op.execute(
        sa.text(
            "ALTER TABLE core.tb_sistema "
            "ADD COLUMN IF NOT EXISTS integra_luftbase boolean NOT NULL DEFAULT true"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE core.tb_sistema "
            "ADD COLUMN IF NOT EXISTS tipo_acesso varchar(20) NOT NULL DEFAULT 'WEB'"
        )
    )
    op.execute(
        sa.text("ALTER TABLE core.tb_sistema ADD COLUMN IF NOT EXISTS url_download varchar(500)")
    )
    _criar_restricao(RESTRICAO_ACESSO, "CHECK (tipo_acesso IN ('WEB', 'DOWNLOAD', 'SEM_ACESSO'))")
    # Download sem endereco nao leva a lugar nenhum; integrar com o LuftBase exige acesso web.
    _criar_restricao(
        RESTRICAO_DOWNLOAD,
        "CHECK ((tipo_acesso <> 'DOWNLOAD' OR url_download IS NOT NULL) "
        "AND (integra_luftbase = false OR tipo_acesso = 'WEB'))",
    )


def _criar_restricao(nome: str, definicao: str) -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint "
            f"WHERE conname = '{nome}' AND conrelid = 'core.tb_sistema'::regclass) THEN "
            f"ALTER TABLE core.tb_sistema ADD CONSTRAINT {nome} {definicao}; END IF; END $$"
        )
    )


def downgrade() -> None:
    """Remove as restricoes e as colunas."""

    op.drop_constraint(RESTRICAO_DOWNLOAD, TABELA, schema=SCHEMA, type_="check")
    op.drop_constraint(RESTRICAO_ACESSO, TABELA, schema=SCHEMA, type_="check")
    op.drop_column(TABELA, "url_download", schema=SCHEMA)
    op.drop_column(TABELA, "tipo_acesso", schema=SCHEMA)
    op.drop_column(TABELA, "integra_luftbase", schema=SCHEMA)
