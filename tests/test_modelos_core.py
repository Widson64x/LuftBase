"""Testes de compatibilidade entre os modelos e o DDL migrado do core."""

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Text
from sqlalchemy.orm import configure_mappers

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core import (  # noqa: F401
    Log,
    LogAcesso,
    LogAlteracao,
    LogDetalhe,
    LogEvento,
    Modulo,
    NotaAtualizacaoItem,
    Notificacao,
    NotificacaoLeitura,
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    Publicacao,
    PublicacaoGrupo,
    PublicacaoLeitura,
    PublicacaoNotificacao,
    RevisaoCache,
    Sessao,
    Sistema,
    Usuario,
)

TABELAS_ESPERADAS = {
    "tb_notificacao_oculta",
    "tb_alerta",
    "tb_alerta_controle",
    "tb_sistema",
    "tb_permissao",
    "tb_permissaogrupo",
    "tb_permissaousuario",
    "tb_logs",
    "tb_logevento",
    "tb_logdetalhe",
    "tb_notificacao",
    "tb_notificacao_leitura",
    "tb_publicacao",
    "tb_publicacaogrupo",
    "tb_publicacaoleitura",
    "tb_publicacaonotificacao",
    "tb_notaatualizacaoitem",
}

TABELAS_NOVAS = {
    "tb_modulo",
    "tb_revisaocache",
    "tb_sessao",
    "tb_sessao_evento",
    "tb_usuario",
}

INDICES_ESPERADOS = {
    "ix_core_alerta_status",
    "ix_core_alerta_chave",
    "ix_core_sistema_ativo_ordem",
    "ix_core_modulo_sistema_ordem",
    "ix_core_permissao_sistema",
    "ix_core_permissao_modulo_ordem",
    "ix_core_permissao_pai",
    "ux_core_permissao_acesso_sistema",
    "ix_core_permissaogrupo_permissao",
    "ix_core_permissaogrupo_grupo",
    "ix_core_permissaousuario_permissao",
    "ix_core_permissaousuario_usuario",
    "ix_core_logs_data",
    "ix_core_logs_sistema_data",
    "ix_core_logs_usuario_data",
    "ix_core_logs_grupo_data",
    "ix_core_logs_correlacao",
    "ix_core_logevento_log",
    "ix_core_logevento_sistema_data",
    "ix_core_logevento_usuario_data",
    "ix_core_logevento_grupo_data",
    "ix_core_logevento_correlacao",
    "ix_core_logevento_sistema_severidade_data",
    "ix_core_logevento_recurso",
    "ix_core_logdetalhe_log",
    "ix_core_logdetalhe_evento",
    "ix_core_logdetalhe_tipo_data",
    "ix_core_notificacao_expiracao",
    "ix_core_notificacao_sistema_data",
    "ix_core_notificacao_usuario_lida_data",
    "ix_core_notificacao_grupo_sistema_data",
    "ix_core_notificacao_leitura_usuario",
    "ix_core_publicacao_escopo_tipo_status_data",
    "ux_core_publicacao_fonte_id_externo",
    "ix_core_publicacaogrupo_grupo_publicacao",
    "ix_core_publicacaoleitura_usuario",
    "ix_core_publicacaonotificacao_notificacao",
    "ix_core_nota_item_publicacao_ordem",
    "ix_core_sessao_status_expira",
    "ix_core_sessao_usuario",
    "ix_core_sessao_sistema",
    "ix_core_sessao_ultima_atividade",
    "ix_core_sessaoevento_sessao",
    "ix_core_sessaoevento_usuario_data",
    "ix_core_sessaoevento_data",
    "ix_core_usuario_email",
    "ix_core_usuario_grupo",
    "ix_core_usuario_online",
    "ix_core_usuario_ultimo_acesso",
}

CHAVES_ESTRANGEIRAS_ESPERADAS = {
    "fk_core_modulo_sistema",
    "fk_core_permissao_sistema",
    "fk_core_permissao_modulo",
    "fk_core_permissao_pai",
    "fk_core_permissaogrupo_permissao",
    "fk_core_permissaousuario_permissao",
    "fk_core_permissaousuario_usuario",
    "fk_core_logs_sistema",
    "fk_core_logs_usuario",
    "fk_core_logevento_sistema",
    "fk_core_logevento_log",
    "fk_core_logevento_usuario",
    "fk_core_logdetalhe_log",
    "fk_core_logdetalhe_logevento",
    "fk_core_notificacao_sistema",
    "fk_core_notificacao_usuario",
    "fk_core_notificacao_leitura_notificacao",
    "fk_core_notificacaoleitura_usuario",
    "fk_core_publicacao_sistema",
    "fk_core_publicacao_criadopor",
    "fk_core_publicacao_atualizadopor",
    "fk_core_publicacaogrupo_publicacao",
    "fk_core_publicacaoleitura_publicacao",
    "fk_core_publicacaoleitura_usuario",
    "fk_core_publicacaonotificacao_publicacao",
    "fk_core_publicacaonotificacao_notificacao",
    "fk_core_nota_item_publicacao",
    "fk_core_sessao_sistema",
    "fk_core_sessao_usuario",
    "fk_core_sessaoevento_sessao",
    "fk_core_sessaoevento_sistema",
    "fk_core_sessaoevento_usuario",
    "fk_core_usuario_sessao_atual",
    "fk_core_notificacaooculta_notificacao",
    "fk_core_notificacaooculta_usuario",
}


