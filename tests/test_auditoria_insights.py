"""Visões analíticas da auditoria: comparativo, mapa de calor, desempenho, segurança e sessões."""

from __future__ import annotations

from datetime import datetime, timedelta

from luftbase.observabilidade.analise import FiltroAuditoria
from luftbase.observabilidade.insights import (
    ServicoInsights,
    agrupar_rotas,
    consolidar_sessoes,
    gerar_destaques,
    montar_mapa_calor,
    normalizar_rota,
)

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"


# ---- funções puras ------------------------------------------------------------------------


def test_normaliza_ids_e_uuids_nas_rotas() -> None:
    assert normalizar_rota("/clientes/42/testar?x=1") == "/clientes/:id/testar"
    assert normalizar_rota("/a/123e4567-e89b-12d3-a456-426614174000") == "/a/:id"
    assert normalizar_rota("/painel") == "/painel" and normalizar_rota("") == "/"


def test_mapa_de_calor_soma_por_dia_da_semana_e_hora() -> None:
    segunda_10h = datetime(2026, 10, 5, 10)  # segunda-feira
    mapa = montar_mapa_calor(
        [(segunda_10h, 5), (segunda_10h + timedelta(days=7), 3), (datetime(2026, 10, 7, 15), 2), ("2026-10-08 15:00:00", 4)]
    )

    assert mapa["matriz"][0][10] == 8  # duas segundas às 10h
    assert mapa["por_hora"][15] == 6 and mapa["maximo"] == 8
    assert (mapa["hora_pico"], mapa["dia_pico"]) == (10, "Seg")
    assert montar_mapa_calor([])["hora_pico"] is None  # sem dados, sem pico


def test_junta_rotas_que_so_diferem_pelo_id() -> None:
    linhas = [
        {"metodo": "GET", "rota": "/c/1", "total": 2, "media_ms": 100, "max_ms": 150, "erros_5xx": 0, "erros_4xx": 1},
        {"metodo": "GET", "rota": "/c/2", "total": 2, "media_ms": 300, "max_ms": 900, "erros_5xx": 1, "erros_4xx": 0},
        {"metodo": "POST", "rota": "/c/2", "total": 1, "media_ms": 10, "max_ms": 10},
    ]

    por_rota = {(r["metodo"], r["rota"]): r for r in agrupar_rotas(linhas)}

    r = por_rota[("GET", "/c/:id")]
    assert (r["total"], r["media_ms"], r["max_ms"], r["erros_5xx"], r["erros_4xx"]) == (4, 200, 900, 1, 1)
    assert ("POST", "/c/:id") in por_rota


def _sessao(codigo, agente, ip, *, ativa=False, dur_min=30, motivo="LOGOUT_VOLUNTARIO"):
    inicio = datetime(2026, 10, 6, 9)
    return {
        "codigo_usuario": codigo, "ip": ip, "user_agent": agente, "status": "ATIVA" if ativa else "FINALIZADA",
        "motivo": motivo, "criada_em": inicio, "encerrada_em": None if ativa else inicio + timedelta(minutes=dur_min),
        "ultima_atividade": inicio + timedelta(minutes=dur_min),
    }


def test_consolida_sessoes_do_periodo() -> None:
    r = consolidar_sessoes(
        [
            _sessao(1, CHROME, "10.0.0.1", dur_min=30),
            _sessao(1, CHROME, "10.0.0.1", dur_min=90, motivo="TIMEOUT_INATIVIDADE"),
            _sessao(2, FIREFOX, "10.0.0.2", ativa=True),
            _sessao(3, IPHONE, "10.0.0.1", dur_min=60),
        ]
    )

    assert (r["total"], r["usuarios_unicos"], r["ips_unicos"]) == (4, 3, 2)
    assert r["duracao_media_segundos"] == 60 * 60  # (30 + 90 + 60) / 3 min; a ativa não entra
    assert r["navegadores"][0] == {"nome": "Chrome", "total": 2, "percentual": 50.0}
    assert {m["nome"] for m in r["motivos"]} == {"LOGOUT_VOLUNTARIO", "TIMEOUT_INATIVIDADE", "Em andamento"}
    assert r["ips"][0] == {"ip": "10.0.0.1", "sessoes": 3, "usuarios": 2, "local": False}  # IP de 2 pessoas


def test_sem_sessoes_nao_quebra() -> None:
    r = consolidar_sessoes([])

    assert r["total"] == 0 and r["duracao_media_segundos"] is None and r["navegadores"] == []


