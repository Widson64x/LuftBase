"""Testes dos hooks Flask de observabilidade."""

from flask import Flask
from flask_login import LoginManager

from luftbase.observabilidade.metricas import RegistroMetricas
from luftbase.observabilidade.web import (
    IntegracaoObservabilidadeFlask,
    marcar_decisao_autorizacao,
)


class AuditoriaFalsa:
    habilitada = True

    def __init__(self, *, falhar: bool = False) -> None:
        self.eventos: list[object] = []
        self.falhar = falhar

    def registrar_acesso(self, evento: object) -> int:
        if self.falhar:
            raise RuntimeError("senha=nao-vazar host=interno")
        self.eventos.append(evento)
        return 1


class LoggerFalso:
    def __init__(self) -> None:
        self.erros: list[tuple[str, str]] = []

    def erro(self, evento: str, erro: BaseException, **opcoes: object) -> None:
        del opcoes
        self.erros.append((evento, type(erro).__name__))


def _app(auditoria: AuditoriaFalsa, metricas: RegistroMetricas, logger: LoggerFalso) -> Flask:
    app = Flask(__name__)
    app.secret_key = "teste"
    gerenciador = LoginManager(app)

    @gerenciador.user_loader
    def carregar_usuario(_identificador: str):  # type: ignore[no-untyped-def]
        return None

    IntegracaoObservabilidadeFlask(
        auditoria,  # type: ignore[arg-type]
        metricas,
        logger,  # type: ignore[arg-type]
    ).instalar(app)

    @app.get("/itens/<int:id_item>")
    def consultar(id_item: int) -> str:
        marcar_decisao_autorizacao("ITENS.VER", True)
        return str(id_item)

    return app


def test_registra_uma_vez_sem_corpo_cabecalhos_ou_id_da_rota() -> None:
    auditoria = AuditoriaFalsa()
    metricas = RegistroMetricas()
    logger = LoggerFalso()
    app = _app(auditoria, metricas, logger)

    resposta = app.test_client().get(
        "/itens/123?senha=segredo&pagina=2",
        headers={"Authorization": "Bearer segredo"},
    )

    evento = auditoria.eventos[0]
    assert resposta.status_code == 200
    assert resposta.headers["X-Correlation-ID"]
    assert evento.rota == "/itens/<int:id_item>"  # type: ignore[attr-defined]
    assert evento.permissao_exigida == "ITENS.VER"  # type: ignore[attr-defined]
    assert evento.acesso_permitido is True  # type: ignore[attr-defined]
    assert "segredo" not in evento.parametros  # type: ignore[operator, attr-defined]
    assert "Authorization" not in evento.parametros  # type: ignore[operator, attr-defined]
    assert metricas.snapshot()["requisicoes_total"] == 1
    assert not logger.erros


def test_falha_da_auditoria_nao_altera_resposta_e_nao_vaza_mensagem() -> None:
    auditoria = AuditoriaFalsa(falhar=True)
    metricas = RegistroMetricas()
    logger = LoggerFalso()
    app = _app(auditoria, metricas, logger)

    resposta = app.test_client().get("/itens/1")

    assert resposta.status_code == 200
    assert metricas.snapshot()["falhas_auditoria_total"] == 1
    assert logger.erros == [("falha_auditoria_http", "RuntimeError")]
