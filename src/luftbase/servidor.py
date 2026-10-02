"""Execucao padronizada das aplicacoes Luft (mesmo servidor, console e banner em todas).

Cada aplicacao tem dois pontos de entrada na raiz, ambos de poucas linhas:

- ``Wsgi.py`` (producao, servico do Windows): ``executar("App:criar_app")`` -> Waitress.
- ``App.py`` (desenvolvimento): ``executar_desenvolvimento("App:criar_app")`` -> servidor do
  Flask com depurador e recarga automatica (``LUFT_AMBIENTE`` diferente de producao).

O alvo e ``modulo:atributo`` (fabrica sem argumentos ou objeto Flask). Pela linha de comando:
``luftbase servir App:criar_app``.

O console e configurado antes de importar a aplicacao, entao as mensagens da inicializacao
(Vault, sessoes, catalogo) saem no mesmo formato. Cada requisicao vai somente para o log
fisico do LuftBase (``Logs/luftbase.log``); o console mostra a subida, avisos e erros.

Configuracao (argumento > variavel ``LUFT_SERVIDOR_*`` > variavel legada > padrao):

- host:    ``LUFT_SERVIDOR_HOST`` | ``HOST``          (127.0.0.1)
- porta:   ``LUFT_SERVIDOR_PORTA`` | ``PORT``         (8000)
- prefixo: ``LUFT_SERVIDOR_PREFIXO`` | ``ROUTE_PREFIX`` (vazio; ex.: /Luft-ConnectAir)
- threads: ``LUFT_SERVIDOR_THREADS``                  (8)

O servidor de desenvolvimento ignora o prefixo (a aplicacao responde na raiz).
"""

from __future__ import annotations

import importlib
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

from flask import Flask

from luftbase._versao import __version__
from luftbase.nucleo.excecoes import ErroConfiguracao

FORMATO_CONSOLE = "%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

_MARCA_HANDLER = "_luftbase_console"
HOST_PADRAO = "127.0.0.1"
PORTA_PADRAO = 8000
THREADS_PADRAO = 8
_logger = logging.getLogger("luftbase.servidor")


@dataclass(frozen=True, slots=True)
class ConfiguracaoServidor:
    """Endereco e capacidade do servidor WSGI."""

    host: str = HOST_PADRAO
    porta: int = PORTA_PADRAO
    prefixo: str = ""
    threads: int = THREADS_PADRAO

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.porta}{self.prefixo}"

    @classmethod
    def de_ambiente(
        cls,
        *,
        host: str | None = None,
        porta: int | None = None,
        prefixo: str | None = None,
        threads: int | None = None,
    ) -> ConfiguracaoServidor:
        host_final = host or _variavel("LUFT_SERVIDOR_HOST", "HOST") or HOST_PADRAO
        porta_final = porta if porta is not None else _inteiro(
            _variavel("LUFT_SERVIDOR_PORTA", "PORT"), "LUFT_SERVIDOR_PORTA", PORTA_PADRAO, 1, 65_535
        )
        threads_final = threads if threads is not None else _inteiro(
            _variavel("LUFT_SERVIDOR_THREADS"), "LUFT_SERVIDOR_THREADS", THREADS_PADRAO, 1, 256
        )
        bruto = (
            prefixo
            if prefixo is not None
            else _variavel("LUFT_SERVIDOR_PREFIXO", "ROUTE_PREFIX")
        )
        return cls(
            host=host_final,
            porta=porta_final,
            prefixo=normalizar_prefixo(bruto),
            threads=threads_final,
        )


def _variavel(*nomes: str) -> str | None:
    for nome in nomes:
        valor = (os.getenv(nome) or "").strip()
        if valor:
            return valor
    return None


def _inteiro(valor: str | None, nome: str, padrao: int, minimo: int, maximo: int) -> int:
    if valor is None:
        return padrao
    try:
        numero = int(valor)
    except ValueError as erro:
        raise ErroConfiguracao(f"{nome} deve ser um numero inteiro.") from erro
    if not minimo <= numero <= maximo:
        raise ErroConfiguracao(f"{nome} deve estar entre {minimo} e {maximo}.")
    return numero


def normalizar_prefixo(prefixo: str | None) -> str:
    """'' ou '/' -> ''; 'Luft-ConnectAir/' -> '/Luft-ConnectAir'."""

    limpo = (prefixo or "").strip().strip("/")
    return f"/{limpo}" if limpo else ""