def _comparativo(atual, anterior):
    from luftbase.observabilidade.insights import _variacao

    return {"atual": atual, "anterior": anterior, "variacao": {k: _variacao(atual[k], anterior[k]) for k in atual}}


def test_destaques_priorizam_erros_e_acessos_negados() -> None:
    comp = _comparativo(
        {"requisicoes": 300, "usuarios": 5, "erros_servidor": 6, "duracao_media_ms": 40},
        {"requisicoes": 100, "usuarios": 4, "erros_servidor": 2, "duracao_media_ms": 40},
    )
    mapa = montar_mapa_calor([(datetime(2026, 10, 6, 14), 50)])
    lentas = [{"metodo": "GET", "rota": "/relatorio", "total": 10, "media_ms": 2500, "max_ms": 4000}]
    erros = [{"rota": "/api/x", "erros_5xx": 4, "erros_4xx": 0}]
    sessoes = consolidar_sessoes([_sessao(1, CHROME, "10.0.0.1")])

    d = gerar_destaques(comparativo=comp, mapa=mapa, rotas_lentas=lentas, rotas_erro=erros, negados=3, sessoes=sessoes)

    titulos = [x["titulo"] for x in d]
    assert titulos[0] == "6 erro(s) no servidor" and d[0]["tom"] == "red" and "/api/x" in d[0]["texto"]
    assert "3 acesso(s) negado(s)" in titulos and "Rota lenta" in titulos and "Pico às 14h" in titulos
    assert any(t.startswith("Uso subiu 200%") for t in titulos) and "Chrome lidera" in titulos


def test_destaque_de_tranquilidade_quando_nada_chama_atencao() -> None:
    comp = _comparativo({"requisicoes": 0, "usuarios": 0, "erros_servidor": 0, "duracao_media_ms": 0},
                        {"requisicoes": 0, "usuarios": 0, "erros_servidor": 0, "duracao_media_ms": 0})

    d = gerar_destaques(comparativo=comp, mapa=montar_mapa_calor([]), rotas_lentas=[], rotas_erro=[], negados=0,
                        sessoes=consolidar_sessoes([]))

    assert [x["titulo"] for x in d] == ["Tudo tranquilo"]


# ---- consultas de verdade (SQLite com as tabelas usadas) ----------------------------------


def _banco():
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
    fim = datetime(2026, 10, 6, 18, 0)
    with engine.begin() as con:
        for comando in ddl:
            con.exec_driver_sql(comando)
        con.exec_driver_sql("INSERT INTO core.tb_sistema VALUES (0, 'Luft-Workspace'), (3, 'Luft-Integrador')")

        def log(sis, cod, login, rota, metodo, status, ms, quando, permitido=None, permissao=None):
            con.exec_driver_sql(
                "INSERT INTO core.tb_logs (id_sistema, codigo_usuario, login_usuario, rota_acessada, metodo_http,"
                " ip_origem, id_correlacao, duracao_ms, status_http, data_hora, acesso_permitido, permissao_exigida)"
                " VALUES (?, ?, ?, ?, ?, '10.0.0.1', 'c', ?, ?, ?, ?, ?)",
                (sis, cod, login, rota, metodo, ms, status, quando, permitido, permissao),
            )

        # período atual: 2 h antes do fim; período anterior: as 2 h anteriores a isso
        for i in range(6):
            log(0, 1, "ana", f"/clientes/{i}/testar", "GET", 200, 1000, fim - timedelta(minutes=10 + i))
        log(3, 2, "bia", "/api/x", "POST", 500, 50, fim - timedelta(minutes=30))
        log(3, 2, "bia", "/admin", "GET", 403, 5, fim - timedelta(minutes=40), permitido=False, permissao="X.Y.Z")
        log(0, 1, "ana", "/painel", "GET", 200, 20, fim - timedelta(hours=3))  # período anterior
        con.exec_driver_sql(
            "INSERT INTO core.tb_logevento (id_sistema, codigo_usuario, login_usuario, acao, recurso, descricao,"
            " severidade, data_hora) VALUES (0, 1, 'ana', 'EXCLUIR', 'usuario', 'Exclusão de usuário', 'ALTA', ?),"
            " (0, 1, 'ana', 'VER', 'tela', 'Visualização', 'BAIXA', ?)",
            (fim - timedelta(minutes=20), fim - timedelta(minutes=21)),
        )
        con.exec_driver_sql(
            "INSERT INTO core.tb_sessao (id_sessao, id_sistema, codigo_usuario, login_usuario, ip_origem, user_agent,"
            " status, criada_em, ultima_atividade, expira_em, encerrada_em, motivo_encerramento)"
            " VALUES ('s1', 0, 1, 'ana', '10.0.0.1', ?, 'FINALIZADA', ?, ?, ?, ?, 'LOGOUT_VOLUNTARIO')",
            (CHROME, fim - timedelta(minutes=90), fim - timedelta(minutes=30), fim, fim - timedelta(minutes=30)),
        )
    return BancoSQLAlchemy("core", engine), fim


