"""Avaliador em segundo plano (opt-in) e comandos `luftbase alertas`."""

from __future__ import annotations

import importlib
import threading
from types import SimpleNamespace
from typing import Any

import pytest
from flask import Flask

from luftbase.observabilidade import alertas, avaliador_alertas
from luftbase.observabilidade.avaliador_alertas import (
    AvaliadorEmSegundoPlano,
    alertas_ativos,
    iniciar_se_ativo,
    intervalo_configurado,
)

# `luftbase.cli.alertas` e tanto o modulo quanto o grupo exportado pelo pacote.
cli_alertas = importlib.import_module("luftbase.cli.alertas")


def test_desligado_por_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LUFT_ALERTAS_ATIVO", raising=False)

    assert alertas_ativos() is False
    assert iniciar_se_ativo(object(), object()) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("valor", ["true", "TRUE", "1", "sim"])
def test_variavel_liga(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    monkeypatch.setenv("LUFT_ALERTAS_ATIVO", valor)

    assert alertas_ativos() is True


@pytest.mark.parametrize("valor", ["false", "0", "", "talvez"])
def test_outros_valores_nao_ligam(monkeypatch: pytest.MonkeyPatch, valor: str) -> None:
    monkeypatch.setenv("LUFT_ALERTAS_ATIVO", valor)

    assert alertas_ativos() is False


def test_intervalo_tem_minimo_e_tolera_lixo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUFT_ALERTAS_INTERVALO_SEGUNDOS", "2")
    assert intervalo_configurado() == 15
    monkeypatch.setenv("LUFT_ALERTAS_INTERVALO_SEGUNDOS", "abc")
    assert intervalo_configurado() == 60
    monkeypatch.setenv("LUFT_ALERTAS_INTERVALO_SEGUNDOS", "120")
    assert intervalo_configurado() == 120


def test_thread_chama_o_avaliador_e_sobrevive_a_erros(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = threading.Event()
    contagem = {"n": 0}

    def falso(bancos: Any, email: Any) -> Any:
        contagem["n"] += 1
        if contagem["n"] == 1:
            raise RuntimeError("primeira falha")
        chamadas.set()
        return SimpleNamespace(erros=())

    monkeypatch.setattr(avaliador_alertas, "avaliar", falso)
    avaliador = AvaliadorEmSegundoPlano(object(), object(), intervalo_segundos=0)  # type: ignore[arg-type]
    # Sem esperar os 5 s da subida: o teste so quer ver o laco rodar.
    monkeypatch.setattr(avaliador._parar, "wait", lambda _s=None: avaliador._parar.is_set())  # noqa: SLF001

    avaliador.iniciar()
    try:
        assert chamadas.wait(5), "o avaliador nao rodou de novo depois do erro"
    finally:
        avaliador.parar()

    assert contagem["n"] >= 2


def test_iniciar_duas_vezes_nao_cria_duas_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(avaliador_alertas, "avaliar", lambda *_a: SimpleNamespace(erros=()))
    avaliador = AvaliadorEmSegundoPlano(object(), object(), intervalo_segundos=3600)  # type: ignore[arg-type]

    avaliador.iniciar()
    primeira = avaliador._thread  # noqa: SLF001
    avaliador.iniciar()
    try:
        assert avaliador._thread is primeira  # noqa: SLF001
    finally:
        avaliador.parar()


def _executar_cli(monkeypatch: pytest.MonkeyPatch, args: list[str], resultado: Any) -> Any:
    estado = SimpleNamespace(bancos=object(), email=object())
    monkeypatch.setattr(cli_alertas, "obter_luftbase", lambda: estado)
    monkeypatch.setattr(alertas, "avaliar", lambda *_a, **_k: resultado)
    app = Flask(__name__)
    app.cli.add_command(cli_alertas.alertas)
    return app.test_cli_runner().invoke(args=["alertas", *args])


def test_comando_avaliar_imprime_o_resultado(monkeypatch: pytest.MonkeyPatch) -> None:
    ok = alertas.ResultadoCiclo(ocorrencias=3, alertas_abertos=1, avisados=1, email_enviado=True)

    saida = _executar_cli(monkeypatch, ["avaliar"], ok)

    assert saida.exit_code == 0, saida.output
    assert "abertos=1" in saida.output and "email_enviado=true" in saida.output


def test_comando_avaliar_sai_com_erro_quando_o_ciclo_falha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ruim = alertas.ResultadoCiclo(erros=("E-mail nao configurado",))

    saida = _executar_cli(monkeypatch, ["avaliar"], ruim)

    assert saida.exit_code == 1
    assert "E-mail nao configurado" in saida.output


def test_plataforma_nao_liga_o_avaliador_sem_a_variavel(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria

    monkeypatch.delenv("LUFT_ALERTAS_ATIVO", raising=False)
    ligou: list[Any] = []
    monkeypatch.setattr(
        avaliador_alertas.AvaliadorEmSegundoPlano, "iniciar", lambda self: ligou.append(self)
    )
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )

    PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)

    assert ligou == []


def test_servidor_liga_o_avaliador_mas_a_plataforma_sozinha_nao(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria

    monkeypatch.setenv("LUFT_ALERTAS_ATIVO", "true")
    ligou: list[Any] = []
    monkeypatch.setattr(
        avaliador_alertas.AvaliadorEmSegundoPlano, "iniciar", lambda self: ligou.append(self)
    )
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )

    PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)
    assert ligou == []  # comandos de CLI carregam o app e nao podem iniciar a thread

    from luftbase import servidor

    servidor._iniciar_alertas(app)
    assert len(ligou) == 1
