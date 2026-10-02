"""Testes dos contratos HTTP e da retomada SSE."""

from datetime import datetime
from types import SimpleNamespace

from flask import Flask
from flask_login import LoginManager

from luftbase.conteudo.modelos import (
    NotificacaoUsuario,
    PaginaNotificacoes,
    PaginaPublicacoes,
    PublicacaoUsuario,
)
from luftbase.conteudo.web import registrar_rotas_conteudo
from luftbase.identidade.modelos import UsuarioAutenticado


class ServicoNotificacoesFalso:
    """Servico que registra o cursor recebido pela rota."""

    def __init__(self) -> None:
        self.cursor: int | None = None
        self.apenas_nao_lidas: bool = False
        self.leituras = 0
        self.leituras_todas = 0

    def listar_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        *,
        cursor: int | None = None,
        limite: int = 30,
        apenas_nao_lidas: bool = False,
    ) -> PaginaNotificacoes:
        del id_usuario, id_grupo, limite
        self.cursor = cursor
        self.apenas_nao_lidas = apenas_nao_lidas
        item = NotificacaoUsuario(
            id_notificacao=12,
            id_sistema=2,
            tipo="INFO",
            categoria="GERAL",
            titulo="Aviso",
            mensagem="Mensagem",
            icone=None,
            lida=False,
            data_criacao=datetime(2026, 9, 16, 10, 0),
            data_leitura=None,
            metadados=None,
            expira_em=None,
            exibir_a_partir_de=None,
        )
        return PaginaNotificacoes((item,), 12, False)

    def marcar_lida(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_notificacao: int,
    ) -> bool:
        del id_usuario, id_grupo, id_notificacao
        self.leituras += 1
        return self.leituras == 1

    def marcar_todas_lidas(
        self,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        del id_usuario, id_grupo
        self.leituras_todas += 1
        return 5


class ServicoPublicacoesFalso:
    """Servico minimo para as rotas de publicacao."""

    def listar_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        *,
        cursor: int | None,
        limite: int,
    ) -> PaginaPublicacoes:
        del id_usuario, id_grupo, cursor, limite
        return PaginaPublicacoes((self._item(),), 7, False)

    def obter_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> PublicacaoUsuario:
        del id_usuario, id_grupo, id_publicacao
        return self._item(conteudo="Conteudo completo")

    def marcar_lida(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> bool:
        del id_usuario, id_grupo, id_publicacao
        return True

    @staticmethod
    def _item(*, conteudo: str | None = None) -> PublicacaoUsuario:
        return PublicacaoUsuario(
            id_publicacao=7,
            id_sistema=2,
            tipo="COMUNICADO",
            audiencia="GERAL",
            titulo="Comunicado",
            resumo="Resumo",
            conteudo=conteudo,
            prioridade="NORMAL",
            versao=None,
            fixado=False,
            lida=False,
            exibir_a_partir_de=None,
            expira_em=None,
            data_publicacao=datetime(2026, 9, 16, 9, 0),
        )


def _criar_app(monkeypatch):  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    app.secret_key = "teste"
    usuario = UsuarioAutenticado(15, "teste", "Usuario Teste", None, 4, "Grupo")
    gerenciador = LoginManager(app)

    @gerenciador.user_loader
    def carregar(_identificador: str) -> UsuarioAutenticado:
        return usuario

    notificacoes = ServicoNotificacoesFalso()
    publicacoes = ServicoPublicacoesFalso()
    estado = SimpleNamespace(notificacoes=notificacoes, publicacoes=publicacoes)
    monkeypatch.setattr("luftbase.plataforma.obter_luftbase", lambda: estado)
    registrar_rotas_conteudo(app)
    return app, notificacoes


def _autenticar(cliente) -> str:  # type: ignore[no-untyped-def]
    token = "csrf-de-teste-com-tamanho-suficiente"
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = "15"
        sessao["_fresh"] = True
        sessao["luftbase_csrf"] = token
    return token


def test_rotas_exigem_usuario_autenticado(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)

    assert app.test_client().get("/_luftbase/notificacoes").status_code == 401


def test_sse_retoma_pelo_last_event_id(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, notificacoes = _criar_app(monkeypatch)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get(
        "/_luftbase/notificacoes/eventos",
        headers={"Last-Event-ID": "11"},
    )

    assert resposta.status_code == 200
    assert resposta.mimetype == "text/event-stream"
    assert "id: 12" in resposta.text
    assert "event: notificacao" in resposta.text
    assert notificacoes.cursor == 11


def test_leitura_e_detalhe_sao_operacoes_separadas(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    cliente = app.test_client()
    token = _autenticar(cliente)

    detalhe = cliente.get("/_luftbase/publicacoes/7")
    leitura = cliente.put(
        "/_luftbase/publicacoes/7/leitura",
        headers={"X-CSRF-Token": token},
    )

    assert detalhe.status_code == 200
    assert detalhe.json["conteudo"] == "Conteudo completo"
    assert leitura.json == {"alterada": True}


def test_leitura_rejeita_mutacao_sem_csrf(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, notificacoes = _criar_app(monkeypatch)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.put("/_luftbase/notificacoes/12/leitura")

    assert resposta.status_code == 403
    assert notificacoes.leituras == 0


def test_rejeita_cursor_invalido_antes_do_servico(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/_luftbase/notificacoes?cursor=invalido")

    assert resposta.status_code == 400


def test_listar_notificacoes_suporta_apenas_nao_lidas_e_compatibilidade_dados(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, notificacoes = _criar_app(monkeypatch)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/_luftbase/notificacoes?apenas_nao_lidas=true")

    assert resposta.status_code == 200
    assert notificacoes.apenas_nao_lidas is True
    dados = resposta.get_json()
    assert "itens" in dados
    assert "dados" in dados
    assert dados["itens"] == dados["dados"]
    assert dados["status"] == "success"


def test_marcar_todas_notificacoes_lidas(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, notificacoes = _criar_app(monkeypatch)
    cliente = app.test_client()
    token = _autenticar(cliente)

    resposta = cliente.put(
        "/_luftbase/notificacoes/leitura-todas",
        headers={"X-CSRF-Token": token},
    )

    assert resposta.status_code == 200
    assert notificacoes.leituras_todas == 1
    assert resposta.json == {"status": "success", "total_lidas": 5, "contagem": 0}
