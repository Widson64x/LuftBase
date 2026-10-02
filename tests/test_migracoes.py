"""Testes do historico Alembic empacotado."""

from io import StringIO

from alembic import command
from alembic.script import ScriptDirectory

from luftbase.migracoes.configuracao import criar_configuracao_alembic


def test_historico_possui_baseline_e_evolucao() -> None:
    configuracao = criar_configuracao_alembic()
    scripts = ScriptDirectory.from_config(configuracao)

    assert scripts.get_base() == "20260915_0001"
    assert scripts.get_current_head() == "20260923_0013"
    assert [revisao.revision for revisao in scripts.walk_revisions()] == [
        "20260923_0013",
        "20260923_0012",
        "20260923_0011",
        "20260922_0010",
        "20260922_0009",
        "20260918_0008",
        "20260917_0007",
        "20260917_0006",
        "20260916_0005",
        "20260916_0004",
        "20260916_0003",
        "20260915_0002",
        "20260915_0001",
    ]


def test_upgrade_offline_recria_o_core_hierarquico_completo() -> None:
    saida = StringIO()
    configuracao = criar_configuracao_alembic()
    configuracao.output_buffer = saida
    configuracao.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://usuario:senha@localhost/luft_web",
    )

    command.upgrade(configuracao, "head", sql=True)

    sql = saida.getvalue().lower()
    assert sql.count("create table core.") == 28
    assert "create table core.alembic_version" in sql
    assert "create table core.tb_sistema" in sql
    assert "create table core.tb_modulo" in sql
    assert "create table core.tb_notaatualizacaoitem" in sql
    assert "create table core.tb_preferenciausuario" in sql
    assert "create table core.tb_revisaocache" in sql
    assert "create table core.tb_sessao" in sql
    assert "create table core.tb_sessao_evento" in sql
    assert "create table core.tb_usuario" in sql
    assert "create table core.tb_logs" in sql
    assert "create table core.tb_logevento" in sql
    assert "create table core.tb_logdetalhe" in sql
    assert "fk_core_sessao_usuario" in sql
    assert "fk_core_logevento_log" in sql
    assert "fk_core_logdetalhe_log" in sql
    assert "fk_core_logdetalhe_logevento" in sql
    assert "parametros_requisicao text" in sql
    assert "fk_core_publicacaonotificacao_notificacao" in sql
    assert "ux_core_publicacao_fonte_id_externo" in sql
    assert "create trigger trg_revisao_autorizacao_tb_permissao" in sql
    assert "fn_incrementar_revisao_autorizacao" in sql
    assert "add column id_correlacao varchar(64)" in sql
    assert "ix_core_logacesso_correlacao" in sql
    assert "ix_core_notificacao_sistema_cursor" in sql
    assert "ix_core_publicacao_sistema_status_cursor" in sql
    assert "fk_core_permissao_modulo" in sql
    assert "fk_core_permissao_pai" in sql
    assert "ux_core_permissao_acesso_sistema" in sql
    assert "add column conceder boolean" in sql
    assert "add column categoria varchar(20)" in sql
    assert sql.count("add column codigo_grupo integer") == 2
    assert "ix_core_logacesso_grupo_data" in sql
    assert "ix_core_logdetalhe_grupo_data" in sql
    assert "ix_core_logdetalhe_sistema_severidade_data" in sql
    assert "add column identificador_aplicacao varchar(80)" in sql
    assert "drop column identificador_aplicacao" in sql
    assert "codigo_usuario" in sql


def test_downgrade_offline_nao_remove_o_schema_core_em_cascata() -> None:
    saida = StringIO()
    configuracao = criar_configuracao_alembic()
    configuracao.output_buffer = saida
    configuracao.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://usuario:senha@localhost/luft_web",
    )

    command.downgrade(configuracao, "head:base", sql=True)

    assert "drop schema core cascade" not in saida.getvalue().lower()