def test_consulta_real_monta_todas_as_visoes() -> None:
    banco, fim = _banco()

    r = ServicoInsights(banco).obter(FiltroAuditoria(inicio=fim - timedelta(hours=2), fim=fim))

    assert r["comparativo"]["atual"]["requisicoes"] == 8 and r["comparativo"]["anterior"]["requisicoes"] == 1
    # 1 requisicao antes nao e base para comparar: nada de "subiu 700%"
    assert r["comparativo"]["base_suficiente"] is False and r["comparativo"]["variacao"]["requisicoes"] is None
    assert r["status"] == {"sucesso": 6, "redirecionamento": 0, "erro_cliente": 1, "erro_servidor": 1}
    assert r["mapa_calor"]["matriz"][1][17] + r["mapa_calor"]["matriz"][1][16] == 8  # terça-feira, 16h-17h
    lenta = r["rotas_lentas"][0]
    assert (lenta["rota"], lenta["total"], lenta["media_ms"]) == ("/clientes/:id/testar", 6, 1000)  # ids juntos
    assert r["rotas_com_erro"][0]["rota"] == "/api/x"
    assert r["negados"]["total"] == 1 and r["negados"]["itens"][0]["permissao"] == "X.Y.Z"
    assert r["negados"]["itens"][0]["sistema"] == "Luft-Integrador"
    assert [c["acao"] for c in r["criticos"]] == ["EXCLUIR"]  # só alta ou crítica
    assert r["usuarios_ativos"][0]["login"] == "ana" and r["usuarios_ativos"][0]["rotas"] == 6
    assert r["sessoes"]["total"] == 1 and r["sessoes"]["duracao_media_segundos"] == 60 * 60
    assert r["destaques"][0]["titulo"] == "1 erro(s) no servidor"


def test_consulta_real_respeita_o_filtro_de_sistema() -> None:
    banco, fim = _banco()

    r = ServicoInsights(banco).obter(FiltroAuditoria(inicio=fim - timedelta(hours=2), fim=fim, id_sistema=3))

    assert r["comparativo"]["atual"]["requisicoes"] == 2
    assert [u["login"] for u in r["usuarios_ativos"]] == ["bia"]
    assert r["criticos"] == []  # o evento crítico é do sistema 0
    assert r["sessoes"]["total"] == 0  # a sessão é de quem não usou o sistema 3


# ---- front-end: o JS só pode citar elementos que existem no modelo ---------------------------