def configurar_console(nivel: int = logging.INFO) -> None:
    """Console unico para a plataforma (idempotente).

    O logger raiz recebe um handler no formato padrao; o servidor de desenvolvimento do Werkzeug
    e o Waitress ficam em WARNING para nao repetir cada requisicao no terminal.
    """

    raiz = logging.getLogger()
    if not any(getattr(h, _MARCA_HANDLER, False) for h in raiz.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(FORMATO_CONSOLE, datefmt=FORMATO_DATA))
        setattr(handler, _MARCA_HANDLER, True)
        raiz.addHandler(handler)
    if raiz.level == logging.NOTSET or raiz.level > nivel:
        raiz.setLevel(nivel)
    for ruidoso in ("werkzeug", "waitress", "waitress.queue"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    # Fora do console padrao, so o que importa: avisos das bibliotecas de terceiros.
    for biblioteca in ("urllib3", "hvac", "sqlalchemy", "ldap3", "httpx", "alembic"):
        logging.getLogger(biblioteca).setLevel(logging.WARNING)


def resolver_aplicacao(alvo: str | Flask | Callable[[], Flask]) -> Flask:
    """Aceita 'modulo:atributo', um Flask ou uma fabrica sem argumentos."""

    if isinstance(alvo, str):
        modulo_nome, _, atributo = alvo.partition(":")
        if not modulo_nome or not atributo:
            raise ErroConfiguracao(f"Alvo invalido {alvo!r}; use 'modulo:atributo' (ex.: App:app).")
        if os.getcwd() not in sys.path:
            sys.path.insert(0, os.getcwd())
        alvo = getattr(importlib.import_module(modulo_nome), atributo)
    if isinstance(alvo, Flask):
        return alvo
    if callable(alvo):
        app = alvo()
        if isinstance(app, Flask):
            return app
    raise ErroConfiguracao("O alvo nao e uma aplicacao Flask nem uma fabrica que retorne uma.")


def _identidade(app: Flask) -> tuple[str, str | None, str | None, int | None]:
    nome = str(app.config.get("LUFT_APLICACAO_NOME") or app.name)
    versao = app.config.get("LUFT_APLICACAO_VERSAO")
    ambiente: str | None = None
    sistema_id: int | None = None
    try:
        from luftbase.plataforma import obter_luftbase

        with app.app_context():
            estado = obter_luftbase()
        aplicacao = estado.configuracao.aplicacao if estado else None
        if aplicacao is not None:
            nome = aplicacao.nome or nome
            versao = versao or aplicacao.versao
            ambiente = aplicacao.ambiente.value
            sistema_id = aplicacao.sistema_id
    except Exception:  # noqa: BLE001 - o banner nunca impede a subida
        pass
    return nome, (str(versao) if versao else None), ambiente, sistema_id


def anunciar(
    app: Flask,
    configuracao: ConfiguracaoServidor,
    servidor: str | None = None,
) -> None:
    """Banner padrao de subida, igual em todas as aplicacoes."""

    nome, versao, ambiente, sistema_id = _identidade(app)
    partes = [f"{nome} v{versao}" if versao else nome]
    if sistema_id is not None:
        partes.append(f"sistema {sistema_id}")
    if ambiente:
        partes.append(f"ambiente {ambiente.upper()}")
    partes.append(f"LuftBase {__version__}")
    _logger.info(" | ".join(partes))
    detalhe = servidor or f"Waitress, {configuracao.threads} threads"
    _logger.info(
        "Servindo em %s (%s). Requisicoes em Logs/luftbase.log.", configuracao.url, detalhe
    )


def _preparar() -> None:
    """.env da aplicacao (diretorio de execucao) e console padrao, antes de importar a app."""

    try:
        from dotenv import load_dotenv

        load_dotenv(os.path.join(os.getcwd(), ".env"), override=False)
    except ImportError:  # pragma: no cover - python-dotenv e dependencia do LuftBase
        pass
    configurar_console()


def ambiente_de_producao() -> bool:
    return (os.getenv("LUFT_AMBIENTE") or "desenvolvimento").strip().lower() in {
        "producao", "production", "prod", "prd",
    }


def executar(
    alvo: str | Flask | Callable[[], Flask],
    *,
    host: str | None = None,
    porta: int | None = None,
    prefixo: str | None = None,
    threads: int | None = None,
) -> None:
    """Configura o console, carrega a aplicacao e a serve com o Waitress."""

    _preparar()
    configuracao = ConfiguracaoServidor.de_ambiente(
        host=host, porta=porta, prefixo=prefixo, threads=threads
    )
    app = resolver_aplicacao(alvo)

    from waitress import serve  # type: ignore[import-untyped]

    anunciar(app, configuracao)
    serve(
        app,
        host=configuracao.host,
        port=configuracao.porta,
        threads=configuracao.threads,
        url_prefix=configuracao.prefixo,
        ident=None,
    )


def executar_desenvolvimento(
    alvo: str | Flask | Callable[[], Flask],
    *,
    host: str | None = None,
    porta: int | None = None,
    depurar: bool | None = None,
) -> None:
    """Servidor de desenvolvimento do Flask (depurador + recarga) com o console padrao.

    ``depurar`` padrao: ligado fora de producao. A recarga automatica reinicia o processo;
    a aplicacao so e criada no processo filho (uma unica inicializacao por ciclo).
    """

    _preparar()
    configuracao = ConfiguracaoServidor.de_ambiente(host=host, porta=porta, prefixo="")
    depuracao = (not ambiente_de_producao()) if depurar is None else depurar

    if depuracao and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        # Processo pai da recarga automatica: so supervisiona (nao cria a aplicacao) e abre
        # a porta; o processo filho, iniciado por ele, sobe a aplicacao de verdade.
        from werkzeug.serving import run_simple

        run_simple(
            configuracao.host,
            configuracao.porta,
            lambda _ambiente, _resposta: [],
            use_reloader=True,
        )
        return

    app = resolver_aplicacao(alvo)
    anunciar(app, configuracao, servidor="Flask, desenvolvimento" if depuracao else "Flask")
    app.run(
        host=configuracao.host,
        port=configuracao.porta,
        debug=depuracao,
        use_reloader=depuracao,
    )
