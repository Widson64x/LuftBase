"""Testes dos caminhos padronizados do Vault."""

import pytest

from luftbase.configuracao import resolver_caminhos_vault
from luftbase.nucleo import ErroConfiguracao


def test_resolve_caminhos_sem_variaveis_completas() -> None:
    caminhos = resolver_caminhos_vault(
        ambiente="development",
        sistema_id=0,
    )

    assert caminhos.sqlserver == "luft/desenvolvimento/sqlserver"
    assert caminhos.sqlserver_diretorio == (
        "luft/desenvolvimento/bancos/sqlserver/conexoes/user.services"
    )
    assert caminhos.postgresql == "luft/desenvolvimento/bancos/postgresql/sistemas/0"
    assert caminhos.sessoes_redis == "luft/desenvolvimento/redis/sessoes"
    assert caminhos.postgresql_conexoes == ("luft/desenvolvimento/bancos/postgresql/conexoes")


def test_rejeita_id_negativo() -> None:
    with pytest.raises(ErroConfiguracao, match="LUFT_SISTEMA_ID"):
        resolver_caminhos_vault(ambiente="desenvolvimento", sistema_id=-1)


def test_rejeita_booleano_como_id() -> None:
    with pytest.raises(ErroConfiguracao, match="LUFT_SISTEMA_ID"):
        resolver_caminhos_vault(ambiente="desenvolvimento", sistema_id=True)


@pytest.mark.parametrize("conexao", ["", "a/b", "..", "com espaco", "-inicio"])
def test_rejeita_nome_de_conexao_invalido(conexao: str) -> None:
    with pytest.raises(ErroConfiguracao, match="conexao"):
        resolver_caminhos_vault(ambiente="desenvolvimento", sistema_id=0, conexao_diretorio=conexao)
