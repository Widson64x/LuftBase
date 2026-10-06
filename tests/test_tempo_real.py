"""Painel "ao vivo" da auditoria: consolidação, rota protegida e arquivos do front."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from luftbase import servidor
from luftbase.observabilidade.tempo_real import consolidar_tempo_real

RAIZ = Path(servidor.__file__).resolve().parent / "interface"
AGORA = datetime(2026, 10, 6, 16, 0, 0)
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EDGE = CHROME + " Edg/126.0.2592.81"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


def _sessao(codigo: int, login: str, agente: str, *, inativo_s: int, conectado_s: int = 3600, sistema: int = 0) -> dict:
    return {
        "codigo_usuario": codigo,
        "login": login,
        "nome": login.title(),
        "grupo": "TI",
        "id_sistema": sistema,
        "ip_origem": "10.0.0.5",
        "user_agent": agente,
        "criada_em": AGORA - timedelta(seconds=conectado_s),
        "ultima_atividade": AGORA - timedelta(seconds=inativo_s),
    }


def _acesso(segundos: int, codigo: int | None, login: str, rota: str, *, status: int = 200, duracao: int = 40) -> dict:
    return {
        "data_hora": AGORA - timedelta(seconds=segundos),
        "codigo_usuario": codigo,
        "login": login,
        "rota": rota,
        "metodo": "GET",
        "status": status,
        "duracao_ms": duracao,
        "id_sistema": 0,
        "ip": "10.0.0.5",
    }


def test_conta_quem_esta_online_e_agrupa_navegadores_sem_a_versao() -> None:
    sessoes = [
        _sessao(1, "ana", CHROME, inativo_s=20),
        _sessao(2, "bia", CHROME.replace("126", "125"), inativo_s=100),
        _sessao(3, "caio", EDGE, inativo_s=200),
        _sessao(4, "davi", IPHONE, inativo_s=30),
        _sessao(5, "eva", CHROME, inativo_s=1800),  # sessão aberta, mas parada há 30 min
    ]

    r = consolidar_tempo_real(sessoes, [], agora=AGORA)

    assert r["kpis"]["usuarios_online"] == 4 and r["kpis"]["sessoes_ativas"] == 5
    nav = {i["nome"]: i["total"] for i in r["navegadores"]}
    assert nav == {"Chrome": 2, "Edge": 1, "Safari": 1}  # a sessão ociosa não conta
    assert {i["nome"] for i in r["dispositivos"]} == {"desktop", "mobile"}
    assert r["navegadores"][0]["percentual"] == 50.0


def test_estado_de_cada_pessoa_e_ordem_por_atividade() -> None:
    sessoes = [_sessao(2, "bia", CHROME, inativo_s=200), _sessao(1, "ana", CHROME, inativo_s=10), _sessao(3, "caio", CHROME, inativo_s=900)]

    r = consolidar_tempo_real(sessoes, [], agora=AGORA)

    assert [o["login"] for o in r["online"]] == ["ana", "bia", "caio"]
    assert [o["estado"] for o in r["online"]] == ["ativo", "recente", "ocioso"]


def test_mostra_o_que_cada_pessoa_fez_por_ultimo_ignorando_chamadas_automaticas() -> None:
    sessoes = [_sessao(1, "ana", CHROME, inativo_s=10)]
    acessos = [
        _acesso(5, 1, "ana", "/_luftbase/notificacoes/contar"),  # polling do sino
        _acesso(8, 1, "ana", "/static/js/base.js"),
        _acesso(30, 1, "ana", "/Luft-Integrador/parametros"),
        _acesso(90, 1, "ana", "/"),
    ]

    r = consolidar_tempo_real(sessoes, acessos, agora=AGORA)

    assert r["online"][0]["fazendo"]["rota"] == "/Luft-Integrador/parametros"
    assert r["online"][0]["fazendo"]["ha_segundos"] == 30
    assert [a["rota"] for a in r["atividade"]] == ["/Luft-Integrador/parametros", "/"]


def test_indicadores_de_trafego_e_erros() -> None:
    acessos = [
        _acesso(10, 1, "ana", "/a", duracao=20),
        _acesso(60, 1, "ana", "/b", duracao=40),
        _acesso(120, 2, "bia", "/c", status=500, duracao=60),
        _acesso(600, 2, "bia", "/d", status=502),  # fora dos 5 min, mas dentro dos 15
    ]

    k = consolidar_tempo_real([], acessos, agora=AGORA)["kpis"]

    assert k["requisicoes_5min"] == 3 and k["requisicoes_por_minuto"] == 0.6
    assert k["tempo_medio_ms"] == 40 and k["erros_15min"] == 2


def test_sem_dados_nao_quebra() -> None:
    r = consolidar_tempo_real([], [], agora=AGORA)

    assert r["online"] == [] and r["atividade"] == [] and r["navegadores"] == []
    assert r["kpis"]["tempo_medio_ms"] == 0 and r["kpis"]["usuarios_online"] == 0


def test_sessao_sem_usuario_conhecido_e_agente_vazio() -> None:
    sessao = _sessao(1, "ana", "", inativo_s=10)
    sessao.update(codigo_usuario=None, login=None, nome=None)

    r = consolidar_tempo_real([sessao], [], agora=AGORA, nomes_sistemas={0: "Luft-Workspace"})

    pessoa = r["online"][0]
    assert pessoa["nome"] == "Usuário" and pessoa["navegador"] == "Desconhecido"
    assert pessoa["sistema"] == "Luft-Workspace" and r["kpis"]["usuarios_online"] == 0


def test_rota_exige_permissao_de_auditoria_e_os_arquivos_do_front_existem() -> None:
    from luftbase.web import auditoria

    funcao = auditoria.api_tempo_real
    assert getattr(funcao, "__wrapped__", None) is not None  # protegida por login/permissão
    modelo = (RAIZ / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
    js = (RAIZ / "static" / "js" / "auditoria_ao_vivo.js").read_text(encoding="utf-8")
    css = (RAIZ / "static" / "css" / "auditoria.css").read_text(encoding="utf-8")
    assert "auditoria_ao_vivo.js" in modelo and "data-tempo-real-url" in modelo
    for id_html in ("auditLiveOnline", "auditLiveFeed", "auditLiveNavegadores", "auditLiveSistemas", "auditLivePausar"):
        assert f'id="{id_html}"' in modelo and id_html in js, id_html
    assert ".audit-live-pessoa" in css and "prefers-reduced-motion" in css
    assert "innerHTML" in js and "esc(" in js  # todo texto dinâmico passa pelo escape


@pytest.mark.parametrize("rota", ["/static/css/a.css", "/x/notificacoes/lidas", "/_luftbase/perfil/sessoes"])
def test_chamadas_automaticas_nao_aparecem_no_feed(rota: str) -> None:
    r = consolidar_tempo_real([], [_acesso(5, 1, "ana", rota)], agora=AGORA)

    assert r["atividade"] == []


# ---- consulta de verdade (SQLite com as tabelas que a consulta usa) -----------------------


def _banco_com_dados():
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
    from luftbase.nucleo.tempo import agora_local

    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def anexar(dbapi_connection, _registro):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS core")
        cursor.close()

    ddl = [
        "CREATE TABLE core.tb_sistema (id_sistema INTEGER PRIMARY KEY, nome_sistema VARCHAR(100))",
        "CREATE TABLE core.tb_usuario (codigo_usuario INTEGER PRIMARY KEY, nome_usuario VARCHAR(255),"
        " sigla_usuariogrupo VARCHAR(100))",
        "CREATE TABLE core.tb_sessao (id_sessao VARCHAR(128) PRIMARY KEY, id_sistema INTEGER, codigo_usuario INTEGER,"
        " login_usuario VARCHAR(100), ip_origem VARCHAR(50), user_agent VARCHAR(500), dados_sessao TEXT,"
        " status VARCHAR(20), total_renovacoes INTEGER DEFAULT 0, criada_em TIMESTAMP, ultima_atividade TIMESTAMP,"
        " expira_em TIMESTAMP, encerrada_em TIMESTAMP, motivo_encerramento VARCHAR(100))",
        "CREATE TABLE core.tb_logs (id_log INTEGER PRIMARY KEY AUTOINCREMENT, id_sistema INTEGER, codigo_usuario INTEGER,"
        " login_usuario VARCHAR(100), codigo_grupo INTEGER, nome_grupo VARCHAR(100), rota_acessada VARCHAR(500),"
        " metodo_http VARCHAR(10), ip_origem VARCHAR(50), user_agent VARCHAR(500), permissao_exigida VARCHAR(180),"
        " acesso_permitido BOOLEAN, parametros_requisicao TEXT, resposta_acao TEXT, id_correlacao VARCHAR(64),"
        " duracao_ms INTEGER, status_http INTEGER, data_hora TIMESTAMP)",
    ]
    agora = agora_local()
    with engine.begin() as con:
        for comando in ddl:
            con.exec_driver_sql(comando)
        con.exec_driver_sql("INSERT INTO core.tb_sistema VALUES (0, 'Luft-Workspace'), (3, 'Luft-Integrador')")
        con.exec_driver_sql("INSERT INTO core.tb_usuario VALUES (1, 'Ana Souza', 'TI'), (2, 'Bia Lima', 'OPS')")
        sessoes = [
            ("s1", 0, 1, "ana", CHROME, 20, "ATIVA"),
            ("s2", 3, 2, "bia", IPHONE, 40, "ATIVA"),
            ("s3", 0, 2, "bia", CHROME, 10, "FINALIZADA"),  # encerrada: não aparece
        ]
        for id_sessao, sis, cod, login, agente, inativo, status in sessoes:
            con.exec_driver_sql(
                "INSERT INTO core.tb_sessao (id_sessao, id_sistema, codigo_usuario, login_usuario, ip_origem, user_agent,"
                " status, criada_em, ultima_atividade, expira_em) VALUES (?, ?, ?, ?, '10.0.0.9', ?, ?, ?, ?, ?)",
                (id_sessao, sis, cod, login, agente, status, agora - timedelta(hours=1),
                 agora - timedelta(seconds=inativo), agora + timedelta(hours=1)),
            )
        acessos = [(0, 1, "ana", "/painel", 30, 200), (3, 2, "bia", "/Luft-Integrador/parametros", 50, 500)]
        for sis, cod, login, rota, seg, status in acessos:
            con.exec_driver_sql(
                "INSERT INTO core.tb_logs (id_sistema, codigo_usuario, login_usuario, rota_acessada, metodo_http,"
                " ip_origem, id_correlacao, duracao_ms, status_http, data_hora) VALUES (?, ?, ?, ?, 'GET', '10.0.0.9',"
                " 'c', 25, ?, ?)",
                (sis, cod, login, rota, status, agora - timedelta(seconds=seg)),
            )
    return BancoSQLAlchemy("core", engine)


def test_consulta_real_traz_sessoes_ativas_nomes_e_o_que_fazem() -> None:
    from luftbase.observabilidade.tempo_real import ServicoTempoReal

    r = ServicoTempoReal(_banco_com_dados()).obter()

    assert r["kpis"]["usuarios_online"] == 2 and r["kpis"]["sessoes_ativas"] == 2  # a finalizada não conta
    por_login = {o["login"]: o for o in r["online"]}
    assert por_login["ana"]["nome"] == "Ana Souza" and por_login["ana"]["sistema"] == "Luft-Workspace"  # sistema 0
    assert por_login["bia"]["sistema"] == "Luft-Integrador" and por_login["bia"]["dispositivo"] == "mobile"
    assert por_login["ana"]["fazendo"]["rota"] == "/painel"
    assert r["kpis"]["erros_15min"] == 1 and len(r["atividade"]) == 2


def test_consulta_real_respeita_o_escopo_do_sistema() -> None:
    from luftbase.observabilidade.tempo_real import ServicoTempoReal

    r = ServicoTempoReal(_banco_com_dados()).obter(id_sistema=3)

    assert [o["login"] for o in r["online"]] == ["bia"]
    assert [a["rota"] for a in r["atividade"]] == ["/Luft-Integrador/parametros"]
