"""IP real do usuario atras do nginx, total de logins e a tela de perfil (foto/idioma)."""

from __future__ import annotations

import re
import threading
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from flask import Flask, request

from luftbase import servidor
from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL

RAIZ = Path(servidor.__file__).resolve().parent / "interface"
DRAWER = (RAIZ / "templates" / "luftbase" / "perfil" / "drawer.html").read_text(encoding="utf-8")
JS = (RAIZ / "static" / "js" / "perfil.js").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "css" / "perfil.css").read_text(encoding="utf-8")


# ---- IP do cliente ------------------------------------------------------------------------


def _servir(configuracao: servidor.ConfiguracaoServidor, cabecalhos: dict[str, str]) -> str:
    """Sobe um Waitress real, faz uma requisicao e devolve o IP que a aplicacao enxergou."""

    from waitress import create_server

    app = Flask("ip")

    @app.get("/ip")
    def ip() -> str:
        return request.remote_addr or ""

    servidor_http = create_server(
        app, host="127.0.0.1", port=0, ident=None, **configuracao.argumentos_proxy
    )
    fio = threading.Thread(target=servidor_http.run, daemon=True)
    fio.start()
    try:
        porta = servidor_http.effective_port
        pedido = urllib.request.Request(f"http://127.0.0.1:{porta}/ip", headers=cabecalhos)
        with urllib.request.urlopen(pedido, timeout=5) as resposta:  # noqa: S310
            return resposta.read().decode()
    finally:
        servidor_http.close()


def test_com_nginx_confiavel_a_aplicacao_enxerga_o_ip_do_usuario() -> None:
    configuracao = servidor.ConfiguracaoServidor()

    assert _servir(configuracao, {"X-Forwarded-For": "10.9.8.7"}) == "10.9.8.7"


def test_so_vale_o_ip_que_o_proxy_acrescentou_e_nao_o_que_o_cliente_forjou() -> None:
    # nginx faz `$proxy_add_x_forwarded_for`: "o-que-o-cliente-mandou, ip-visto-pelo-nginx".
    configuracao = servidor.ConfiguracaoServidor()

    visto = _servir(configuracao, {"X-Forwarded-For": "6.6.6.6, 10.9.8.7"})

    assert visto == "10.9.8.7"


def test_sem_confiar_no_proxy_o_cabecalho_e_descartado() -> None:
    # Foi exatamente o que acontecia: sem `trusted_proxy` o Waitress apaga X-Forwarded-*.
    configuracao = servidor.ConfiguracaoServidor(proxy_confiavel="")

    assert _servir(configuracao, {"X-Forwarded-For": "10.9.8.7"}) == "127.0.0.1"


def test_proxy_confiavel_vem_do_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LUFT_PROXY_CONFIAVEL", raising=False)
    assert servidor.ConfiguracaoServidor.de_ambiente().proxy_confiavel == "127.0.0.1"

    monkeypatch.setenv("LUFT_PROXY_CONFIAVEL", "10.0.0.5")
    assert servidor.ConfiguracaoServidor.de_ambiente().proxy_confiavel == "10.0.0.5"

    monkeypatch.setenv("LUFT_PROXY_CONFIAVEL", "desligado")
    configuracao = servidor.ConfiguracaoServidor.de_ambiente()
    assert configuracao.proxy_confiavel == "" and configuracao.argumentos_proxy == {}


def test_a_sessao_grava_o_ip_resolvido_e_nao_o_cabecalho_cru() -> None:
    import json
    from datetime import datetime

    from sqlalchemy import create_engine, event, select
    from sqlalchemy.pool import StaticPool

    from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
    from luftbase.persistencia.core.sessoes import Sessao

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def anexar(dbapi_connection, _registro):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS core")
        cursor.close()

    with engine.begin() as conexao:
        conexao.exec_driver_sql(
            "CREATE TABLE core.tb_sessao (id_sessao VARCHAR(128) PRIMARY KEY, id_sistema INTEGER,"
            " codigo_usuario INTEGER, login_usuario VARCHAR(100), ip_origem VARCHAR(50),"
            " user_agent VARCHAR(500), dados_sessao TEXT, status VARCHAR(20) DEFAULT 'ATIVA' NOT NULL,"
            " total_renovacoes INTEGER DEFAULT 0 NOT NULL, criada_em TIMESTAMP NOT NULL,"
            " ultima_atividade TIMESTAMP NOT NULL, expira_em TIMESTAMP NOT NULL,"
            " encerrada_em TIMESTAMP, motivo_encerramento VARCHAR(100))"
        )
        conexao.exec_driver_sql(
            "CREATE TABLE core.tb_sessao_evento (id_evento_sessao INTEGER PRIMARY KEY AUTOINCREMENT,"
            " id_sessao VARCHAR(128) NOT NULL, id_sistema INTEGER, codigo_usuario INTEGER,"
            " login_usuario VARCHAR(100), tipo_evento VARCHAR(30) NOT NULL, ip_origem VARCHAR(50),"
            " user_agent VARCHAR(500), data_hora TIMESTAMP NOT NULL, detalhes TEXT)"
        )
    banco = BancoSQLAlchemy("core", engine)
    armazenamento = ArmazenamentoSessoesPostgreSQL(banco)
    carga = json.dumps(
        {
            "versao": 1,
            "salva_em": datetime.now().isoformat(),
            "dados": {"luftbase_usuario": {"id_usuario": 3049, "login": "teste.ti"}},
        }
    ).encode("utf-8")
    app = Flask("t")
    app.config["LUFT_SISTEMA_ID"] = 0

    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "10.9.8.7"}, headers={"X-Forwarded-For": "6.6.6.6"}
    ):
        armazenamento.salvar("luft:sessao:s1", carga, 600)

    with banco.leitura() as db:
        assert db.execute(select(Sessao)).scalar_one().ip_origem == "10.9.8.7"


