"""Testes do contrato tipado de configuracao."""

import pytest

from luftbase.configuracao import Ambiente, ConfiguracaoLuftBase
from luftbase.nucleo.excecoes import ErroConfiguracao


def test_carrega_configuracao_canonica() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "development",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_NAMESPACE": "luft",
            "LUFT_VAULT_TOKEN": "nao-exibir",
        }
    )

    assert configuracao.aplicacao.identificador == ""
    assert configuracao.aplicacao.nome == ""
    assert configuracao.aplicacao.ambiente is Ambiente.DESENVOLVIMENTO
    assert configuracao.aplicacao.sistema_id == 0
    assert "nao-exibir" not in repr(configuracao)


def test_identidade_de_exibicao_pode_ser_resolvida_depois_do_bootstrap() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_SISTEMA_ID": "0",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
        }
    )

    assert configuracao.aplicacao.identificador == ""
    assert configuracao.aplicacao.nome == ""
    assert configuracao.aplicacao.sistema_id == 0


def test_sistema_id_e_obrigatorio_no_bootstrap() -> None:
    with pytest.raises(ErroConfiguracao, match="LUFT_SISTEMA_ID"):
        ConfiguracaoLuftBase.de_mapeamento(
            {
                "LUFT_AMBIENTE": "desenvolvimento",
                "LUFT_VAULT_ENDERECO": "http://vault:8200",
                "LUFT_LDAP_SERVIDOR": "ad.luft",
                "LUFT_LDAP_DOMINIO": "luftfarma",
            }
        )


def test_aceita_aliases_durante_a_transicao() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "SISTEMA_ID": "2",
            "APP_NAME": "Luft Control",
            "APP_ENV": "prod",
            "VAULT_ADDR": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
        }
    )

    assert configuracao.aplicacao.ambiente is Ambiente.PRODUCAO
    assert configuracao.aplicacao.sistema_id == 2


def test_sobreposicao_tem_precedencia_sobre_ambiente(monkeypatch) -> None:
    monkeypatch.setenv("LUFT_SISTEMA_ID", "2")
    monkeypatch.setenv("LUFT_AMBIENTE", "homologacao")
    monkeypatch.setenv("LUFT_VAULT_ENDERECO", "http://vault:8200")
    monkeypatch.setenv("LUFT_LDAP_SERVIDOR", "ad.luft")
    monkeypatch.setenv("LUFT_LDAP_DOMINIO", "luftfarma")
    configuracao = ConfiguracaoLuftBase.de_ambiente(
        {"LUFT_SISTEMA_ID": "3"},
    )

    assert configuracao.aplicacao.sistema_id == 3
    assert configuracao.aplicacao.nome == ""


def _configuracao_inicializavel(**alteracoes: object) -> ConfiguracaoLuftBase:
    dados: dict[str, object] = {
        "LUFT_SISTEMA_ID": "0",
        "LUFT_APLICACAO_VERSAO": "1.0.0",
        "LUFT_AMBIENTE": "producao",
        "LUFT_VAULT_ENDERECO": "http://vault:8200",
        "LUFT_LDAP_SERVIDOR": "ad.luft",
        "LUFT_LDAP_DOMINIO": "luftfarma",
        "LUFT_VAULT_TOKEN": "token-protegido",
        "LUFT_TOKEN_ACESSO": "chave-do-ambiente",
    }
    dados.update(alteracoes)
    return ConfiguracaoLuftBase.de_mapeamento(dados)


def test_valida_configuracao_completa_de_producao() -> None:
    _configuracao_inicializavel().validar_para_inicializacao()


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("LUFT_VAULT_ENDERECO", "vault-sem-esquema", "URL HTTP"),
        ("LUFT_VAULT_TOKEN", "", "LUFT_VAULT_TOKEN"),
        ("LUFT_TOKEN_ACESSO", "", "LUFT_TOKEN_ACESSO"),
        ("LUFT_VAULT_TOKEN", "<TOKEN>", "placeholders"),
        ("LUFT_APLICACAO_VERSAO", "", "VERSAO"),
    ],
)
def test_rejeita_configuracao_incompleta_de_producao(
    campo: str,
    valor: object,
    mensagem: str,
) -> None:
    with pytest.raises(ErroConfiguracao, match=mensagem):
        _configuracao_inicializavel(**{campo: valor}).validar_para_inicializacao()


def test_desenvolvimento_nao_exige_versao() -> None:
    configuracao = _configuracao_inicializavel(
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_APLICACAO_VERSAO="",
    )

    configuracao.validar_para_inicializacao()


def test_centraliza_politica_de_sessao_e_forca_cookie_seguro_em_producao() -> None:
    configuracao = _configuracao_inicializavel(
        LUFT_SESSAO_COOKIE_SEGURO="false",
        LUFT_SESSAO_COOKIE_DOMINIO=".luftfarma.com.br",
        LUFT_SESSAO_TTL_MINUTOS="120",
    )

    assert configuracao.sessao.cookie_seguro is True
    assert configuracao.sessao.dominio_cookie == ".luftfarma.com.br"
    assert configuracao.sessao.ttl_minutos == 120
    assert configuracao.autorizacao.ttl_resultado_segundos == 300


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("LUFT_LDAP_TRANSPORTE", "texto-puro", "ldaps ou starttls"),
        ("LUFT_SESSAO_COOKIE_SEGURO", "talvez", "true ou false"),
        ("LUFT_SESSAO_TTL_MINUTOS", "0", "entre 1 e 10080"),
        ("LUFT_AUTORIZACAO_TTL_SEGUNDOS", "4", "entre 5 e 3600"),
        ("LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS", "61", "entre 1 e 60"),
        ("LUFT_AUTORIZACAO_MAX_CHAVES", "0", "entre 1 e 500"),
    ],
)
def test_rejeita_configuracao_de_identidade_invalida(
    campo: str,
    valor: object,
    mensagem: str,
) -> None:
    with pytest.raises(ErroConfiguracao, match=mensagem):
        _configuracao_inicializavel(**{campo: valor})
