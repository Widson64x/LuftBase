"""Drill-down da auditoria: clicar num gráfico ou tabela vira um filtro que traz os registros correspondentes."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from luftbase.identidade.agente_usuario import interpretar_agente
from luftbase.observabilidade.analise import FiltroAuditoria, PaginaAuditoria, ServicoAnaliseAuditoria
from luftbase.observabilidade.filtros import NAVEGADORES, padrao_rota
from luftbase.observabilidade.insights import ServicoInsights

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EDGE = CHROME + " Edg/126.0.2592.81"
OPERA = CHROME + " OPR/110.0.0.0"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
SAFARI = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
SAMSUNG = "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
IE = "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko"

FIM = datetime(2026, 10, 9, 18, 0)  # quinta-feira
INICIO = FIM - timedelta(days=5)


def _banco(logs, sessoes=()):
    from sqlalchemy import create_engine, event
    from sqlalchemy.pool import StaticPool

    from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy

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
        "CREATE TABLE core.tb_logevento (id_logevento INTEGER PRIMARY KEY AUTOINCREMENT, id_sistema INTEGER, id_log INTEGER,"
        " codigo_usuario INTEGER, login_usuario VARCHAR(100), codigo_grupo INTEGER, nome_grupo VARCHAR(100),"
        " acao VARCHAR(80), recurso VARCHAR(150), id_recurso VARCHAR(150), descricao VARCHAR(1000), ip_origem VARCHAR(50),"
        " user_agent VARCHAR(500), severidade VARCHAR(20), traceback TEXT, id_correlacao VARCHAR(64), data_hora TIMESTAMP)",
    ]
    with engine.begin() as con:
        for comando in ddl:
            con.exec_driver_sql(comando)
        con.exec_driver_sql("INSERT INTO core.tb_sistema VALUES (0, 'Luft-Workspace')")
        con.exec_driver_sql("INSERT INTO core.tb_usuario VALUES (1, 'Ana Souza', 'TI'), (2, 'Bia Lima', 'OPS')")
        for rota, metodo, status, login, grupo, ip, agente, quando, permitido in logs:
            con.exec_driver_sql(
                "INSERT INTO core.tb_logs (id_sistema, codigo_usuario, login_usuario, nome_grupo, rota_acessada, metodo_http,"
                " ip_origem, user_agent, id_correlacao, duracao_ms, status_http, data_hora, acesso_permitido)"
                " VALUES (0, ?, ?, ?, ?, ?, ?, ?, 'c', 20, ?, ?, ?)",
                (1 if login == "ana" else 2, login, grupo, rota, metodo, ip, agente, status, quando, permitido),
            )
        for i, (login, ip, agente, status, motivo, criada, expira) in enumerate(sessoes):
            con.exec_driver_sql(
                "INSERT INTO core.tb_sessao (id_sessao, id_sistema, codigo_usuario, login_usuario, ip_origem, user_agent,"
                " status, criada_em, ultima_atividade, expira_em, encerrada_em, motivo_encerramento)"
                " VALUES (?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (f"s{i}", 1 if login == "ana" else 2, login, ip, agente, status, criada, criada + timedelta(minutes=30),
                 expira, None if status == "ATIVA" else criada + timedelta(minutes=30), motivo),
            )
    return BancoSQLAlchemy("core", engine)


def _d(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto)


LOGS = [
    ("/clientes/1/testar", "GET", 200, "ana", "TI", "10.0.0.1", CHROME, _d(5, 10, 15), None),  # segunda
    ("/clientes/2/testar", "POST", 500, "ana", "TI", "10.0.0.1", CHROME, _d(5, 10, 40), None),  # segunda
    ("/painel", "GET", 302, "bia", "OPS", "10.0.0.2", EDGE, _d(6, 14, 5), None),  # terça
    ("/painel", "GET", 200, "bia", "OPS", "10.0.0.2", FIREFOX, _d(6, 14, 30), None),  # terça
    ("/x", "GET", 403, "bia", "OPS", "10.0.0.3", SAFARI, _d(7, 9, 0), False),  # quarta
    ("/clientes/9/testar", "GET", 200, "ana", "TI", "10.0.0.1", CHROME, _d(8, 10, 20), None),  # quinta
    ("/y", "GET", 200, "bia", "OPS", "10.0.0.4", None, _d(8, 17, 0), None),  # quinta, sem navegador
]


def _acessos(banco, **drill) -> list[str]:
    filtro = FiltroAuditoria(inicio=INICIO, fim=FIM, **drill)
    itens = ServicoAnaliseAuditoria(banco).listar_acessos(filtro, PaginaAuditoria(1, 100))["itens"]
    return [i["rota"] for i in itens]


@pytest.fixture(scope="module")
def banco():
    return _banco(LOGS)


def test_clique_em_rota_agrupa_os_ids(banco) -> None:
    assert len(_acessos(banco, rota="/clientes/:id/testar")) == 3
    assert _acessos(banco, rota="/clientes/:id/testar", metodo="POST") == ["/clientes/2/testar"]
    assert _acessos(banco, rota="/painel") == ["/painel", "/painel"]


def test_clique_em_pessoa_ip_e_grupo(banco) -> None:
    assert len(_acessos(banco, login="ana")) == 3
    assert len(_acessos(banco, ip="10.0.0.2")) == 2
    assert len(_acessos(banco, grupo_nome="OPS")) == 4


def test_clique_no_mapa_de_calor_hora_e_dia(banco) -> None:
    assert len(_acessos(banco, hora=10)) == 3  # 10h de segunda e quinta
    assert _acessos(banco, hora=10, dia_semana=0) == ["/clientes/2/testar", "/clientes/1/testar"]  # só segunda
    assert len(_acessos(banco, dia_semana=1)) == 2  # terça
    assert _acessos(banco, hora=3) == []


def test_clique_na_rosca_de_status(banco) -> None:
    assert _acessos(banco, resultado_http="redirecionamento") == ["/painel"]
    assert _acessos(banco, resultado_http="servidor") == ["/clientes/2/testar"]
    assert _acessos(banco, resultado_http="negado") == ["/x"]
    assert len(_acessos(banco, resultado_http="sucesso")) == 4  # só 2xx; os 3xx têm o próprio recorte


@pytest.mark.parametrize(
    ("navegador", "esperado"),
    [("Chrome", 3), ("Edge", 1), ("Firefox", 1), ("Safari", 1), ("Desconhecido", 1), ("Opera", 0)],
)
def test_clique_em_navegador(banco, navegador: str, esperado: int) -> None:
    assert len(_acessos(banco, navegador=navegador)) == esperado


def test_cada_user_agent_cai_exatamente_no_navegador_que_o_grafico_contou() -> None:
    amostras = [CHROME, EDGE, OPERA, FIREFOX, SAFARI, SAMSUNG, ANDROID, IE]
    logs = [("/a", "GET", 200, "ana", "TI", "10.0.0.1", ua, _d(6, 9), None) for ua in amostras]
    banco = _banco(logs)

    for nome in NAVEGADORES:
        no_sql = len(_acessos(banco, navegador=nome))
        no_parser = sum(
            1 for ua in amostras if (interpretar_agente(ua)["navegador"] or "").rsplit(" ", 1)[0] == nome
        )
        assert no_sql == no_parser, f"{nome}: SQL achou {no_sql}, o parser {no_parser}"


def test_padrao_de_rota_escapa_caracteres_do_like() -> None:
    assert padrao_rota("/a/:id/b") == "/a/%/b"
    assert padrao_rota("/100%_certo") == "/100\\%\\_certo"


def test_mapa_de_calor_e_rosca_mostram_o_todo_mesmo_com_o_proprio_recorte() -> None:
    banco = _banco(LOGS)
    servico = ServicoInsights(banco)

    recortado = servico.obter(FiltroAuditoria(inicio=INICIO, fim=FIM, hora=10, dia_semana=0, resultado_http="servidor"))
    so_resultado = servico.obter(FiltroAuditoria(inicio=INICIO, fim=FIM, resultado_http="servidor"))
    so_hora_e_dia = servico.obter(FiltroAuditoria(inicio=INICIO, fim=FIM, hora=10, dia_semana=0))

    # o mapa ignora hora e dia (a própria dimensão), mas respeita os outros recortes
    assert recortado["mapa_calor"]["matriz"] == so_resultado["mapa_calor"]["matriz"]
    # a rosca ignora o resultado (a própria dimensão), mas respeita hora e dia
    assert recortado["status"] == so_hora_e_dia["status"]
    assert recortado["comparativo"]["atual"]["requisicoes"] == 1  # os números do recorte, sim, encolhem


def test_destaques_trazem_a_acao_do_clique() -> None:
    banco = _banco(LOGS)

    d = ServicoInsights(banco).obter(FiltroAuditoria(inicio=INICIO, fim=FIM))["destaques"]

    erro = next(x for x in d if "erro(s)" in x["titulo"])
    assert erro["acao"] == {"drill": {"resultado": "servidor"}, "ir": "registros", "aba": "acessos"}
    pico = next(x for x in d if x["titulo"].startswith("Pico"))
    assert pico["acao"]["drill"] == {"hora": 10, "dia_semana": 0}


def test_eventos_tambem_respondem_ao_recorte() -> None:
    banco = _banco(LOGS)
    with banco.unidade_trabalho() as db:
        db.connection().exec_driver_sql(
            "INSERT INTO core.tb_logevento (id_sistema, codigo_usuario, login_usuario, acao, recurso, descricao,"
            " severidade, ip_origem, user_agent, data_hora) VALUES (0, 1, 'ana', 'EXCLUIR', 'u', 'x', 'ALTA', '10.0.0.1', ?, ?),"
            " (0, 2, 'bia', 'VER', 'u', 'y', 'BAIXA', '10.0.0.2', ?, ?)",
            (CHROME, _d(5, 10, 0), EDGE, _d(6, 14, 0)),
        )

    def eventos(**drill):
        filtro = FiltroAuditoria(inicio=INICIO, fim=FIM, **drill)
        return [e["acao"] for e in ServicoAnaliseAuditoria(banco).listar_detalhes(filtro, PaginaAuditoria(1, 50))["itens"]]

    assert eventos(login="ana") == ["EXCLUIR"] and eventos(ip="10.0.0.2") == ["VER"]
    assert eventos(navegador="Edge") == ["VER"] and eventos(hora=10, dia_semana=0) == ["EXCLUIR"]


# ---- sessões ------------------------------------------------------------------------------

SESSOES = [
    ("ana", "10.0.0.1", CHROME, "FINALIZADA", "LOGOUT_VOLUNTARIO", _d(8, 9), _d(8, 21)),
    ("ana", "10.0.0.1", CHROME, "FINALIZADA", "TIMEOUT_INATIVIDADE", _d(7, 9), _d(7, 21)),
    ("bia", "10.0.0.2", EDGE, "ATIVA", None, _d(9, 17), _d(9, 23)),  # ainda vale às 18h
    ("bia", "10.0.0.2", FIREFOX, "ATIVA", None, _d(6, 8), _d(6, 9)),  # ATIVA no banco, mas já expirou
]


def _sessoes(banco, **drill):
    filtro = FiltroAuditoria(inicio=INICIO, fim=FIM, **drill)
    return ServicoInsights(banco).listar_sessoes(filtro, PaginaAuditoria(1, 50))


def test_lista_de_sessoes_com_navegador_e_situacao() -> None:
    banco = _banco(LOGS, SESSOES)

    r = _sessoes(banco)

    assert r["total"] == 4
    por_nav = {i["navegador"].split(" ")[0]: i for i in r["itens"]}
    assert por_nav["Edge"]["situacao"] == "Em andamento" and por_nav["Firefox"]["situacao"] == "Expirou"
    assert por_nav["Chrome"]["duracao_segundos"] == 30 * 60 and por_nav["Chrome"]["nome"] == "Ana Souza"


def test_sessoes_respondem_a_pessoa_ip_navegador_e_motivo() -> None:
    banco = _banco(LOGS, SESSOES)

    assert _sessoes(banco, login="ana")["total"] == 2
    assert _sessoes(banco, ip="10.0.0.2")["total"] == 2
    assert _sessoes(banco, navegador="Chrome")["total"] == 2
    assert _sessoes(banco, motivo="TIMEOUT_INATIVIDADE")["total"] == 1
    assert _sessoes(banco, motivo="ATIVA")["total"] == 1 and _sessoes(banco, motivo="EXPIRADA")["total"] == 1
    assert _sessoes(banco, hora=9, dia_semana=3)["total"] == 1  # quinta, 9h: a da Ana (08/10)


# ---- validação dos parâmetros -----------------------------------------------------------


@pytest.mark.parametrize(
    "consulta",
    ["navegador=Netscape", "hora=24", "hora=abc", "dia_semana=7", "metodo=BREW", "ip=<script>", "motivo=QUALQUER"],
)
def test_parametros_invalidos_sao_recusados(consulta: str) -> None:
    from flask import Flask
    from werkzeug.exceptions import HTTPException

    from luftbase.web.auditoria import _montar_drill

    with Flask("t").test_request_context(f"/?{consulta}"):
        with pytest.raises(HTTPException) as erro:
            _montar_drill()
    assert erro.value.code == 400


def test_parametros_validos_viram_filtro() -> None:
    from flask import Flask

    from luftbase.web.auditoria import _montar_drill

    with Flask("t").test_request_context(
        "/?rota=/a/:id&metodo=post&ip=10.0.0.1&login=ana&grupo=TI&navegador=Chrome&hora=14&dia_semana=0&motivo=logout_voluntario"
    ):
        drill = _montar_drill()

    assert drill == {
        "rota": "/a/:id", "metodo": "POST", "ip": "10.0.0.1", "login": "ana", "grupo_nome": "TI",
        "navegador": "Chrome", "hora": 14, "dia_semana": 0, "motivo": "LOGOUT_VOLUNTARIO",
    }


def test_rota_de_sessoes_esta_protegida() -> None:
    from luftbase.web import auditoria

    assert getattr(auditoria.api_sessoes, "__wrapped__", None) is not None


# ---- front-end: tudo o que o clique usa existe no modelo --------------------------------------


def test_front_do_drill_esta_ligado_ao_modelo() -> None:
    import re
    from pathlib import Path

    from luftbase import servidor

    raiz = Path(servidor.__file__).resolve().parent / "interface"
    modelo = (raiz / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
    drill = (raiz / "static" / "js" / "auditoria_drill.js").read_text(encoding="utf-8")
    visoes = (raiz / "static" / "js" / "auditoria_visoes.js").read_text(encoding="utf-8")
    principal = (raiz / "static" / "js" / "auditoria.js").read_text(encoding="utf-8")
    ao_vivo = (raiz / "static" / "js" / "auditoria_ao_vivo.js").read_text(encoding="utf-8")

    ids = set(re.findall(r'id="([^"]+)"', modelo))
    citados = set(re.findall(r"\$\('([A-Za-z]+)'\)", drill)) | set(re.findall(r"\['(audit[A-Za-z]+)',", drill))
    assert not (citados - ids), sorted(citados - ids)

    # a ordem importa: o estado dos recortes precisa existir antes de auditoria.js montar as consultas
    assert modelo.index("auditoria_drill.js") < modelo.index("auditoria.js")
    assert 'data-log-tab="sessoes"' in modelo and "data-sessoes-url" in modelo
    assert 'value="redirecionamento"' in modelo  # a rosca filtra por 3xx pelo campo Resultado

    # os pontos clicáveis prometidos ao usuário
    assert "tornarClicavel" in principal and "tornarClicavel" in visoes and "tornarClicavel" in ao_vivo
    for gancho in ("window.luftAuditoriaAtualizar", "window.luftAuditoriaAba", "window.luftDrill?.parametros()"):
        assert gancho in principal, gancho
    assert "window.luftAuditoriaVisao" in visoes
    assert "shiftKey" in drill  # Shift+clique só filtra, sem trocar de seção
    # as chaves de recorte do front são exatamente as que o servidor aceita
    chaves_front = set(re.findall(r"PROPRIOS = \[(.*?)\]", drill, re.S)[0].replace("'", "").replace(" ", "").split(","))
    from luftbase.web import auditoria

    fonte_web = Path(auditoria.__file__).read_text(encoding="utf-8")
    for chave in chaves_front:
        assert f'"{chave}"' in fonte_web or f"'{chave}'" in fonte_web or chave == "grupo", chave
