"""Tema (familia de cores) e modo (claro/escuro) como eixos independentes."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, render_template
from flask_login import LoginManager

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.interface.modelos import ManifestoTema, PreferenciaTema
from luftbase.interface.servico import RegistroTemas, ServicoTemas, criar_registro_padrao
from luftbase.interface.web import registrar_interface_web
from luftbase.nucleo import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema

ESTATICO = Path(__file__).parents[1] / "src" / "luftbase" / "interface" / "static"


class RepositorioFalso:
    def __init__(self, preferencia: PreferenciaTema | None = None) -> None:
        self.preferencia = preferencia
        self.salvas: list[tuple[int, PreferenciaTema]] = []

    def obter(self, id_usuario: int) -> PreferenciaTema | None:
        del id_usuario
        return self.preferencia

    def salvar(self, id_usuario: int, preferencia: PreferenciaTema) -> None:
        self.preferencia = preferencia
        self.salvas.append((id_usuario, preferencia))


def _registro_com_tema_claro() -> RegistroTemas:
    registro = criar_registro_padrao()
    registro.registrar(
        ManifestoTema(
            "so-claro",
            "Somente Claro",
            "1.0.0",
            "/_luftbase/static/css/temas/luft.css",
            frozenset({ModoTema.CLARO}),
        )
    )
    return registro


def test_registro_padrao_inclui_luft_esg_com_os_dois_modos() -> None:
    esg = criar_registro_padrao().obter("luft-esg")

    assert esg is not None
    assert esg.modos == {ModoTema.CLARO, ModoTema.ESCURO}
    assert esg.url_css == "/_luftbase/static/css/temas/luft-esg.css"
    assert esg.cores_previa


def test_modo_efetivo_respeita_preferencia_em_tema_completo() -> None:
    servico = ServicoTemas(RepositorioFalso(), criar_registro_padrao())

    for modo in ModoTema:
        resolvido = servico.resolver(PreferenciaTema("luft-esg", modo))
        assert resolvido.modo_efetivo is modo
        assert resolvido.modo_bloqueado is False


def test_tema_de_modo_unico_impoe_o_modo_e_guarda_a_preferencia() -> None:
    repositorio = RepositorioFalso()
    servico = ServicoTemas(repositorio, _registro_com_tema_claro())

    guardada = servico.alterar_preferencia(7, "so-claro", "ESCURO")
    resolvido = servico.resolver(guardada)

    # O usuario queria escuro, o tema so tem claro: exibe claro, mas nao perde a escolha.
    assert guardada == PreferenciaTema("so-claro", ModoTema.ESCURO)
    assert resolvido.modo_preferido is ModoTema.ESCURO
    assert resolvido.modo_efetivo is ModoTema.CLARO
    assert resolvido.modo_bloqueado is True

    # Ao voltar a um tema completo a preferencia original volta a valer.
    de_volta = servico.resolver(PreferenciaTema("luft", guardada.modo))
    assert de_volta.modo_efetivo is ModoTema.ESCURO


def test_modo_automatico_tambem_e_neutralizado_em_tema_de_modo_unico() -> None:
    servico = ServicoTemas(RepositorioFalso(), _registro_com_tema_claro())

    resolvido = servico.resolver(PreferenciaTema("so-claro", ModoTema.SISTEMA))

    assert resolvido.modo_efetivo is ModoTema.CLARO


def test_alterar_preferencia_continua_rejeitando_tema_e_modo_invalidos() -> None:
    servico = ServicoTemas(RepositorioFalso(), criar_registro_padrao())

    with pytest.raises(ErroConfiguracao, match="Tema nao registrado"):
        servico.alterar_preferencia(1, "inexistente", "CLARO")
    with pytest.raises(ErroConfiguracao, match="Modo deve ser"):
        servico.alterar_preferencia(1, "luft", "ROXO")


def _criar_app(monkeypatch, repositorio: RepositorioFalso, registro: RegistroTemas):  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    app.secret_key = "teste"
    usuario = UsuarioAutenticado(15, "teste", "Usuario Teste", None, 4, "Grupo")
    login = LoginManager(app)

    @login.user_loader
    def carregar(_identificador: str) -> UsuarioAutenticado:
        return usuario

    temas = ServicoTemas(repositorio, registro)
    monkeypatch.setattr(
        "luftbase.plataforma.obter_luftbase",
        lambda: SimpleNamespace(temas=temas),
    )
    registrar_interface_web(app)

    @app.get("/pagina")
    def pagina():  # type: ignore[no-untyped-def]
        return render_template("luftbase/base.html")

    return app


def _cliente_autenticado(app):  # type: ignore[no-untyped-def]
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = "15"
        sessao["_fresh"] = True
    return cliente


def test_pagina_em_tema_de_modo_unico_marca_html_e_bloqueia_o_botao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repositorio = RepositorioFalso(PreferenciaTema("so-claro", ModoTema.ESCURO))
    app = _criar_app(monkeypatch, repositorio, _registro_com_tema_claro())

    html = _cliente_autenticado(app).get("/pagina").text

    assert 'data-luft-theme="so-claro"' in html
    assert 'data-luft-mode="claro"' in html
    assert 'data-theme="light"' in html
    assert 'data-luft-modo-preferido="escuro"' in html
    assert 'data-luft-modos="claro"' in html
    assert 'data-luft-modo-bloqueado="true"' in html
    assert "luft-btn-action--bloqueado" in html
    assert 'aria-disabled="true"' in html
    assert "Modo fixo: o tema Somente Claro" in html


def test_pagina_em_tema_completo_mantem_o_botao_ativo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repositorio = RepositorioFalso(PreferenciaTema("luft-esg", ModoTema.ESCURO))
    app = _criar_app(monkeypatch, repositorio, criar_registro_padrao())

    html = _cliente_autenticado(app).get("/pagina").text

    assert 'data-luft-theme="luft-esg"' in html
    assert 'data-theme="dark"' in html
    assert 'data-luft-modo-bloqueado="false"' in html
    assert "luft-btn-action--bloqueado" not in html
    assert "Alternar entre modo claro e escuro" in html


def test_pagina_carrega_o_css_de_todos_os_temas_e_publica_o_catalogo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = _criar_app(monkeypatch, RepositorioFalso(), _registro_com_tema_claro())

    html = _cliente_autenticado(app).get("/pagina").text

    assert 'data-luft-tema-css="luft"' in html
    assert 'data-luft-tema-css="luft-esg"' in html
    assert "/_luftbase/static/css/temas/luft-esg.css" in html
    catalogo = re.search(r'id="luft-temas-config">(.*?)</script>', html, re.S)
    assert catalogo is not None
    compacto = re.sub(r"\s+", "", catalogo.group(1))
    assert '"id":"so-claro"' in compacto
    assert '"modos":["claro"]' in compacto


def test_drawer_de_perfil_lista_os_temas_registrados(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = _criar_app(monkeypatch, RepositorioFalso(), _registro_com_tema_claro())

    html = _cliente_autenticado(app).get("/pagina").text

    assert 'name="perfil_tema_preferido" value="luft-esg"' in html
    assert 'name="perfil_tema_preferido" value="so-claro"' in html
    assert "Somente modo claro" in html
    assert "Claro e escuro" in html


def test_put_preferencia_informa_modo_efetivo_e_bloqueio(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repositorio = RepositorioFalso()
    app = _criar_app(monkeypatch, repositorio, _registro_com_tema_claro())
    cliente = _cliente_autenticado(app)
    token = re.search(r'name="luft-csrf-token" content="([^"]+)"', cliente.get("/pagina").text)
    assert token is not None

    resposta = cliente.put(
        "/_luftbase/interface/preferencia",
        json={"tema": "so-claro", "modo": "ESCURO"},
        headers={"X-CSRF-Token": token.group(1)},
    )

    assert resposta.status_code == 200
    assert resposta.json["tema"] == "so-claro"
    assert resposta.json["modo"] == "ESCURO"
    assert resposta.json["modo_efetivo"] == "CLARO"
    assert resposta.json["modo_bloqueado"] is True
    assert resposta.json["modos_suportados"] == ["CLARO"]
    assert repositorio.salvas[-1] == (15, PreferenciaTema("so-claro", ModoTema.ESCURO))


def test_css_luft_esg_define_tokens_e_os_dois_modos() -> None:
    from luftbase.cli.tema import validar_css_tema

    css = (ESTATICO / "css" / "temas" / "luft-esg.css").read_text(encoding="utf-8")

    assert validar_css_tema(css) == []
    assert 'html[data-luft-theme="luft-esg"][data-theme="dark"]' in css
    # O escuro precisa vencer o [data-theme="dark"] que themes.css aplica tambem ao <body>.
    assert 'html[data-luft-theme="luft-esg"][data-theme="dark"] body' in css
    for token in ("--luft-primary-600", "--luft-brand", "--luft-bg-app", "--luft-primary-hover"):
        assert css.count(token + ":") >= 2, f"{token} deve existir no claro e no escuro"


def test_base_js_expoe_alternar_modo_e_mantem_alias_deprecado() -> None:
    js = (ESTATICO / "js" / "base.js").read_text(encoding="utf-8")

    assert "alternarModo: function()" in js
    assert "definirTema: function" in js
    assert "aplicarTema: function" in js
    assert "alternarTema: function()" in js
    assert "this.alternarModo();" in js
    assert "oferece apenas o modo" in js


def test_cores_de_marca_do_css_mantem_fallback_igual_ao_azul_original() -> None:
    css = (ESTATICO / "css" / "sidebar.css").read_text(encoding="utf-8")

    assert "var(--luft-brand, #1d63d8)" in css
    assert "rgba(var(--luft-brand-rgb, 29, 99, 216)" in css
