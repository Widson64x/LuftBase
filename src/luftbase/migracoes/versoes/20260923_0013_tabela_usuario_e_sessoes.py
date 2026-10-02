"""Cria a tabela espelho de usuarios (tb_usuario) e reestrutura sessoes e FKs.

Revision ID: 20260923_0013
Revises: 20260923_0012

Esta revisao:
1. Remove core.tb_preferenciausuario (incorporada em core.tb_usuario).
2. Adiciona a coluna schema_aplicacao em core.tb_sistema.
3. Cria core.tb_usuario com codigo_usuario como PK (espelhado do LuftInforma).
4. Recria core.tb_sessao e core.tb_sessao_evento vinculadas a tb_usuario.
5. Estabelece Foreign Keys fisicas para core.tb_usuario(codigo_usuario) em
   todas as tabelas que referenciam usuarios (permissao, notificacoes, publicacoes, logs).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260923_0013"
down_revision = "20260923_0012"
branch_labels = None
depends_on = None

SCHEMA = "core"
DATA_HORA_LOCAL = sa.text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP = postgresql.TIMESTAMP(timezone=False, precision=3)


def _identidade() -> sa.Identity:
    return sa.Identity(always=False)


def upgrade() -> None:
    """Aplica criacao de tb_usuario, atualizacao de tb_sistema e reestruturacao de sessoes."""

    # 1. Limpeza de tabelas legadas / substituídas
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_preferenciausuario CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_sessao_evento CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_sessao CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS core.tb_usuario CASCADE"))

    # 2. Schema aplicacao em core.tb_sistema
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'core'
                      AND table_name = 'tb_sistema'
                      AND column_name = 'schema_aplicacao'
                ) THEN
                    ALTER TABLE core.tb_sistema ADD COLUMN schema_aplicacao VARCHAR(63);
                END IF;
            END $$;
            """
        )
    )

    # 3. Criar core.tb_usuario (espelho corporativo do LuftInforma)
    op.create_table(
        "tb_usuario",
        sa.Column("codigo_usuario", sa.Integer(), nullable=False),
        sa.Column("login_usuario", sa.String(100), nullable=False),
        sa.Column("nome_usuario", sa.String(255), nullable=False),
        sa.Column("email_usuario", sa.String(255)),
        sa.Column("codigo_usuariogrupo", sa.Integer()),
        sa.Column("sigla_usuariogrupo", sa.String(100)),
        sa.Column("descricao_usuariogrupo", sa.String(255)),
        sa.Column("foto_perfil", sa.Text()),
        sa.Column("status_online", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("id_sessao_atual", sa.String(128)),
        sa.Column("telefone_usuario", sa.String(50)),
        sa.Column("celular_usuario", sa.String(50)),
        sa.Column("cargo_usuario", sa.String(150)),
        sa.Column("departamento_usuario", sa.String(150)),
        sa.Column("unidade_filial", sa.String(150)),
        sa.Column("codigo_empresa", sa.Integer()),
        sa.Column("codigo_filial", sa.Integer()),
        sa.Column("gestor_imediato", sa.String(150)),
        sa.Column("codigo_gestor", sa.Integer()),
        sa.Column("ultimo_acesso", TIMESTAMP),
        sa.Column("ultimo_ip", sa.String(50)),
        sa.Column("ultimo_user_agent", sa.String(500)),
        sa.Column("total_logins", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tema_preferido", sa.String(30), server_default="luft", nullable=False),
        sa.Column("modo_tema", sa.String(20), server_default="SISTEMA", nullable=False),
        sa.Column("idioma", sa.String(10), server_default="pt-BR", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("bloqueado", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("motivo_bloqueio", sa.String(255)),
        sa.Column("metadados_json", postgresql.JSONB()),
        sa.Column("criado_em", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("atualizado_em", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.PrimaryKeyConstraint("codigo_usuario"),
        sa.UniqueConstraint("login_usuario", name="uq_core_usuario_login"),
        schema=SCHEMA,
    )

    # 4. Criar core.tb_sessao
    op.create_table(
        "tb_sessao",
        sa.Column("id_sessao", sa.String(128), nullable=False),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("dados_sessao", sa.Text()),
        sa.Column("status", sa.String(20), server_default="ATIVA", nullable=False),
        sa.Column("total_renovacoes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("criada_em", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("ultima_atividade", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("expira_em", TIMESTAMP, nullable=False),
        sa.Column("encerrada_em", TIMESTAMP),
        sa.Column("motivo_encerramento", sa.String(100)),
        sa.CheckConstraint(
            "status IN ('ATIVA', 'FINALIZADA', 'EXPIRADA', 'REVOGADA')",
            name="ck_core_sessao_status",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_sessao_sistema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["codigo_usuario"],
            ["core.tb_usuario.codigo_usuario"],
            name="fk_core_sessao_usuario",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id_sessao"),
        schema=SCHEMA,
    )

    # 5. Criar core.tb_sessao_evento
    op.create_table(
        "tb_sessao_evento",
        sa.Column("id_evento_sessao", sa.BigInteger(), _identidade(), nullable=False),
        sa.Column("id_sessao", sa.String(128), nullable=False),
        sa.Column("id_sistema", sa.Integer()),
        sa.Column("codigo_usuario", sa.Integer()),
        sa.Column("login_usuario", sa.String(100)),
        sa.Column("tipo_evento", sa.String(50), nullable=False),
        sa.Column("ip_origem", sa.String(50)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("data_hora", TIMESTAMP, server_default=DATA_HORA_LOCAL, nullable=False),
        sa.Column("detalhes", sa.Text()),
        sa.CheckConstraint(
            "tipo_evento IN ('INICIO', 'RENOVACAO', 'LOGOUT', 'TIMEOUT', 'REVOGACAO')",
            name="ck_core_sessaoevento_tipo",
        ),
        sa.ForeignKeyConstraint(
            ["id_sessao"],
            ["core.tb_sessao.id_sessao"],
            name="fk_core_sessaoevento_sessao",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["id_sistema"],
            ["core.tb_sistema.id_sistema"],
            name="fk_core_sessaoevento_sistema",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["codigo_usuario"],
            ["core.tb_usuario.codigo_usuario"],
            name="fk_core_sessaoevento_usuario",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id_evento_sessao"),
        schema=SCHEMA,
    )

    # 6. FK circular adiada: tb_usuario.id_sessao_atual -> tb_sessao.id_sessao
    op.create_foreign_key(
        "fk_core_usuario_sessao_atual",
        "tb_usuario",
        "tb_sessao",
        ["id_sessao_atual"],
        ["id_sessao"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )

    # 7. Foreign Keys das tabelas existentes apontando para core.tb_usuario(codigo_usuario)
    _criar_chaves_estrangeiras_usuario()

    # 8. Indices
    _criar_indices()

    # 9. Conceder Privilegios
    _conceder_privilegios()


def _criar_chaves_estrangeiras_usuario() -> None:
    fks = (
        (
            "fk_core_permissaousuario_usuario",
            "tb_permissaousuario",
            ["codigo_usuario"],
            "CASCADE",
        ),
        (
            "fk_core_notificacao_usuario",
            "tb_notificacao",
            ["id_usuario_destino"],
            "CASCADE",
        ),
        (
            "fk_core_notificacaoleitura_usuario",
            "tb_notificacao_leitura",
            ["id_usuario"],
            "CASCADE",
        ),
        (
            "fk_core_publicacaoleitura_usuario",
            "tb_publicacaoleitura",
            ["id_usuario"],
            "CASCADE",
        ),
        (
            "fk_core_publicacao_criadopor",
            "tb_publicacao",
            ["criado_por_id"],
            "SET NULL",
        ),
        (
            "fk_core_publicacao_atualizadopor",
            "tb_publicacao",
            ["atualizado_por_id"],
            "SET NULL",
        ),
        (
            "fk_core_logs_usuario",
            "tb_logs",
            ["codigo_usuario"],
            "SET NULL",
        ),
        (
            "fk_core_logevento_usuario",
            "tb_logevento",
            ["codigo_usuario"],
            "SET NULL",
        ),
    )
    for nome_fk, tabela_origem, colunas, ondelete in fks:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = '{nome_fk}'
                    ) THEN
                        ALTER TABLE core.{tabela_origem}
                        ADD CONSTRAINT {nome_fk}
                        FOREIGN KEY ({", ".join(colunas)})
                        REFERENCES core.tb_usuario (codigo_usuario)
                        ON DELETE {ondelete};
                    END IF;
                END $$;
                """
            )
        )


def _criar_indices() -> None:
    comandos = (
        "CREATE INDEX IF NOT EXISTS ix_core_usuario_email ON core.tb_usuario (email_usuario)",
        "CREATE INDEX IF NOT EXISTS ix_core_usuario_grupo ON core.tb_usuario (codigo_usuariogrupo)",
        "CREATE INDEX IF NOT EXISTS ix_core_usuario_online ON core.tb_usuario (status_online)",
        "CREATE INDEX IF NOT EXISTS ix_core_usuario_ultimo_acesso ON core.tb_usuario (ultimo_acesso DESC NULLS LAST)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessao_status_expira ON core.tb_sessao (status, expira_em)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessao_usuario ON core.tb_sessao (codigo_usuario)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessao_sistema ON core.tb_sessao (id_sistema)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessao_ultima_atividade ON core.tb_sessao (ultima_atividade DESC)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessaoevento_sessao ON core.tb_sessao_evento (id_sessao)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessaoevento_usuario_data ON core.tb_sessao_evento (codigo_usuario, data_hora DESC)",
        "CREATE INDEX IF NOT EXISTS ix_core_sessaoevento_data ON core.tb_sessao_evento (data_hora DESC)",
    )
    for comando in comandos:
        op.execute(sa.text(comando))


def _conceder_privilegios() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                -- Role de seguranca administrativa
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_core_security_admin') THEN
                    GRANT ALL PRIVILEGES ON core.tb_usuario, core.tb_sessao, core.tb_sessao_evento TO luft_core_security_admin;
                    GRANT USAGE, SELECT ON SEQUENCE core.tb_sessao_evento_id_evento_sessao_seq TO luft_core_security_admin;
                END IF;

                -- Role de autenticacao (leitura de usuario e sessoes)
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_core_auth_ro') THEN
                    GRANT SELECT ON core.tb_usuario, core.tb_sessao TO luft_core_auth_ro;
                END IF;

                -- Role de preferencias (leitura e atualizacao de tema/modo do usuario)
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_core_preferences_rw') THEN
                    GRANT SELECT, UPDATE (tema_preferido, modo_tema, idioma) ON core.tb_usuario TO luft_core_preferences_rw;
                END IF;

                -- App de runtime do workspace
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'luft_workspace_app') THEN
                    GRANT SELECT, INSERT, UPDATE, DELETE ON core.tb_usuario, core.tb_sessao, core.tb_sessao_evento TO luft_workspace_app;
                    GRANT USAGE, SELECT ON SEQUENCE core.tb_sessao_evento_id_evento_sessao_seq TO luft_workspace_app;
                END IF;
            END $$;
            """
        )
    )


def downgrade() -> None:
    """Reverte para a revisao 0012."""

    op.drop_constraint("fk_core_usuario_sessao_atual", "tb_usuario", schema=SCHEMA, type_="foreignkey")
    for fk, tabela in (
        ("fk_core_permissaousuario_usuario", "tb_permissaousuario"),
        ("fk_core_notificacao_usuario", "tb_notificacao"),
        ("fk_core_notificacaoleitura_usuario", "tb_notificacao_leitura"),
        ("fk_core_publicacaoleitura_usuario", "tb_publicacaoleitura"),
        ("fk_core_publicacao_criadopor", "tb_publicacao"),
        ("fk_core_publicacao_atualizadopor", "tb_publicacao"),
        ("fk_core_logs_usuario", "tb_logs"),
        ("fk_core_logevento_usuario", "tb_logevento"),
    ):
        op.drop_constraint(fk, tabela, schema=SCHEMA, type_="foreignkey")

    op.drop_table("tb_sessao_evento", schema=SCHEMA)
    op.drop_table("tb_sessao", schema=SCHEMA)
    op.drop_table("tb_usuario", schema=SCHEMA)
    op.drop_column("tb_sistema", "schema_aplicacao", schema=SCHEMA)
