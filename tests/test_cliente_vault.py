"""Testes do adaptador Vault sem realizar chamadas de rede."""

import pytest

from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.nucleo.excecoes import (
    AutenticacaoCofreInvalida,
    ErroCofre,
    SegredoNaoEncontrado,
)


class InvalidPath(Exception):
    """Simula o erro de caminho inexistente do HVAC."""


class LeitorFalso:
    """Simula a API KV v2 encadeada do HVAC."""

    def __init__(self, resposta: object = None, erro: Exception | None = None) -> None:
        self.resposta = resposta
        self.erro = erro
        self.chamada: dict[str, object] = {}

    def read_secret_version(self, **argumentos: object) -> object:
        self.chamada = argumentos
        if self.erro:
            raise self.erro
        return self.resposta


class ClienteFalso:
    """Cliente HVAC minimo suficiente para o contrato do adaptador."""

    def __init__(self, autenticado: bool, leitor: LeitorFalso) -> None:
        self._autenticado = autenticado
        self.secrets = type("Segredos", (), {})()
        self.secrets.kv = type("Kv", (), {})()
        self.secrets.kv.v2 = leitor

    def is_authenticated(self) -> bool:
        return self._autenticado


def test_le_segredo_kv_v2() -> None:
    leitor = LeitorFalso({"data": {"data": {"host": "db"}}})
    cliente = ClienteVaultHvac(
        "http://vault.interno",
        Segredo("token"),
        cliente=ClienteFalso(True, leitor),
    )

    dados = cliente.ler_segredo("luft/desenvolvimento/postgresql/app")

    assert dados == {"host": "db"}
    assert leitor.chamada["path"] == "luft/desenvolvimento/postgresql/app"
    assert leitor.chamada["mount_point"] == "secret"


def test_rejeita_token_nao_autenticado() -> None:
    cliente = ClienteVaultHvac(
        "http://vault.interno",
        Segredo("token"),
        cliente=ClienteFalso(False, LeitorFalso()),
    )

    with pytest.raises(AutenticacaoCofreInvalida):
        cliente.ler_segredo("luft/desenvolvimento/postgresql/app")


def test_normaliza_caminho_inexistente() -> None:
    cliente = ClienteVaultHvac(
        "http://vault.interno",
        Segredo("token"),
        cliente=ClienteFalso(True, LeitorFalso(erro=InvalidPath())),
    )

    with pytest.raises(SegredoNaoEncontrado, match="nao existe"):
        cliente.ler_segredo("luft/desenvolvimento/postgresql/app")


@pytest.mark.parametrize("caminho", ["", "/", "luft//app", "luft/../app"])
def test_rejeita_caminho_perigoso(caminho: str) -> None:
    cliente = ClienteVaultHvac(
        "http://vault.interno",
        Segredo("token"),
        cliente=ClienteFalso(True, LeitorFalso()),
    )

    with pytest.raises(ErroCofre, match="caminho"):
        cliente.ler_segredo(caminho)


def test_rejeita_payload_malformado() -> None:
    cliente = ClienteVaultHvac(
        "http://vault.interno",
        Segredo("token"),
        cliente=ClienteFalso(True, LeitorFalso({"data": {}})),
    )

    with pytest.raises(ErroCofre, match="payload"):
        cliente.ler_segredo("luft/desenvolvimento/postgresql/app")