def test_visoes_do_front_apontam_para_elementos_que_existem() -> None:
    import re
    from pathlib import Path

    from luftbase import servidor

    raiz = Path(servidor.__file__).resolve().parent / "interface"
    modelo = (raiz / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
    js = (raiz / "static" / "js" / "auditoria_visoes.js").read_text(encoding="utf-8")
    ao_vivo = (raiz / "static" / "js" / "auditoria_ao_vivo.js").read_text(encoding="utf-8")
    principal = (raiz / "static" / "js" / "auditoria.js").read_text(encoding="utf-8")

    ids_html = set(re.findall(r'id="([^"]+)"', modelo))
    ids_js = set(re.findall(r"\$\('([A-Za-z]+)'\)", js)) | set(re.findall(r"\$\('(audit[A-Za-z]+)'\)", ao_vivo))
    assert not (ids_js - ids_html), f"ids citados no JS e ausentes no modelo: {sorted(ids_js - ids_html)}"

    secoes = set(re.findall(r'data-visao="(\w+)"', modelo))
    paineis = set(re.findall(r'data-painel="(\w+)"', modelo))
    assert secoes == paineis == {"geral", "aovivo", "pessoas", "desempenho", "seguranca", "registros"}
    assert "data-insights-url" in modelo and "auditoria_visoes.js" in modelo
    # auditoria.js expõe os filtros e avisa quando atualizou (as novas seções dependem disso)
    assert "window.luftAuditoriaParametros" in principal and "luft:auditoria:atualizada" in principal
    assert "auditoriaPronta" in principal and "auditoriaPronta" in js
    # os ids antigos que auditoria.js usa continuam no modelo (a reorganização não os apagou)
    antigos = set(re.findall(r"\$\('(audit[A-Za-z]+)'\)", principal))
    assert not (antigos - ids_html), sorted(antigos - ids_html)


def test_rota_de_insights_esta_protegida() -> None:
    from luftbase.web import auditoria

    assert getattr(auditoria.api_insights, "__wrapped__", None) is not None


# ---- dados reais: visitantes, navegador desconhecido, sessão expirada, IP local, corte -------


def test_visitantes_e_sem_navegador_nao_distorcem_os_numeros() -> None:
    agora = datetime(2026, 10, 7, 12)
    visitante = _sessao(None, CHROME, "10.0.0.9", ativa=True)
    visitante["expira_em"] = agora + timedelta(hours=1)
    antiga = _sessao(1, "", "127.0.0.1", ativa=True)  # sessão de antes da captura do navegador
    antiga["expira_em"] = agora - timedelta(hours=2)  # ainda "ATIVA" no banco, mas já expirou
    viva = _sessao(2, CHROME, "10.0.0.5", ativa=True)
    viva["expira_em"] = agora + timedelta(hours=1)

    r = consolidar_sessoes([visitante, antiga, viva], agora=agora)

    assert r["total"] == 2 and r["usuarios_unicos"] == 2  # o visitante não é um login
    assert r["sem_navegador"] == 1
    assert [n["nome"] for n in r["navegadores"]] == ["Chrome"]  # "Desconhecido" fica fora do ranking
    assert r["navegadores"][0]["percentual"] == 100.0  # sobre quem tem navegador registrado
    assert {m["nome"] for m in r["motivos"]} == {"Expirou", "Em andamento"}
    locais = {i["ip"]: i["local"] for i in r["ips"]}
    assert locais == {"127.0.0.1": True, "10.0.0.5": False}


def test_destaque_nao_cita_navegador_quando_ninguem_tem_registro() -> None:
    sessoes = consolidar_sessoes([_sessao(1, "", "10.0.0.1")])
    comp = _comparativo({"requisicoes": 0, "usuarios": 0, "erros_servidor": 0, "duracao_media_ms": 0},
                        {"requisicoes": 0, "usuarios": 0, "erros_servidor": 0, "duracao_media_ms": 0})

    d = gerar_destaques(comparativo=comp, mapa=montar_mapa_calor([]), rotas_lentas=[], rotas_erro=[], negados=0,
                        sessoes=sessoes)

    assert [x["titulo"] for x in d] == ["Tudo tranquilo"]


def test_corte_de_dados_confiaveis_limita_periodo_e_comparativo() -> None:
    banco, fim = _banco()
    marco = fim - timedelta(minutes=35)  # só a bia (30 e 40 min atrás: a de 40 fica de fora) e a ana de 10-15 min

    r = ServicoInsights(banco).obter(FiltroAuditoria(inicio=marco, fim=fim), desde=marco)

    assert r["dados_a_partir_de"] == marco.isoformat()
    assert r["comparativo"]["atual"]["requisicoes"] == 7  # 6 da ana + 1 erro da bia; o negado (40 min) saiu
    assert r["comparativo"]["anterior"]["requisicoes"] == 0  # nada antes do marco entra na comparação
    assert r["negados"]["total"] == 0


def test_variavel_de_corte_aceita_data_valida_e_ignora_lixo(monkeypatch) -> None:
    from luftbase.web.auditoria import dados_confiaveis_desde

    monkeypatch.delenv("LUFT_AUDITORIA_DADOS_DESDE", raising=False)
    assert dados_confiaveis_desde() is None
    monkeypatch.setenv("LUFT_AUDITORIA_DADOS_DESDE", "2026-10-06T17:00")
    assert dados_confiaveis_desde() == datetime(2026, 10, 6, 17, 0)
    monkeypatch.setenv("LUFT_AUDITORIA_DADOS_DESDE", "ontem de tarde")
    assert dados_confiaveis_desde() is None  # valor inválido não derruba a tela


def test_variavel_de_corte_esta_na_tela_de_ambiente() -> None:
    from luftbase.infraestrutura.variaveis_ambiente import ErroVariavel, PERMITIDAS

    var = next(v for v in PERMITIDAS if v.chave == "LUFT_AUDITORIA_DADOS_DESDE")
    assert var.validar("") == "" and var.validar(" 2026-10-06T17:00 ") == "2026-10-06T17:00"
    try:
        var.validar("17h")
    except ErroVariavel:
        pass
    else:  # pragma: no cover
        raise AssertionError("aceitou data inválida")
