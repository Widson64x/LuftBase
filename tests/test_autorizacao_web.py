"""Testes do decorator e dos helpers Jinja de autorizacao."""

from types import SimpleNamespace

import pytest
from flask import Flask, render_template_string

from luftbase.autorizacao import exigir_alguma_permissao, exigir_permissao
from luftbase.autorizacao.web import registrar_contexto_jinja
from luftbase.identidade import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroAutorizacao


class AutorizacaoFalsa:
    def __init__(self, permitido: bool = True, *, falhar: bool = False) -> None:
        self.permitido = permitido
        self.falhar = falhar
        self.chaves: list[str] = []

    def possui(self, usuario: UsuarioAutenticado, chave: str) -> bool:
        del usuario
        self.chaves.append(chave)
        if self.falhar:
            raise ErroAutorizacao("indisponivel")
        return self.permitido

    def consultar(self, usuario, chaves):  # type: ignore[no-untyped-def]
        del usuario
        return {chave: self.permitido for chave in chaves}


@pytest.mark.parametrize(
    ("permitido", "falhar", "status"),
    [(True, False, 200), (False, False, 403), (False, True, 503)],
)
def test_decorator_aplica_decisao_fail_closed(
    monkeypatch,
    permitido: bool,
    falhar: bool,
    status: int,
) -> None:  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    autorizacao = AutorizacaoFalsa(permitido, falhar=falhar)
    usuario = UsuarioAutenticado(1, "usuario", "Usuario", None, 7, "TI")
    monkeypatch.setattr("luftbase.autorizacao.web._usuario_atual", lambda: usuario)
    monkeypatch.setattr(
        "luftbase.plataforma.obter_luftbase",
        lambda: SimpleNamespace(autorizacao=autorizacao),
    )

    @app.get("/protegida")
    @exigir_permissao("relatorios.ver")
    def protegida() -> str:
        return "ok"

    resposta = app.test_client().get("/protegida")

    assert resposta.status_code == status
    assert autorizacao.chaves == ["RELATORIOS.VER"]


def test_contexto_jinja_disponibiliza_consulta_em_portugues(monkeypatch) -> None:
    app = Flask(__name__)
    autorizacao = AutorizacaoFalsa(True)
    usuario = UsuarioAutenticado(1, "usuario", "Usuario", None, 7, "TI")
    monkeypatch.setattr("luftbase.autorizacao.web._usuario_atual", lambda: usuario)
    monkeypatch.setattr(
        "luftbase.plataforma.obter_luftbase",
        lambda: SimpleNamespace(autorizacao=autorizacao),
    )
    registrar_contexto_jinja(app)

    with app.test_request_context("/"):
        html = render_template_string("{{ tem_permissao('RELATORIOS.VER') }}")

    assert html == "True"


@pytest.mark.parametrize(
    ("decisoes", "status"),
    [
        ({"CONFIGURACOES.VISUALIZAR": False, "OBSERVABILIDADE.AUDITORIA.VISUALIZAR": True}, 200),
        ({"CONFIGURACOES.VISUALIZAR": False, "OBSERVABILIDADE.AUDITORIA.VISUALIZAR": False}, 403),
    ],
)
def test_decorator_exigir_alguma_permissao(monkeypatch, decisoes, status: int) -> None:  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    autorizacao = AutorizacaoFalsa()
    autorizacao.consultar = lambda _usuario, chaves: {chave: decisoes[chave] for chave in chaves}  # type: ignore[method-assign]
    usuario = UsuarioAutenticado(1, "usuario", "Usuario", None, 7, "TI")
    monkeypatch.setattr("luftbase.autorizacao.web._usuario_atual", lambda: usuario)
    monkeypatch.setattr(
        "luftbase.plataforma.obter_luftbase",
        lambda: SimpleNamespace(autorizacao=autorizacao),
    )

    @app.get("/alguma")
    @exigir_alguma_permissao(("CONFIGURACOES.VISUALIZAR", "OBSERVABILIDADE.AUDITORIA.VISUALIZAR"))
    def alguma() -> str:
        return "ok"

    assert app.test_client().get("/alguma").status_code == status