# ---- Total de logins ----------------------------------------------------------------------


def _usuario() -> SimpleNamespace:
    return SimpleNamespace(
        total_logins=0,
        status_online=False,
        id_sessao_atual=None,
        ultimo_acesso=None,
        ultimo_ip=None,
        ultimo_user_agent=None,
    )


def _ativar(usuario: SimpleNamespace, *, novo_login: bool) -> None:
    sessao = MagicMock()
    sessao.get.return_value = usuario
    ArmazenamentoSessoesPostgreSQL._atualizar_usuario_ao_ativar(
        sessao, 3049, "s1", None, "10.0.0.1", "navegador", novo_login=novo_login
    )


def test_login_novo_soma_um_e_renovacao_nao_soma() -> None:
    usuario = _usuario()

    _ativar(usuario, novo_login=True)
    assert usuario.total_logins == 1

    for _ in range(5):  # polling e navegacao so renovam a sessao
        _ativar(usuario, novo_login=False)
    assert usuario.total_logins == 1

    _ativar(usuario, novo_login=True)
    assert usuario.total_logins == 2
    assert usuario.status_online is True and usuario.ultimo_ip == "10.0.0.1"


def test_total_de_logins_parte_de_zero_mesmo_se_o_campo_vier_vazio() -> None:
    usuario = _usuario()
    usuario.total_logins = None  # type: ignore[assignment]

    _ativar(usuario, novo_login=True)

    assert usuario.total_logins == 1


# ---- Tela de perfil -----------------------------------------------------------------------


def test_barra_de_acoes_do_avatar_foi_removida() -> None:
    assert "luft-perfil-avatar-actions" not in DRAWER
    assert "btn-luft-alterar-foto" not in DRAWER and "btn-luft-remover-foto" not in DRAWER
    assert "luft-perfil-avatar-actions" not in CSS
    assert "btn-luft-alterar-foto" not in JS and "btn-luft-remover-foto" not in JS


def test_idioma_esta_comentado_e_nao_chega_ao_html() -> None:
    comentarios = re.findall(r"\{#.*?#\}", DRAWER, re.S)
    fora = re.sub(r"\{#.*?#\}", "", DRAWER, flags=re.S)

    assert any("campo-perfil-idioma" in c for c in comentarios)
    assert "campo-perfil-idioma" not in fora and "Idioma da Interface" not in fora


def test_idioma_nao_e_enviado_quando_o_campo_nao_existe() -> None:
    assert "campo-perfil-idioma') ? { idioma:" in JS  # so envia se o campo existir


def test_gatilho_da_camera_abre_o_editor_com_os_controles_esperados() -> None:
    ids_html = set(re.findall(r'id="([^"]+)"', DRAWER))
    ids_js = set(re.findall(r"el\('(luft-foto-[a-z-]+)'\)", JS)) | {
        "luft-foto-modal",
        "luft-perfil-avatar-upload-trigger",
    }

    assert not (ids_js - ids_html), f"ids do JS sem elemento: {sorted(ids_js - ids_html)}"
    for recurso in (
        "luft-foto-zoom",
        "luft-foto-girar-esq",
        "luft-foto-remover",
        "luft-foto-salvar",
    ):
        assert recurso in ids_html
    assert "luft-perfil-avatar-selo" in DRAWER and ".luft-perfil-avatar-selo" in CSS


def test_editor_nao_usa_alert_nem_confirm_e_fica_acima_do_drawer() -> None:
    editor = JS[JS.index("EDITOR DE FOTO") : JS.index("_atualizarAvataresNaInterface: function")]

    assert "alert(" not in editor and "confirm(" not in editor
    assert "document.body.appendChild(modal)" in editor  # o drawer tem transform
    assert re.search(r"\.luft-foto-modal \{[^}]*z-index: 1100", CSS)
    assert "Confirmar remoção" in editor
