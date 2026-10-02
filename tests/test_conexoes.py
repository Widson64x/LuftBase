"""Testes da criacao segura de URLs e engines."""

from typing import Any

import pytest

from luftbase.infraestrutura.banco import conexoes
from luftbase.infraestrutura.banco.conexoes import (
    ESQUEMA_LOGICO_APLICACAO,
    ConfiguracaoPool,
    ConstrutorEngines,
)
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco


def _credencial(tipo: TipoBanco, esquema: str | None = None) -> CredencialBanco:
    return CredencialBanco(
        tipo=tipo,
        host="banco.interno",
        porta=5432 if tipo is TipoBanco.POSTGRESQL else 1433,
        nome_banco="luft_web" if tipo is TipoBanco.POSTGRESQL else "intec",
        usuario="svc_aplicacao",
        senha=Segredo("p@ss:/?#[]"),
        esquema=esquema,
    )


def test_url_postgresql_e_escapada_e_oculta_senha() -> None:
    url = ConstrutorEngines().criar_url(_credencial(TipoBanco.POSTGRESQL, "luft_workspace"))

    assert url.drivername == "postgresql+psycopg"
    assert "p@ss:/?#[]" not in str(url)
    assert "p%40ss%3A%2F%3F%23%5B%5D" in url.render_as_string(hide_password=False)


def test_url_sqlserver_define_driver_seguro() -> None:
    url = ConstrutorEngines().criar_url(_credencial(TipoBanco.SQLSERVER))

    assert url.drivername == "mssql+pyodbc"
    assert url.query["driver"] == "ODBC Driver 18 for SQL Server"
    assert url.query["Encrypt"] == "yes"


def test_engine_usa_pool_limitado_e_pre_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    argumentos: dict[str, Any] = {}

    def criar_engine_falsa(url: object, **opcoes: object) -> object:
        argumentos["url"] = url
        argumentos.update(opcoes)
        return object()

    monkeypatch.setattr(conexoes, "create_engine", criar_engine_falsa)
    construtor = ConstrutorEngines(
        ConfiguracaoPool(
            tamanho=7,
            excedentes=2,
            reciclagem_segundos=900,
            timeout_segundos=12,
        )
    )

    construtor.criar(_credencial(TipoBanco.POSTGRESQL, "luft_workspace"))

    assert argumentos["pool_pre_ping"] is True
    assert argumentos["pool_size"] == 7
    assert argumentos["max_overflow"] == 2
    assert argumentos["pool_recycle"] == 900
    assert argumentos["pool_timeout"] == 12


def test_engine_aplicacao_recebe_schema_translate_map() -> None:
    engine = object()
    opcoes: dict[str, object] = {}

    class EngineFalsa:
        def execution_options(self, **argumentos: object) -> object:
            opcoes.update(argumentos)
            return engine

    resultado = ConstrutorEngines().para_aplicacao(  # type: ignore[arg-type]
        EngineFalsa(),
        "luft_workspace",
    )

    assert resultado is engine
    assert opcoes["schema_translate_map"] == {ESQUEMA_LOGICO_APLICACAO: "luft_workspace"}


@pytest.mark.parametrize(
    ("argumentos", "mensagem"),
    [
        ({"tamanho": 0}, "tamanho"),
        ({"excedentes": -1}, "excedentes"),
        ({"timeout_segundos": 0}, "timeout"),
    ],
)
def test_rejeita_configuracao_invalida_de_pool(argumentos: dict[str, int], mensagem: str) -> None:
    with pytest.raises(ValueError, match=mensagem):
        ConfiguracaoPool(**argumentos)
