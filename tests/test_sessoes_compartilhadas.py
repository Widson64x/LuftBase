"""Testes da sessao server-side sem Redis real."""

from datetime import timedelta

import pytest
from flask import Flask, jsonify, session

from luftbase.identidade.sessoes import (
    InterfaceSessaoCompartilhada,
    revogar_sessao_atual,
    rotacionar_sessao,
)
from luftbase.nucleo.excecoes import ErroSessao


class ArmazenamentoMemoria:
    """Armazenamento deterministico que registra TTL e remocoes."""

    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}
        self.ttls: dict[str, int] = {}
        self.removidas: list[str] = []

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        self.dados[chave] = valor
        self.ttls[chave] = ttl_segundos

    def remover(self, chave: str) -> None:
        self.removidas.append(chave)
        self.dados.pop(chave, None)

    def verificar_saude(self) -> bool:
        return True


def _criar_app(armazenamento: ArmazenamentoMemoria) -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.secret_key = "s" * 64
    app.permanent_session_lifetime = timedelta(minutes=30)
    app.config.update(
        SESSION_COOKIE_NAME="luft_sessao",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    app.session_interface = InterfaceSessaoCompartilhada(
        armazenamento,
        "a" * 64,
    )

    @app.get("/gravar")
    def gravar():  # type: ignore[no-untyped-def]
        session["usuario"] = {"id": 2759, "login": "valdeir.junior"}
        return jsonify(ok=True)

    @app.get("/ler")
    def ler():  # type: ignore[no-untyped-def]
        return jsonify(usuario=session.get("usuario"))

    @app.get("/rotacionar")
    def rotacionar():  # type: ignore[no-untyped-def]
        rotacionar_sessao()
        return jsonify(ok=True)

    @app.get("/sair")
    def sair():  # type: ignore[no-untyped-def]
        revogar_sessao_atual()
        return jsonify(ok=True)

    return app


def test_cookie_e_opaco_e_dados_ficam_no_armazenamento() -> None:
    armazenamento = ArmazenamentoMemoria()
    cliente = _criar_app(armazenamento).test_client()

    resposta = cliente.get("/gravar")

    cookie = resposta.headers["Set-Cookie"]
    assert "valdeir" not in cookie
    assert "2759" not in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert len(armazenamento.dados) == 1
    assert next(iter(armazenamento.ttls.values())) == 1800
    assert b"valdeir.junior" in next(iter(armazenamento.dados.values()))


def test_sessao_e_recuperada_em_requisicao_posterior() -> None:
    armazenamento = ArmazenamentoMemoria()
    cliente = _criar_app(armazenamento).test_client()
    cliente.get("/gravar")

    resposta = cliente.get("/ler")

    assert resposta.json["usuario"] == {"id": 2759, "login": "valdeir.junior"}


def test_rotacao_revoga_id_anterior_sem_perder_dados() -> None:
    armazenamento = ArmazenamentoMemoria()
    cliente = _criar_app(armazenamento).test_client()
    cliente.get("/gravar")
    chave_anterior = next(iter(armazenamento.dados))

    cliente.get("/rotacionar")

    assert chave_anterior in armazenamento.removidas
    assert chave_anterior not in armazenamento.dados
    assert cliente.get("/ler").json["usuario"]["id"] == 2759


def test_logout_global_revoga_e_limpa_sessao() -> None:
    armazenamento = ArmazenamentoMemoria()
    cliente = _criar_app(armazenamento).test_client()
    cliente.get("/gravar")
    chave = next(iter(armazenamento.dados))

    resposta = cliente.get("/sair")

    assert chave in armazenamento.removidas
    assert not armazenamento.dados
    assert "Expires=" in resposta.headers["Set-Cookie"]
    assert cliente.get("/ler").json["usuario"] is None


def test_cookie_adulterado_nao_recupera_sessao() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _criar_app(armazenamento)
    cliente = app.test_client()
    cliente.set_cookie("luft_sessao", "id-inventado.assinatura-invalida")

    assert cliente.get("/ler").json["usuario"] is None


def test_payload_corrompido_falha_fechado() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _criar_app(armazenamento)
    cliente = app.test_client()
    cliente.get("/gravar")
    chave = next(iter(armazenamento.dados))
    armazenamento.dados[chave] = b"nao-e-json"

    with pytest.raises(ErroSessao):
        cliente.get("/ler")


def test_exige_chave_de_assinatura_forte() -> None:
    with pytest.raises(ErroSessao, match="32 caracteres"):
        InterfaceSessaoCompartilhada(ArmazenamentoMemoria(), "curta")