def test_base_contem_o_core_completo_incluindo_modulos() -> None:
    tabelas = set(BaseLuft.metadata.tables)

    assert {f"core.{nome}" for nome in TABELAS_ESPERADAS}.issubset(tabelas)
    assert tabelas == {f"core.{nome}" for nome in TABELAS_ESPERADAS | TABELAS_NOVAS}
    assert all(tabela.schema == "core" for tabela in BaseLuft.metadata.tables.values())


def test_mapeadores_e_relacionamentos_sao_validos() -> None:
    configure_mappers()


def test_campos_que_provocaram_truncamento_sao_texto() -> None:
    tabela = BaseLuft.metadata.tables["core.tb_logs"]

    assert isinstance(tabela.c.parametros_requisicao.type, Text)
    assert isinstance(tabela.c.resposta_acao.type, Text)
    assert isinstance(BaseLuft.metadata.tables["core.tb_publicacao"].c.conteudo.type, Text)


def test_indices_correspondem_ao_ddl_migrado() -> None:
    indices = {
        indice.name
        for tabela in BaseLuft.metadata.tables.values()
        for indice in tabela.indexes
        if isinstance(indice, Index)
    }

    assert indices == INDICES_ESPERADOS


def test_chaves_estrangeiras_correspondem_ao_ddl_migrado() -> None:
    chaves = {
        restricao.name
        for tabela in BaseLuft.metadata.tables.values()
        for restricao in tabela.constraints
        if isinstance(restricao, ForeignKeyConstraint)
    }

    assert chaves == CHAVES_ESTRANGEIRAS_ESPERADAS


def test_checks_preservam_nomes_fisicos() -> None:
    checks = {
        restricao.name
        for tabela in BaseLuft.metadata.tables.values()
        for restricao in tabela.constraints
        if isinstance(restricao, CheckConstraint)
    }

    assert checks == {
        "ck_core_alerta_status",
        "ck_core_logs_duracao",
        "ck_core_logs_status_http",
        "ck_core_logevento_severidade",
        "ck_core_logdetalhe_tipo_alteracao",
        "ck_core_sistema_categoria",
        "ck_core_sistema_ordem",
        "ck_core_modulo_codigo",
        "ck_core_modulo_ordem",
        "ck_core_permissao_chave",
        "ck_core_permissao_acao",
        "ck_core_permissao_pai_distinto",
        "ck_core_permissao_ordem",
        "ck_core_permissaogrupo_codigo",
        "ck_core_permissaousuario_codigo",
        "ck_core_notificacao_tipo",
        "ck_core_notificacao_categoria",
        "ck_core_publicacao_tipo",
        "ck_core_publicacao_status",
        "ck_core_publicacao_audiencia",
        "ck_core_publicacao_prioridade",
        "ck_core_publicacao_fonte",
        "ck_core_publicacao_versao",
        "ck_core_publicacao_vigencia",
        "ck_core_publicacao_metadados_json",
        "ck_core_nota_item_tipo",
        "ck_core_revisaocache_nao_negativa",
        "ck_core_sessao_status",
        "ck_core_sessaoevento_tipo",
    }


def test_ids_externos_do_luftinforma_nao_possuem_fk_local() -> None:
    colunas_logicas = (
        PermissaoGrupo.codigo_usuariogrupo,
        Log.codigo_grupo,
        LogEvento.codigo_grupo,
        Notificacao.id_grupo_destino,
        PublicacaoGrupo.id_grupo,
    )

    assert all(not coluna.property.columns[0].foreign_keys for coluna in colunas_logicas)


def test_tabela_usuario_e_chaves_estrangeiras() -> None:
    tabela_usuario = BaseLuft.metadata.tables["core.tb_usuario"]
    assert tabela_usuario.c.codigo_usuario.primary_key is True
    assert tabela_usuario.c.login_usuario.nullable is False
    assert tabela_usuario.c.status_online.server_default is not None
    assert tabela_usuario.c.tema_preferido.server_default is not None
    assert tabela_usuario.c.modo_tema.server_default is not None

    colunas_usuario = (
        PermissaoUsuario.codigo_usuario,
        Notificacao.id_usuario_destino,
        NotificacaoLeitura.id_usuario,
        PublicacaoLeitura.id_usuario,
        Publicacao.criado_por_id,
        Publicacao.atualizado_por_id,
        Log.codigo_usuario,
        LogEvento.codigo_usuario,
    )
    for col in colunas_usuario:
        fks = list(col.property.columns[0].foreign_keys)
        assert len(fks) == 1, f"Coluna {col} deveria ter exatamente 1 FK"
        assert fks[0].target_fullname == "core.tb_usuario.codigo_usuario"


def test_alteracao_herda_identidade_do_detalhe_pai() -> None:
    assert LogDetalhe.__table__.c.id_logdetalhe.nullable is False
    assert LogDetalhe.__table__.c.id_logevento.nullable is False
    assert "codigo_usuario" not in LogDetalhe.__table__.c
    assert "id_sistema" not in LogDetalhe.__table__.c


def test_modulo_e_permissao_pertencem_ao_mesmo_sistema() -> None:
    assert Modulo.__table__.c.id_sistema.nullable is False
    assert Permissao.__table__.c.id_modulo.nullable is False
    assert Permissao.__table__.c.id_permissao_pai.nullable is True


def test_preferencia_separa_familia_visual_de_modo_claro_escuro() -> None:
    assert Usuario.__table__.c.tema_preferido.server_default is not None
    assert Usuario.__table__.c.modo_tema.server_default is not None
    assert RevisaoCache.__table__.c.revisao.server_default is not None
