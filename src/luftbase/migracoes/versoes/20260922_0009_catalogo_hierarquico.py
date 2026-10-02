"""Cria modulos e autorizacao hierarquica com integridade referencial.

Revision ID: 20260922_0009
Revises: 20260918_0008
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260922_0009"
down_revision: str | None = "20260918_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
AGORA = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")

FKS_SISTEMA = (
    ("tb_permissao", "fk_core_permissao_sistema", True),
    ("tb_logacesso", "fk_core_logacesso_sistema", False),
    ("tb_logdetalhe", "fk_core_logdetalhe_sistema", False),
    ("tb_notificacao", "fk_core_notificacao_sistema", False),
    ("tb_publicacao", "fk_core_publicacao_sistema", False),
    ("tb_sessao", "fk_core_sessao_sistema", False),
    ("tb_sessao_evento", "fk_core_sessaoevento_sistema", False),
)


def _normalizar_catalogo_legado() -> None:
    op.execute(
        """
        INSERT INTO core.tb_modulo (
            id_sistema, codigo_modulo, nome_modulo, descricao_modulo,
            icone, ordem_exibicao, ativo
        )
        SELECT DISTINCT
            p.id_sistema,
            LEFT(
                UPPER(
                    REGEXP_REPLACE(
                        COALESCE(NULLIF(BTRIM(p.categoria_permissao), ''),
                                 SPLIT_PART(p.chave_permissao, '.', 1)),
                        '[^A-Za-z0-9_]+', '_', 'g'
                    )
                ),
                50
            ) AS codigo_modulo,
            INITCAP(
                REPLACE(
                    COALESCE(NULLIF(BTRIM(p.categoria_permissao), ''),
                             SPLIT_PART(p.chave_permissao, '.', 1)),
                    '_', ' '
                )
            ) AS nome_modulo,
            'Modulo importado do catalogo legado.',
            'ph-squares-four',
            0,
            true
        FROM core.tb_permissao AS p
        ON CONFLICT (id_sistema, codigo_modulo) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE core.tb_permissao AS p
        SET id_modulo = m.id_modulo,
            recurso = LEFT(
                CASE
                    WHEN ARRAY_LENGTH(STRING_TO_ARRAY(p.chave_permissao, '.'), 1) <= 2
                        THEN 'GERAL'
                    ELSE ARRAY_TO_STRING(
                        (STRING_TO_ARRAY(p.chave_permissao, '.'))[2:
                            ARRAY_LENGTH(STRING_TO_ARRAY(p.chave_permissao, '.'), 1) - 1],
                        '_'
                    )
                END,
                80
            ),
            acao = CASE UPPER(REGEXP_REPLACE(p.chave_permissao, '^.*\\.', ''))
                WHEN 'ACESSO' THEN 'ACESSAR'
                WHEN 'DELETAR' THEN 'EXCLUIR'
                WHEN 'MAPA' THEN 'VISUALIZAR'
                WHEN 'SINCRONIZAR_GMAIL' THEN 'SINCRONIZAR'
                WHEN 'APROVAR' THEN 'APROVAR'
                WHEN 'ARQUIVAR' THEN 'ARQUIVAR'
                WHEN 'CRIAR' THEN 'CRIAR'
                WHEN 'EDITAR' THEN 'EDITAR'
                WHEN 'EXCLUIR' THEN 'EXCLUIR'
                WHEN 'EXPORTAR' THEN 'EXPORTAR'
                WHEN 'PUBLICAR' THEN 'PUBLICAR'
                WHEN 'REJEITAR' THEN 'REJEITAR'
                WHEN 'SINCRONIZAR' THEN 'SINCRONIZAR'
                WHEN 'VISUALIZAR' THEN 'VISUALIZAR'
                ELSE 'EXECUTAR'
            END,
            descricao_permissao = COALESCE(
                NULLIF(BTRIM(p.descricao_permissao), ''),
                'Permissao migrada: ' || p.chave_permissao
            )
        FROM core.tb_modulo AS m
        WHERE m.id_sistema = p.id_sistema
          AND m.codigo_modulo = LEFT(
                UPPER(
                    REGEXP_REPLACE(
                        COALESCE(NULLIF(BTRIM(p.categoria_permissao), ''),
                                 SPLIT_PART(p.chave_permissao, '.', 1)),
                        '[^A-Za-z0-9_]+', '_', 'g'
                    )
                ),
                50
          )
        """
    )
    op.execute(
        """
        UPDATE core.tb_permissao AS p
        SET eh_acesso_sistema = true
        FROM core.tb_sistema AS s
        WHERE s.id_permissao_base = p.id_permissao
        """
    )


def _recriar_fks_sistema(*, cascata: bool) -> None:
    for tabela, nome, obrigatoria in FKS_SISTEMA:
        op.drop_constraint(nome, tabela, schema=SCHEMA, type_="foreignkey")
        op.create_foreign_key(
            nome,
            tabela,
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete="CASCADE" if cascata else None,
        )
        if obrigatoria:
            op.alter_column(tabela, "id_sistema", schema=SCHEMA, nullable=False)


def upgrade() -> None:
    """Evolui dados legados sem remove-los e aplica o novo contrato."""

    op.create_table(
        "tb_modulo",
        sa.Column("id_modulo", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("codigo_modulo", sa.String(50), nullable=False),
        sa.Column("nome_modulo", sa.String(100), nullable=False),
        sa.Column("descricao_modulo", sa.String(500)),
        sa.Column("icone", sa.String(100)),
        sa.Column("ordem_exibicao", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "criado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        sa.Column(
            "atualizado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        sa.PrimaryKeyConstraint("id_modulo"),
        sa.UniqueConstraint("id_sistema", "codigo_modulo", name="uq_core_modulo_codigo_sistema"),
        sa.UniqueConstraint("id_modulo", "id_sistema", name="uq_core_modulo_id_sistema"),
        sa.CheckConstraint(
            "codigo_modulo ~ '^[A-Z][A-Z0-9_]{1,49}$'", name="ck_core_modulo_codigo"
        ),
        sa.CheckConstraint("ordem_exibicao >= 0", name="ck_core_modulo_ordem"),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_modulo_sistema",
            ondelete="CASCADE",
        ),
        schema=SCHEMA,
    )

    op.add_column(
        "tb_sistema",
        sa.Column("categoria", sa.String(20), server_default="APLICACAO", nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_sistema",
        sa.Column("ordem_exibicao", sa.SmallInteger(), server_default="0", nullable=False),
        schema=SCHEMA,
    )
    op.add_column("tb_sistema", sa.Column("cor", sa.String(30)), schema=SCHEMA)
    op.add_column("tb_sistema", sa.Column("url_saude", sa.String(500)), schema=SCHEMA)
    op.add_column("tb_sistema", sa.Column("responsavel", sa.String(150)), schema=SCHEMA)
    op.add_column("tb_sistema", sa.Column("contato_suporte", sa.String(255)), schema=SCHEMA)
    op.add_column("tb_sistema", sa.Column("metadados_json", postgresql.JSONB()), schema=SCHEMA)
    op.add_column(
        "tb_sistema",
        sa.Column(
            "criado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_sistema",
        sa.Column(
            "atualizado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )
    op.alter_column(
        "tb_sistema",
        "descricao_sistema",
        schema=SCHEMA,
        type_=sa.String(500),
        existing_type=sa.String(255),
    )
    op.alter_column(
        "tb_sistema", "link", schema=SCHEMA, type_=sa.String(500), existing_type=sa.String(255)
    )
    op.execute("UPDATE core.tb_sistema SET ativo = true WHERE ativo IS NULL")
    op.alter_column(
        "tb_sistema", "ativo", schema=SCHEMA, nullable=False, server_default=sa.text("true")
    )
    op.create_check_constraint(
        "ck_core_sistema_ordem", "tb_sistema", "ordem_exibicao >= 0", schema=SCHEMA
    )
    op.create_check_constraint(
        "ck_core_sistema_categoria",
        "tb_sistema",
        "categoria IN ('HUB', 'APLICACAO', 'SERVICO')",
        schema=SCHEMA,
    )

    op.alter_column(
        "tb_permissao",
        "chave_permissao",
        schema=SCHEMA,
        type_=sa.String(180),
        existing_type=sa.String(100),
    )
    op.alter_column(
        "tb_permissao",
        "descricao_permissao",
        schema=SCHEMA,
        type_=sa.String(500),
        existing_type=sa.String(255),
    )
    op.add_column("tb_permissao", sa.Column("id_modulo", sa.Integer()), schema=SCHEMA)
    op.add_column("tb_permissao", sa.Column("id_permissao_pai", sa.Integer()), schema=SCHEMA)
    op.add_column("tb_permissao", sa.Column("recurso", sa.String(80)), schema=SCHEMA)
    op.add_column("tb_permissao", sa.Column("acao", sa.String(30)), schema=SCHEMA)
    op.add_column(
        "tb_permissao",
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissao",
        sa.Column("sensivel", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissao",
        sa.Column(
            "eh_acesso_sistema", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissao",
        sa.Column("ordem_exibicao", sa.SmallInteger(), server_default="0", nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissao",
        sa.Column(
            "criado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissao",
        sa.Column(
            "atualizado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )

    _normalizar_catalogo_legado()
    # A baseline possui FKs adiadas entre sistema e permissao. Forcar a
    # verificacao aqui libera os eventos antes dos ALTER TABLE seguintes.
    op.execute("SET CONSTRAINTS ALL IMMEDIATE")

    op.alter_column("tb_permissao", "id_modulo", schema=SCHEMA, nullable=False)
    op.alter_column("tb_permissao", "recurso", schema=SCHEMA, nullable=False)
    op.alter_column("tb_permissao", "acao", schema=SCHEMA, nullable=False)
    op.alter_column("tb_permissao", "descricao_permissao", schema=SCHEMA, nullable=False)
    op.create_unique_constraint(
        "uq_core_permissao_id_sistema",
        "tb_permissao",
        ["id_permissao", "id_sistema"],
        schema=SCHEMA,
    )
    op.create_foreign_key(
        "fk_core_permissao_modulo",
        "tb_permissao",
        "tb_modulo",
        ["id_modulo", "id_sistema"],
        ["id_modulo", "id_sistema"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_core_permissao_pai",
        "tb_permissao",
        "tb_permissao",
        ["id_permissao_pai", "id_sistema"],
        ["id_permissao", "id_sistema"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_core_permissao_acao",
        "tb_permissao",
        "acao IN ('ACESSAR','ADMINISTRAR','APROVAR','ARQUIVAR','ATIVAR','BAIXAR','CANCELAR','CONCEDER','CONFIGURAR','CRIAR','DESATIVAR','EDITAR','ENVIAR','EXECUTAR','EXCLUIR','EXPORTAR','GERENCIAR','IGNORAR','IMPORTAR','IMPRIMIR','LISTAR','PROCESSAR','PUBLICAR','REJEITAR','REPROCESSAR','REVOGAR','SINCRONIZAR','VISUALIZAR')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_core_permissao_pai_distinto",
        "tb_permissao",
        "id_permissao_pai IS NULL OR id_permissao_pai <> id_permissao",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_core_permissao_ordem", "tb_permissao", "ordem_exibicao >= 0", schema=SCHEMA
    )
    op.execute(
        "ALTER TABLE core.tb_permissao ADD CONSTRAINT ck_core_permissao_chave CHECK (chave_permissao ~ '^[A-Z][A-Z0-9_]*(\\.[A-Z][A-Z0-9_]*){1,}$') NOT VALID"
    )

    op.add_column(
        "tb_permissaogrupo",
        sa.Column("conceder", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissaogrupo", sa.Column("codigo_usuario_alteracao", sa.Integer()), schema=SCHEMA
    )
    op.add_column(
        "tb_permissaogrupo",
        sa.Column(
            "atualizado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )
    op.add_column(
        "tb_permissaousuario", sa.Column("codigo_usuario_alteracao", sa.Integer()), schema=SCHEMA
    )
    op.add_column(
        "tb_permissaousuario",
        sa.Column(
            "atualizado_em", postgresql.TIMESTAMP(precision=3), server_default=AGORA, nullable=False
        ),
        schema=SCHEMA,
    )
    op.execute("UPDATE core.tb_permissaousuario SET conceder = true WHERE conceder IS NULL")
    op.alter_column(
        "tb_permissaousuario",
        "conceder",
        schema=SCHEMA,
        nullable=False,
        server_default=sa.text("true"),
    )
    op.create_check_constraint(
        "ck_core_permissaogrupo_codigo",
        "tb_permissaogrupo",
        "codigo_usuariogrupo > 0",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "ck_core_permissaousuario_codigo",
        "tb_permissaousuario",
        "codigo_usuario > 0",
        schema=SCHEMA,
    )

    op.drop_constraint(
        "fk_core_permissaogrupo_permissao", "tb_permissaogrupo", schema=SCHEMA, type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_core_permissaogrupo_permissao",
        "tb_permissaogrupo",
        "tb_permissao",
        ["id_permissao"],
        ["id_permissao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_core_permissaousuario_permissao",
        "tb_permissaousuario",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_core_permissaousuario_permissao",
        "tb_permissaousuario",
        "tb_permissao",
        ["id_permissao"],
        ["id_permissao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    _recriar_fks_sistema(cascata=True)

    op.drop_constraint(
        "fk_core_sistema_permissao_base", "tb_sistema", schema=SCHEMA, type_="foreignkey"
    )
    op.drop_column("tb_sistema", "id_permissao_base", schema=SCHEMA)
    op.drop_column("tb_permissao", "categoria_permissao", schema=SCHEMA)

    op.create_index(
        "ix_core_sistema_ativo_ordem", "tb_sistema", ["ativo", "ordem_exibicao"], schema=SCHEMA
    )
    op.create_index(
        "ix_core_modulo_sistema_ordem", "tb_modulo", ["id_sistema", "ordem_exibicao"], schema=SCHEMA
    )
    op.create_index(
        "ix_core_permissao_modulo_ordem",
        "tb_permissao",
        ["id_modulo", "ordem_exibicao"],
        schema=SCHEMA,
    )
    op.create_index("ix_core_permissao_pai", "tb_permissao", ["id_permissao_pai"], schema=SCHEMA)
    op.create_index(
        "ix_core_permissaogrupo_grupo", "tb_permissaogrupo", ["codigo_usuariogrupo"], schema=SCHEMA
    )
    op.create_index(
        "ux_core_permissao_acesso_sistema",
        "tb_permissao",
        ["id_sistema"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("eh_acesso_sistema IS TRUE"),
    )

    op.execute(
        "CREATE TRIGGER trg_revisao_autorizacao_tb_modulo AFTER INSERT OR UPDATE OR DELETE ON core.tb_modulo FOR EACH STATEMENT EXECUTE FUNCTION core.fn_incrementar_revisao_autorizacao()"
    )


def downgrade() -> None:
    """Restaura o contrato anterior preservando as chaves e concessoes existentes."""

    op.execute("DROP TRIGGER IF EXISTS trg_revisao_autorizacao_tb_modulo ON core.tb_modulo")
    op.drop_index("ux_core_permissao_acesso_sistema", table_name="tb_permissao", schema=SCHEMA)
    op.drop_index("ix_core_permissaogrupo_grupo", table_name="tb_permissaogrupo", schema=SCHEMA)
    op.drop_index("ix_core_permissao_pai", table_name="tb_permissao", schema=SCHEMA)
    op.drop_index("ix_core_permissao_modulo_ordem", table_name="tb_permissao", schema=SCHEMA)
    op.drop_index("ix_core_modulo_sistema_ordem", table_name="tb_modulo", schema=SCHEMA)
    op.drop_index("ix_core_sistema_ativo_ordem", table_name="tb_sistema", schema=SCHEMA)

    # Dropar restricoes adicionadas na 0009 ANTES de qualquer DML/atualizacao
    op.drop_constraint("fk_core_permissao_pai", "tb_permissao", schema=SCHEMA, type_="foreignkey")
    op.drop_constraint(
        "fk_core_permissao_modulo", "tb_permissao", schema=SCHEMA, type_="foreignkey"
    )
    for restricao in (
        "ck_core_permissao_chave",
        "ck_core_permissao_acao",
        "ck_core_permissao_pai_distinto",
        "ck_core_permissao_ordem",
    ):
        op.drop_constraint(restricao, "tb_permissao", schema=SCHEMA, type_="check")
    op.drop_constraint(
        "uq_core_permissao_id_sistema", "tb_permissao", schema=SCHEMA, type_="unique"
    )

    for tabela, restricao in (
        ("tb_permissaousuario", "ck_core_permissaousuario_codigo"),
        ("tb_permissaogrupo", "ck_core_permissaogrupo_codigo"),
    ):
        op.drop_constraint(restricao, tabela, schema=SCHEMA, type_="check")

    op.add_column("tb_sistema", sa.Column("id_permissao_base", sa.Integer()), schema=SCHEMA)
    op.execute(
        "UPDATE core.tb_sistema AS s SET id_permissao_base = p.id_permissao FROM core.tb_permissao AS p WHERE p.id_sistema = s.id_sistema AND p.eh_acesso_sistema IS TRUE"
    )
    op.create_foreign_key(
        "fk_core_sistema_permissao_base",
        "tb_sistema",
        "tb_permissao",
        ["id_permissao_base"],
        ["id_permissao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )

    op.add_column("tb_permissao", sa.Column("categoria_permissao", sa.String(50)), schema=SCHEMA)
    op.execute(
        "UPDATE core.tb_permissao AS p SET categoria_permissao = m.codigo_modulo FROM core.tb_modulo AS m WHERE m.id_modulo = p.id_modulo"
    )

    _recriar_fks_sistema(cascata=False)
    op.drop_constraint(
        "fk_core_permissaousuario_permissao",
        "tb_permissaousuario",
        schema=SCHEMA,
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_core_permissaousuario_permissao",
        "tb_permissaousuario",
        "tb_permissao",
        ["id_permissao"],
        ["id_permissao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )
    op.drop_constraint(
        "fk_core_permissaogrupo_permissao", "tb_permissaogrupo", schema=SCHEMA, type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_core_permissaogrupo_permissao",
        "tb_permissaogrupo",
        "tb_permissao",
        ["id_permissao"],
        ["id_permissao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
    )

    op.drop_column("tb_permissaousuario", "atualizado_em", schema=SCHEMA)
    op.drop_column("tb_permissaousuario", "codigo_usuario_alteracao", schema=SCHEMA)
    op.alter_column(
        "tb_permissaousuario",
        "conceder",
        schema=SCHEMA,
        nullable=True,
        server_default=sa.text("true"),
    )
    op.drop_column("tb_permissaogrupo", "atualizado_em", schema=SCHEMA)
    op.drop_column("tb_permissaogrupo", "codigo_usuario_alteracao", schema=SCHEMA)
    op.drop_column("tb_permissaogrupo", "conceder", schema=SCHEMA)

    for coluna in (
        "atualizado_em",
        "criado_em",
        "ordem_exibicao",
        "eh_acesso_sistema",
        "sensivel",
        "ativo",
        "acao",
        "recurso",
        "id_permissao_pai",
        "id_modulo",
    ):
        op.drop_column("tb_permissao", coluna, schema=SCHEMA)
    op.alter_column(
        "tb_permissao",
        "descricao_permissao",
        schema=SCHEMA,
        nullable=True,
        type_=sa.String(255),
        existing_type=sa.String(500),
    )
    op.alter_column(
        "tb_permissao",
        "chave_permissao",
        schema=SCHEMA,
        type_=sa.String(100),
        existing_type=sa.String(180),
    )

    for restricao in ("ck_core_sistema_categoria", "ck_core_sistema_ordem"):
        op.drop_constraint(restricao, "tb_sistema", schema=SCHEMA, type_="check")
    for coluna in (
        "atualizado_em",
        "criado_em",
        "metadados_json",
        "contato_suporte",
        "responsavel",
        "url_saude",
        "cor",
        "ordem_exibicao",
        "categoria",
    ):
        op.drop_column("tb_sistema", coluna, schema=SCHEMA)
    op.alter_column(
        "tb_sistema", "link", schema=SCHEMA, type_=sa.String(255), existing_type=sa.String(500)
    )
    op.alter_column(
        "tb_sistema",
        "descricao_sistema",
        schema=SCHEMA,
        type_=sa.String(255),
        existing_type=sa.String(500),
    )
    op.alter_column(
        "tb_sistema", "ativo", schema=SCHEMA, nullable=True, server_default=sa.text("true")
    )
    op.drop_table("tb_modulo", schema=SCHEMA)
