"""Registra e permite recriar as 13 tabelas sistemicas migradas.

Revisao: 20260915_0001
Anterior: nenhuma
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def _identidade() -> sa.Identity:
    return sa.Identity(always=False)


def upgrade() -> None:
    """Cria a baseline em bancos novos; bancos migrados devem adota-la via CLI."""

    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS core"))
    op.create_table(
        "tb_sistema",
        sa.Column("id_sistema", sa.Integer(), _identidade(), nullable=False),
        sa.Column("nome_sistema", sa.String(100), nullable=False),
        sa.Column("descricao_sistema", sa.String(255)),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true")),
        sa.Column(
            "em_manutencao",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("icone", sa.String(255)),
        sa.Column("link", sa.String(255)),
        sa.Column("id_permissao_base", sa.Integer()),
        sa.PrimaryKeyConstraint("id_sistema"),
        sa.UniqueConstraint("nome_sistema", name="uq_core_sistema_nome"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_permissao",
        sa.Column("id_permissao", sa.Integer(), _identidade(), nullable=False),
        sa.Column("chave_permissao", sa.String(100), nullable=False),
        sa.Column("descricao_permissao", sa.String(255)),
        sa.Column("categoria_permissao", sa.String(50)),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_permissao"),
        sa.UniqueConstraint(
            "chave_permissao",
            "id_sistema",
            name="uq_core_permissao_chave_sistema",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_permissaogrupo",
        sa.Column("id_vinculo", sa.Integer(), _identidade(), nullable=False),
        sa.Column("codigo_usuariogrupo", sa.Integer(), nullable=False),
        sa.Column("id_permissao", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id_vinculo"),
        sa.UniqueConstraint(
            "codigo_usuariogrupo",
            "id_permissao",
            name="uq_core_permissaogrupo",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_permissaousuario",
        sa.Column("id_vinculo", sa.Integer(), _identidade(), nullable=False),
        sa.Column("codigo_usuario", sa.Integer(), nullable=False),
        sa.Column("id_permissao", sa.Integer(), nullable=False),
        sa.Column("conceder", sa.Boolean(), server_default=sa.text("true")),
        sa.PrimaryKeyConstraint("id_vinculo"),
        sa.UniqueConstraint(
            "codigo_usuario",
            "id_permissao",
            name="uq_core_permissaousuario",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_logacesso",
        sa.Column("id_log", sa.Integer(), _identidade(), nullable=False),
        sa.Column("id_usuario", sa.Integer()),
        sa.Column("nome_usuario", sa.String(150)),
        sa.Column("rota_acessada", sa.String(200)),
        sa.Column("metodo_http", sa.String(10)),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("permissao_exigida", sa.String(100)),
        sa.Column("acesso_permitido", sa.Boolean()),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("parametros_requisicao", sa.Text()),
        sa.Column("resposta_acao", sa.Text()),
        sa.PrimaryKeyConstraint("id_log"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_logdetalhe",
        sa.Column("id_logdetalhe", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), nullable=False),
        sa.Column("id_logacesso", sa.Integer()),
        sa.Column("id_usuario", sa.Integer()),
        sa.Column("nome_usuario", sa.String(255)),
        sa.Column("acao", sa.String(50)),
        sa.Column("recurso", sa.String(100)),
        sa.Column("id_recurso", sa.String(100)),
        sa.Column("descricao", sa.String(500), nullable=False),
        sa.Column("dados_anteriores_json", sa.Text()),
        sa.Column("dados_novos_json", sa.Text()),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("severidade", sa.String(20), server_default="BAIXA", nullable=False),
        sa.Column("traceback", sa.Text()),
        sa.CheckConstraint(
            "severidade IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
            name="ck_core_logdetalhe_severidade",
        ),
        sa.PrimaryKeyConstraint("id_logdetalhe"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_notificacao",
        sa.Column("id_notificacao", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("id_usuario_destino", sa.Integer()),
        sa.Column("tipo", sa.String(20), server_default="INFO", nullable=False),
        sa.Column("categoria", sa.String(50), server_default="GERAL", nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("mensagem", sa.Text(), nullable=False),
        sa.Column("icone", sa.String(100)),
        sa.Column("lida", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("data_criacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("data_leitura", TIMESTAMP),
        sa.Column("criado_por", sa.String(150), server_default="SISTEMA", nullable=False),
        sa.Column("metadados_json", sa.Text()),
        sa.Column("expira_em", TIMESTAMP),
        sa.Column("id_grupo_destino", sa.Integer()),
        sa.Column("exibir_a_partir_de", TIMESTAMP),
        sa.CheckConstraint(
            "tipo IN ('SISTEMA', 'ALERTA', 'INFO', 'SUCESSO', 'ERRO')",
            name="ck_core_notificacao_tipo",
        ),
        sa.CheckConstraint(
            "categoria IN ('ETL', 'SEGURANCA', 'BANCO', 'SERVICO', 'GERAL', "
            "'USUARIO', 'CONFIGURACAO', 'INTEGRACAO', 'COMUNICADO', 'ATUALIZACAO')",
            name="ck_core_notificacao_categoria",
        ),
        sa.PrimaryKeyConstraint("id_notificacao"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_notificacao_leitura",
        sa.Column("id_notificacao", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("data_leitura", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint(
            "id_notificacao",
            "id_usuario",
            name="pk_core_notificacao_leitura",
        ),
        schema=SCHEMA,
    )
    _criar_publicacoes()
    _criar_chaves_estrangeiras()
    _criar_indices()


def _criar_publicacoes() -> None:
    op.create_table(
        "tb_publicacao",
        sa.Column("id_publicacao", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sistema", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tipo_publicacao", sa.String(20), nullable=False),
        sa.Column("status_publicacao", sa.String(20), server_default="RASCUNHO", nullable=False),
        sa.Column("tipo_audiencia", sa.String(10), server_default="GERAL", nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("resumo", sa.String(500)),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("prioridade", sa.String(20), server_default="NORMAL", nullable=False),
        sa.Column("versao", sa.String(50)),
        sa.Column("notificar", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("fixado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("exibir_a_partir_de", TIMESTAMP),
        sa.Column("expira_em", TIMESTAMP),
        sa.Column("data_publicacao", TIMESTAMP),
        sa.Column("data_criacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("data_atualizacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("criado_por_id", sa.Integer()),
        sa.Column("criado_por", sa.String(150), nullable=False),
        sa.Column("atualizado_por_id", sa.Integer()),
        sa.Column("atualizado_por", sa.String(150)),
        sa.Column("fonte", sa.String(20), server_default="INTERNO", nullable=False),
        sa.Column("id_externo", sa.String(255)),
        sa.Column("thread_externo", sa.String(255)),
        sa.Column("remetente_externo", sa.String(255)),
        sa.Column("url_externa", sa.String(500)),
        sa.Column("metadados_json", sa.Text()),
        sa.CheckConstraint(
            "tipo_publicacao IN ('COMUNICADO', 'ATUALIZACAO')",
            name="ck_core_publicacao_tipo",
        ),
        sa.CheckConstraint(
            "status_publicacao IN ('RASCUNHO', 'AGENDADO', 'PUBLICADO', 'ARQUIVADO')",
            name="ck_core_publicacao_status",
        ),
        sa.CheckConstraint(
            "tipo_audiencia IN ('GERAL', 'GRUPOS')",
            name="ck_core_publicacao_audiencia",
        ),
        sa.CheckConstraint(
            "prioridade IN ('BAIXA', 'NORMAL', 'ALTA', 'CRITICA')",
            name="ck_core_publicacao_prioridade",
        ),
        sa.CheckConstraint(
            "fonte IN ('INTERNO', 'GMAIL', 'API')",
            name="ck_core_publicacao_fonte",
        ),
        sa.CheckConstraint(
            "tipo_publicacao <> 'ATUALIZACAO' OR NULLIF(BTRIM(versao), '') IS NOT NULL",
            name="ck_core_publicacao_versao",
        ),
        sa.CheckConstraint(
            "expira_em IS NULL OR exibir_a_partir_de IS NULL OR expira_em > exibir_a_partir_de",
            name="ck_core_publicacao_vigencia",
        ),
        sa.CheckConstraint(
            "metadados_json IS NULL OR metadados_json::jsonb IS NOT NULL",
            name="ck_core_publicacao_metadados_json",
        ),
        sa.PrimaryKeyConstraint("id_publicacao"),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_publicacaogrupo",
        sa.Column("id_publicacao", sa.BigInteger(), nullable=False),
        sa.Column("id_grupo", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint(
            "id_publicacao",
            "id_grupo",
            name="pk_core_publicacaogrupo",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_publicacaoleitura",
        sa.Column("id_publicacao", sa.BigInteger(), nullable=False),
        sa.Column("id_usuario", sa.Integer(), nullable=False),
        sa.Column("data_leitura", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint(
            "id_publicacao",
            "id_usuario",
            name="pk_core_publicacaoleitura",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_publicacaonotificacao",
        sa.Column("id_vinculo", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_publicacao", sa.BigInteger(), nullable=False),
        sa.Column("id_notificacao", sa.BigInteger(), nullable=False),
        sa.Column("data_criacao", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint("id_vinculo"),
        sa.UniqueConstraint(
            "id_publicacao",
            "id_notificacao",
            name="uq_core_publicacaonotificacao",
        ),
        schema=SCHEMA,
    )
    op.create_table(
        "tb_notaatualizacaoitem",
        sa.Column("id_item", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_publicacao", sa.BigInteger(), nullable=False),
        sa.Column("tipo_item", sa.String(20), server_default="MELHORIA", nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("descricao", sa.Text()),
        sa.Column("ordem", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "tipo_item IN ('NOVO', 'MELHORIA', 'CORRECAO', 'SEGURANCA', 'TECNICO')",
            name="ck_core_nota_item_tipo",
        ),
        sa.PrimaryKeyConstraint("id_item"),
        schema=SCHEMA,
    )


def _criar_chaves_estrangeiras() -> None:
    chaves = (
        (
            "fk_core_sistema_permissao_base",
            "tb_sistema",
            "tb_permissao",
            ["id_permissao_base"],
            ["id_permissao"],
            "SET NULL",
            True,
        ),
        (
            "fk_core_permissao_sistema",
            "tb_permissao",
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            None,
            True,
        ),
        (
            "fk_core_permissaogrupo_permissao",
            "tb_permissaogrupo",
            "tb_permissao",
            ["id_permissao"],
            ["id_permissao"],
            None,
            False,
        ),
        (
            "fk_core_permissaousuario_permissao",
            "tb_permissaousuario",
            "tb_permissao",
            ["id_permissao"],
            ["id_permissao"],
            None,
            False,
        ),
        (
            "fk_core_logacesso_sistema",
            "tb_logacesso",
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            None,
            False,
        ),
        (
            "fk_core_logdetalhe_sistema",
            "tb_logdetalhe",
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            None,
            False,
        ),
        (
            "fk_core_logdetalhe_logacesso",
            "tb_logdetalhe",
            "tb_logacesso",
            ["id_logacesso"],
            ["id_log"],
            "SET NULL",
            False,
        ),
        (
            "fk_core_notificacao_sistema",
            "tb_notificacao",
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            None,
            False,
        ),
        (
            "fk_core_notificacao_leitura_notificacao",
            "tb_notificacao_leitura",
            "tb_notificacao",
            ["id_notificacao"],
            ["id_notificacao"],
            "CASCADE",
            False,
        ),
        (
            "fk_core_publicacao_sistema",
            "tb_publicacao",
            "tb_sistema",
            ["id_sistema"],
            ["id_sistema"],
            None,
            False,
        ),
        (
            "fk_core_publicacaogrupo_publicacao",
            "tb_publicacaogrupo",
            "tb_publicacao",
            ["id_publicacao"],
            ["id_publicacao"],
            "CASCADE",
            False,
        ),
        (
            "fk_core_publicacaoleitura_publicacao",
            "tb_publicacaoleitura",
            "tb_publicacao",
            ["id_publicacao"],
            ["id_publicacao"],
            "CASCADE",
            False,
        ),
        (
            "fk_core_publicacaonotificacao_publicacao",
            "tb_publicacaonotificacao",
            "tb_publicacao",
            ["id_publicacao"],
            ["id_publicacao"],
            "CASCADE",
            False,
        ),
        (
            "fk_core_publicacaonotificacao_notificacao",
            "tb_publicacaonotificacao",
            "tb_notificacao",
            ["id_notificacao"],
            ["id_notificacao"],
            "CASCADE",
            False,
        ),
        (
            "fk_core_nota_item_publicacao",
            "tb_notaatualizacaoitem",
            "tb_publicacao",
            ["id_publicacao"],
            ["id_publicacao"],
            "CASCADE",
            False,
        ),
    )
    for nome, origem, destino, locais, remotas, ao_excluir, adiavel in chaves:
        op.create_foreign_key(
            nome,
            origem,
            destino,
            locais,
            remotas,
            source_schema=SCHEMA,
            referent_schema=SCHEMA,
            ondelete=ao_excluir,
            deferrable=adiavel or None,
            initially="DEFERRED" if adiavel else None,
        )


def _criar_indices() -> None:
    simples = (
        ("ix_core_permissao_sistema", "tb_permissao", ["id_sistema"]),
        ("ix_core_permissaogrupo_permissao", "tb_permissaogrupo", ["id_permissao"]),
        ("ix_core_permissaousuario_permissao", "tb_permissaousuario", ["id_permissao"]),
        ("ix_core_permissaousuario_usuario", "tb_permissaousuario", ["codigo_usuario"]),
        ("ix_core_logdetalhe_logacesso", "tb_logdetalhe", ["id_logacesso"]),
        (
            "ix_core_publicacaogrupo_grupo_publicacao",
            "tb_publicacaogrupo",
            ["id_grupo", "id_publicacao"],
        ),
        (
            "ix_core_publicacaonotificacao_notificacao",
            "tb_publicacaonotificacao",
            ["id_notificacao"],
        ),
        (
            "ix_core_nota_item_publicacao_ordem",
            "tb_notaatualizacaoitem",
            ["id_publicacao", "ordem", "id_item"],
        ),
    )
    for nome, tabela, colunas in simples:
        op.create_index(nome, tabela, colunas, schema=SCHEMA)

    comandos = (
        "CREATE INDEX ix_core_logacesso_data ON core.tb_logacesso (data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_sistema_data ON core.tb_logacesso (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logacesso_usuario_data ON core.tb_logacesso (id_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_sistema_data ON core.tb_logdetalhe (id_sistema, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_usuario_data ON core.tb_logdetalhe (id_usuario, data_hora DESC)",
        "CREATE INDEX ix_core_logdetalhe_recurso ON core.tb_logdetalhe (recurso, id_recurso, data_hora DESC)",
        "CREATE INDEX ix_core_notificacao_expiracao ON core.tb_notificacao (expira_em) WHERE expira_em IS NOT NULL",
        "CREATE INDEX ix_core_notificacao_sistema_data ON core.tb_notificacao (id_sistema, data_criacao DESC)",
        "CREATE INDEX ix_core_notificacao_usuario_lida_data ON core.tb_notificacao (id_usuario_destino, lida, data_criacao DESC) INCLUDE (tipo, categoria, titulo, icone)",
        "CREATE INDEX ix_core_notificacao_grupo_sistema_data ON core.tb_notificacao (id_grupo_destino, id_sistema, data_criacao DESC)",
        "CREATE INDEX ix_core_notificacao_leitura_usuario ON core.tb_notificacao_leitura (id_usuario, data_leitura DESC)",
        "CREATE INDEX ix_core_publicacao_escopo_tipo_status_data ON core.tb_publicacao (id_sistema, tipo_publicacao, status_publicacao, data_publicacao DESC) INCLUDE (titulo, resumo, prioridade, tipo_audiencia, fixado, exibir_a_partir_de, expira_em)",
        "CREATE UNIQUE INDEX ux_core_publicacao_fonte_id_externo ON core.tb_publicacao (fonte, id_externo) WHERE id_externo IS NOT NULL",
        "CREATE INDEX ix_core_publicacaoleitura_usuario ON core.tb_publicacaoleitura (id_usuario, data_leitura DESC)",
    )
    for comando in comandos:
        op.execute(sa.text(comando))


def downgrade() -> None:
    """Remove a baseline em ordem segura e sem CASCADE."""

    op.drop_constraint(
        "fk_core_sistema_permissao_base",
        "tb_sistema",
        schema=SCHEMA,
        type_="foreignkey",
    )
    for tabela in (
        "tb_notaatualizacaoitem",
        "tb_publicacaonotificacao",
        "tb_publicacaoleitura",
        "tb_publicacaogrupo",
        "tb_publicacao",
        "tb_notificacao_leitura",
        "tb_notificacao",
        "tb_logdetalhe",
        "tb_logacesso",
        "tb_permissaousuario",
        "tb_permissaogrupo",
        "tb_permissao",
        "tb_sistema",
    ):
        op.drop_table(tabela, schema=SCHEMA)
