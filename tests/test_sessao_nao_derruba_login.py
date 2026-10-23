"""O cookie de sessao e compartilhado entre os sistemas: nenhuma requisicao pode trocar um cookie bom por um anonimo."""

import time
from datetime import timedelta

from flask import Flask, abort, jsonify, session
from flask_login import LoginManager, current_user

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.identidade.sessoes import (
    InterfaceSessaoCompartilhada,
    carregar_usuario_sessao,
    iniciar_sessao_usuario,
)

CHAVE = "a" * 64
USUARIO = UsuarioAutenticado(
    id_usuario=7, login="ana", nome_completo="Ana", email=None, id_grupo=1, nome_grupo="G",
    permissoes=frozenset(),
)


class ArmazenamentoMemoria:
    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}
        self.encerradas: set[str] = set()

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> bool:
        if chave in self.encerradas:
            return False  # como o PostgreSQL: sessao ja encerrada nao volta a valer
        self.dados[chave] = valor
        return True

    def remover(self, chave: str) -> None:
        self.encerradas.add(chave)
        self.dados.pop(chave, None)

    def verificar_saude(self) -> bool:
        return True


def _app(armazenamento: ArmazenamentoMemoria) -> Flask:
    app = Flask(__name__)
    app.testing = True
    app.secret_key = "s" * 64
    app.permanent_session_lifetime = timedelta(minutes=60)
    app.config.update(SESSION_COOKIE_NAME="luft_sessao", SESSION_COOKIE_SECURE=False)
    interface = InterfaceSessaoCompartilhada(armazenamento, CHAVE)
    app.session_interface = interface
    gerenciador = LoginManager()
    gerenciador.session_protection = "basic"
    gerenciador.init_app(app)
    gerenciador.user_loader(carregar_usuario_sessao)

    @gerenciador.unauthorized_handler
    def _nao():  # type: ignore[no-untyped-def]
        abort(401)

    @app.get("/estatico")
    def estatico():  # type: ignore[no-untyped-def]
        return "css"

    @app.get("/api")
    def api():  # type: ignore[no-untyped-def]
        if not current_user.is_authenticated:  # o Flask-Login escreve `_fresh` na sessao do visitante
            abort(401)
        return jsonify(ok=True)

    @app.get("/tela-login")
    def tela_login():  # type: ignore[no-untyped-def]
        session["luftbase_csrf"] = "x" * 43  # a tela de entrada guarda o token CSRF
        return "login"

    @app.get("/fundo-grava")
    def fundo_grava():  # type: ignore[no-untyped-def]
        session["fila"] = [1]
        return "ok"

    @app.post("/entrar")
    def entrar():  # type: ignore[no-untyped-def]
        iniciar_sessao_usuario(USUARIO)
        return "ok"

    return app


def _cookie(resposta) -> str | None:  # type: ignore[no-untyped-def]
    for linha in resposta.headers.getlist("Set-Cookie"):
        if linha.startswith("luft_sessao="):
            return linha.split(";", 1)[0].split("=", 1)[1]
    return None


def _chamar(app, caminho, cookie=None, metodo="GET", **cab):  # type: ignore[no-untyped-def]
    cabecalhos = dict(cab)
    if cookie:
        cabecalhos["Cookie"] = f"luft_sessao={cookie}"
    return app.test_client(use_cookies=False).open(caminho, method=metodo, headers=cabecalhos)


def _entrar(app):  # type: ignore[no-untyped-def]
    anonimo = _cookie(_chamar(app, "/tela-login"))
    return _cookie(_chamar(app, "/entrar", anonimo, "POST"))


def _cookie_antigo(armazenamento, idade_s: int) -> str:  # type: ignore[no-untyped-def]
    """Cookie de uma sessao viva, assinado `idade_s` segundos atras (negativo = no futuro)."""

    app = _app(armazenamento)
    cookie = _entrar(app)
    interface = app.session_interface
    assinador = interface._assinador()
    assinador.get_timestamp = lambda: int(time.time()) - idade_s  # type: ignore[method-assign]
    return assinador.sign(interface_id(cookie)).decode()


def interface_id(cookie: str) -> bytes:
    return cookie.split(".")[0].encode()


def test_visitante_sem_cookie_nao_cria_sessao_nem_cookie() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)

    for caminho in ("/estatico", "/api"):
        resposta = _chamar(app, caminho)
        assert _cookie(resposta) is None, caminho

    assert armazenamento.dados == {}


def test_requisicao_de_fundo_sem_sessao_nunca_cria_sessao() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)

    resposta = _chamar(app, "/fundo-grava", **{"X-Background-Request": "1"})

    assert _cookie(resposta) is None
    assert armazenamento.dados == {}


def test_tela_de_login_guarda_o_token_e_ganha_cookie() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)

    resposta = _chamar(app, "/tela-login")

    assert _cookie(resposta) is not None
    assert len(armazenamento.dados) == 1


def test_cookie_fresco_nao_e_reenviado_a_cada_resposta() -> None:
    app = _app(ArmazenamentoMemoria())
    cookie = _entrar(app)

    resposta = _chamar(app, "/api", cookie)

    assert resposta.status_code == 200
    assert _cookie(resposta) is None


def test_cookie_envelhecido_e_renovado() -> None:
    armazenamento = ArmazenamentoMemoria()
    antigo = _cookie_antigo(armazenamento, idade_s=400)
    app = _app(armazenamento)

    resposta = _chamar(app, "/api", antigo)

    assert resposta.status_code == 200
    assert _cookie(resposta) is not None  # >= 300 s: renova validade e carimbo


def test_login_troca_o_id_e_entrega_cookie_novo() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)
    anonimo = _cookie(_chamar(app, "/tela-login"))

    resposta = _chamar(app, "/entrar", anonimo, "POST")

    novo = _cookie(resposta)
    assert novo is not None and novo.split(".")[0] != anonimo.split(".")[0]


def test_resposta_de_requisicao_iniciada_antes_do_login_nao_sobrescreve_o_cookie() -> None:
    """Requisicao em voo com o id antigo: o login encerra esse id e a resposta atrasada nao traz cookie."""

    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)
    anonimo = _cookie(_chamar(app, "/tela-login"))
    _chamar(app, "/entrar", anonimo, "POST")  # troca o id: o antigo fica encerrado

    atrasada = _chamar(app, "/api", anonimo)  # chega depois, ainda com o cookie antigo

    assert _cookie(atrasada) is None


def test_gravacao_recusada_por_sessao_encerrada_nao_envia_cookie() -> None:
    armazenamento = ArmazenamentoMemoria()
    app = _app(armazenamento)
    cookie = _entrar(app)
    identificador = cookie.split(".")[0]
    armazenamento.encerradas.add(f"luft:sessao:{identificador}")

    resposta = _chamar(app, "/tela-login", cookie)

    assert _cookie(resposta) is None


def test_relogio_de_outro_servidor_adiantado_alguns_segundos_nao_derruba() -> None:
    armazenamento = ArmazenamentoMemoria()
    futuro = _cookie_antigo(armazenamento, idade_s=-5)
    app = _app(armazenamento)

    assert _chamar(app, "/api", futuro).status_code == 200


def test_carimbo_muito_no_futuro_e_recusado() -> None:
    armazenamento = ArmazenamentoMemoria()
    futuro = _cookie_antigo(armazenamento, idade_s=-120)
    app = _app(armazenamento)

    assert _chamar(app, "/api", futuro).status_code == 401
