"""Testes do registro, preferencias e perfil web obrigatorio."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask, render_template, render_template_string
from flask_login import LoginManager

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.interface.modelos import ManifestoTema, PreferenciaTema
from luftbase.interface.servico import ServicoTemas, criar_registro_padrao
from luftbase.interface.web import registrar_interface_web
from luftbase.nucleo import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema


class RepositorioFalso:
    """Preferencias em memoria para testar o caso de uso."""

    def __init__(self, preferencia: PreferenciaTema | None = None) -> None:
        self.preferencia = preferencia
        self.salvas: list[tuple[int, PreferenciaTema]] = []

    def obter(self, id_usuario: int) -> PreferenciaTema | None:
        del id_usuario
        return self.preferencia

    def salvar(self, id_usuario: int, preferencia: PreferenciaTema) -> None:
        self.preferencia = preferencia
        self.salvas.append((id_usuario, preferencia))


def test_manifesto_exige_slug_url_local_e_ao_menos_um_modo() -> None:
    with pytest.raises(ErroConfiguracao, match="slug"):
        ManifestoTema("Tema Invalido", "Tema", "1.0.0", "/tema.css")
    with pytest.raises(ErroConfiguracao, match="local"):
        ManifestoTema("tema", "Tema", "1.0.0", "https://cdn/tema.css")
    with pytest.raises(ErroConfiguracao, match="ao menos um modo"):
        ManifestoTema("tema", "Tema", "1.0.0", "/tema.css", frozenset())
    with pytest.raises(ErroConfiguracao, match="SISTEMA"):
        ManifestoTema("tema", "Tema", "1.0.0", "/tema.css", frozenset({ModoTema.SISTEMA}))


def test_manifesto_aceita_tema_de_modo_unico_e_o_marca_como_fixo() -> None:
    claro = ManifestoTema("so-claro", "So Claro", "1.0.0", "/t.css", frozenset({ModoTema.CLARO}))
    completo = ManifestoTema("completo", "Completo", "1.0.0", "/t.css")

    assert claro.modo_unico is ModoTema.CLARO
    assert claro.oferece_alternancia is False
    assert completo.modo_unico is None
    assert completo.oferece_alternancia is True


def test_registro_rejeita_substituicao_silenciosa() -> None:
    registro = criar_registro_padrao()

    with pytest.raises(ErroConfiguracao, match="ja foi registrado"):
        registro.registrar(registro.obter("luft"))  # type: ignore[arg-type]


def test_servico_aplica_fallback_e_persiste_familia_separada_do_modo() -> None:
    repositorio = RepositorioFalso(PreferenciaTema("removido", ModoTema.ESCURO))
    servico = ServicoTemas(repositorio, criar_registro_padrao())

    fallback = servico.obter_preferencia(15)
    alterada = servico.alterar_preferencia(15, "luft", "CLARO")

    assert fallback == PreferenciaTema("luft", ModoTema.ESCURO)
    assert alterada == PreferenciaTema("luft", ModoTema.CLARO)
    assert repositorio.salvas == [(15, alterada)]


def _criar_app(monkeypatch):  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    app.secret_key = "teste"
    app.config["LUFT_APLICACAO_NOME"] = "Aplicacao Teste"
    usuario = UsuarioAutenticado(15, "teste", "Usuario Teste", None, 4, "Grupo")
    login = LoginManager(app)

    @login.user_loader
    def carregar(_identificador: str) -> UsuarioAutenticado:
        return usuario

    repositorio = RepositorioFalso()
    temas = ServicoTemas(repositorio, criar_registro_padrao())
    monkeypatch.setattr(
        "luftbase.plataforma.obter_luftbase",
        lambda: SimpleNamespace(temas=temas),
    )
    registrar_interface_web(app)

    @app.get("/teste-interface")
    def pagina():  # type: ignore[no-untyped-def]
        return render_template("luftbase/base.html")

    return app, repositorio


def _autenticar(cliente) -> None:  # type: ignore[no-untyped-def]
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = "15"
        sessao["_fresh"] = True


def test_base_injeta_assets_tokens_e_marcos_de_acessibilidade(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    cliente = app.test_client()

    resposta = cliente.get("/teste-interface")
    html = resposta.text

    assert resposta.status_code == 200
    assert 'href="#conteudo-principal"' in html
    assert 'id="conteudo-principal"' in html
    assert 'aria-live="polite"' in html
    assert "/_luftbase/static/css/base.css" in html
    assert "/_luftbase/static/css/themes.css" in html
    assert "/_luftbase/static/css/global.css" in html
    assert "/_luftbase/static/css/temas/luft.css" in html
    assert "/_luftbase/static/js/base.js" in html
    assert 'class="luft-sidebar"' in html
    assert "Luft Logistics" in html
    assert "https://" not in html


def test_preferencia_exige_login_e_csrf_e_atualiza_sessao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, repositorio = _criar_app(monkeypatch)
    cliente = app.test_client()
    assert cliente.put("/_luftbase/interface/preferencia", json={}).status_code == 401
    _autenticar(cliente)
    pagina = cliente.get("/teste-interface")
    token = re.search(r'name="luft-csrf-token" content="([^"]+)"', pagina.text)
    assert token is not None

    sem_token = cliente.put(
        "/_luftbase/interface/preferencia",
        json={"tema": "luft", "modo": "ESCURO"},
    )
    resposta = cliente.put(
        "/_luftbase/interface/preferencia",
        json={"tema": "luft", "modo": "ESCURO"},
        headers={"X-CSRF-Token": token.group(1)},
    )

    assert sem_token.status_code == 403
    assert resposta.json["tema"] == "luft"
    assert resposta.json["modo"] == "ESCURO"
    assert resposta.json["modo_efetivo"] == "ESCURO"
    assert resposta.json["modo_bloqueado"] is False
    assert repositorio.salvas[-1] == (15, PreferenciaTema("luft", ModoTema.ESCURO))


def test_assets_obrigatorios_sao_servidos_pelo_blueprint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    cliente = app.test_client()

    css = cliente.get("/_luftbase/static/css/base.css")
    tema = cliente.get("/_luftbase/static/css/temas/luft.css")
    javascript = cliente.get("/_luftbase/static/js/base.js")
    logo = cliente.get("/_luftbase/static/icons/luft-logo-150x150-Dark.png")

    assert css.status_code == tema.status_code == javascript.status_code == logo.status_code == 200
    assert b"--luft-cor-fundo" in tema.data
    assert b"prefers-reduced-motion" in css.data


def test_login_oficial_preserva_identidade_visual_e_csrf(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)

    @app.get("/login-teste")
    def login_teste():  # type: ignore[no-untyped-def]
        return render_template("luftbase/login.html", erro=None, destino="/")

    resposta = app.test_client().get("/login-teste")

    assert resposta.status_code == 200
    assert "Logística que conecta" in resposta.text
    assert 'name="csrf_token"' in resposta.text
    assert 'name="login"' in resposta.text
    assert "/_luftbase/static/css/login.css" in resposta.text
    assert "/_luftbase/static/js/login.js" in resposta.text


def test_macros_geram_rotulos_e_relacoes_acessiveis(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)

    with app.test_request_context():
        html = render_template_string(
            "{% from 'luftbase/componentes.html' import campo, alerta %}"
            "{{ campo('email', 'E-mail', tipo='email', obrigatorio=true, ajuda='Corporativo') }}"
            "{{ alerta('Falha controlada', variante='perigo') }}"
        )

    assert 'for="email"' in html
    assert 'aria-describedby="email-ajuda"' in html
    assert 'aria-required="true"' in html
    assert 'role="alert"' in html


def test_css_nao_depende_de_arquivo_externo() -> None:
    raiz = Path(__file__).parents[1] / "src" / "luftbase" / "interface" / "static"
    conteudo = "\n".join(arquivo.read_text(encoding="utf-8") for arquivo in raiz.rglob("*.css"))

    assert "url(http://" not in conteudo
    assert "url(https://" not in conteudo


def test_breadcrumb_padronizado_exibe_nome_aplicacao_e_casinha(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    app.config["LUFT_APLICACAO_NOME"] = "Luft-WorkSpace"

    @app.get("/teste-base")
    def rota_base():  # type: ignore[no-untyped-def]
        return render_template("luftbase/base.html", pode_ver_painel=True)

    cliente = app.test_client()
    _autenticar(cliente)
    resposta = cliente.get("/teste-base")
    assert resposta.status_code == 200
    assert "ph-fill ph-house" in resposta.text
    assert "Luft-WorkSpace" in resposta.text
    assert ">Modo<" in resposta.text
    assert "LuftBase.alternarModo()" in resposta.text
    assert "alternarTema" not in resposta.text
    assert ">Config.<" in resposta.text
    assert "Painel de Controle / Configurações" in resposta.text
    assert ">Sair<" in resposta.text


def test_css_global_define_acoes_proporcionais() -> None:
    estatico = Path(__file__).parents[1] / "src" / "luftbase" / "interface" / "static"
    raiz = estatico / "css" / "global.css"
    css = raiz.read_text(encoding="utf-8")

    assert ".luft-actions {" in css
    assert "grid-template-columns: repeat(3, 1fr)" in css
    assert ".luft-btn-action {" in css
    assert "height: 38px;" in css
    assert "flex-direction: row;" in css
    assert ".luft-btn-action span {" in css


def test_rodape_versao_ambiente_link_changelog(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app, _ = _criar_app(monkeypatch)
    app.config["LUFT_AMBIENTE"] = "desenvolvimento"
    app.config["LUFT_APLICACAO_VERSAO"] = "0.1.1"

    @app.get("/teste-rodape")
    def rota_rodape():  # type: ignore[no-untyped-def]
        return render_template("luftbase/base.html")

    cliente = app.test_client()
    resposta = cliente.get("/teste-rodape")
    assert resposta.status_code == 200
    assert 'class="luft-footer-version-link text-decoration-none"' in resposta.text
    assert 'class="luft-footer-version-meta"' in resposta.text
    assert "DESENVOLVIMENTO - v0.1.1" in resposta.text
    assert 'title="Ver histórico de atualizações (ChangeLog)"' in resposta.text
