"""Execucao padronizada: configuracao, console e resolucao do alvo."""

from __future__ import annotations

import logging
import sys
import types

import pytest
from flask import Flask

from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.servidor import (
    ConfiguracaoServidor,
    ambiente_de_producao,
    anunciar,
    configurar_console,
    executar_desenvolvimento,
    normalizar_prefixo,
    resolver_aplicacao,
)

_VARIAVEIS = (
    "LUFT_SERVIDOR_HOST", "HOST", "LUFT_SERVIDOR_PORTA", "PORT",
    "LUFT_SERVIDOR_PREFIXO", "ROUTE_PREFIX", "LUFT_SERVIDOR_THREADS",
)


@pytest.fixture(autouse=True)
def _ambiente_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    for nome in _VARIAVEIS:
        monkeypatch.delenv(nome, raising=False)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [(None, ""), ("", ""), ("/", ""), ("Luft-ConnectAir/", "/Luft-ConnectAir"), (" /x ", "/x")],
)
def test_normaliza_prefixo(bruto: str | None, esperado: str) -> None:
    assert normalizar_prefixo(bruto) == esperado


def test_padroes() -> None:
    config = ConfiguracaoServidor.de_ambiente()
    assert (config.host, config.porta, config.prefixo, config.threads) == ("127.0.0.1", 8000, "", 8)
    assert config.url == "http://127.0.0.1:8000"


def test_variaveis_legadas_e_novas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8095")
    monkeypatch.setenv("ROUTE_PREFIX", "/Luft-ConnectAir")
    config = ConfiguracaoServidor.de_ambiente()
    assert config.url == "http://0.0.0.0:8095/Luft-ConnectAir"

    monkeypatch.setenv("LUFT_SERVIDOR_PORTA", "9010")
    monkeypatch.setenv("LUFT_SERVIDOR_PREFIXO", "")
    assert ConfiguracaoServidor.de_ambiente().porta == 9010
    # argumento explicito vence o ambiente
    assert ConfiguracaoServidor.de_ambiente(porta=7000, prefixo="").url == "http://0.0.0.0:7000"


@pytest.mark.parametrize(
    ("nome", "valor"),
    [("PORT", "abc"), ("PORT", "70000"), ("LUFT_SERVIDOR_THREADS", "0")],
)
def test_valores_invalidos(monkeypatch: pytest.MonkeyPatch, nome: str, valor: str) -> None:
    monkeypatch.setenv(nome, valor)
    with pytest.raises(ErroConfiguracao):
        ConfiguracaoServidor.de_ambiente()


def test_console_idempotente_e_silencia_requisicoes() -> None:
    raiz = logging.getLogger()
    antes = list(raiz.handlers)
    try:
        configurar_console()
        configurar_console()
        marcados = [h for h in raiz.handlers if getattr(h, "_luftbase_console", False)]
        assert len(marcados) == 1
        assert logging.getLogger("werkzeug").level == logging.WARNING
        assert logging.getLogger("waitress").level == logging.WARNING
    finally:
        raiz.handlers[:] = antes


def test_resolve_alvo(monkeypatch: pytest.MonkeyPatch) -> None:
    app = Flask("teste")
    modulo = types.ModuleType("modulo_app_teste")
    modulo.app = app  # type: ignore[attr-defined]
    modulo.fabrica = lambda: app  # type: ignore[attr-defined]
    modulo.outro = 42  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "modulo_app_teste", modulo)

    assert resolver_aplicacao("modulo_app_teste:app") is app
    assert resolver_aplicacao("modulo_app_teste:fabrica") is app
    assert resolver_aplicacao(app) is app
    with pytest.raises(ErroConfiguracao):
        resolver_aplicacao("modulo_app_teste")
    with pytest.raises(ErroConfiguracao):
        resolver_aplicacao("modulo_app_teste:outro")


def test_banner_sem_plataforma(caplog: pytest.LogCaptureFixture) -> None:
    app = Flask("teste")
    app.config["LUFT_APLICACAO_VERSAO"] = "1.2.3"
    with caplog.at_level(logging.INFO, logger="luftbase.servidor"):
        anunciar(app, ConfiguracaoServidor(porta=8095, prefixo="/X"))
    texto = caplog.text
    assert "teste v1.2.3" in texto
    assert "http://127.0.0.1:8095/X" in texto


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(None, False), ("desenvolvimento", False), ("producao", True), (" PRODUCAO ", True)],
)
def test_ambiente_de_producao(
    monkeypatch: pytest.MonkeyPatch, valor: str | None, esperado: bool
) -> None:
    if valor is None:
        monkeypatch.delenv("LUFT_AMBIENTE", raising=False)
    else:
        monkeypatch.setenv("LUFT_AMBIENTE", valor)
    assert ambiente_de_producao() is esperado


def test_desenvolvimento_sem_depurador_serve_na_raiz(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[dict[str, object]] = []
    app = Flask("teste")
    monkeypatch.setattr(app, "run", lambda **kwargs: chamadas.append(kwargs))
    monkeypatch.setenv("LUFT_AMBIENTE", "producao")
    monkeypatch.setenv("ROUTE_PREFIX", "/Prefixo")
    monkeypatch.setenv("PORT", "9010")

    executar_desenvolvimento(app)

    assert chamadas == [
        {"host": "127.0.0.1", "port": 9010, "debug": False, "use_reloader": False}
    ]
