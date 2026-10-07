"""Controle administrativo de sessões: encerrar uma, desconectar uma pessoa ou todas."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.tempo import agora_local
from luftbase.observabilidade.controle_sessoes import ServicoControleSessoes, referencia
from luftbase.persistencia.core import EventoSessao, Log, Sessao, Sistema, Usuario


def _banco():
    """SQLite com as tabelas reais do core (so os nomes das colunas: sem tipos nem defaults do PostgreSQL)."""

    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def anexar(dbapi_connection, _registro):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS core")
        cursor.close()

    agora = agora_local()
    with engine.begin() as con:
        for modelo in (Sistema, Usuario, Sessao, EventoSessao, Log):
            colunas = ", ".join(
                f"{c.name} INTEGER PRIMARY KEY AUTOINCREMENT" if c.primary_key and "INT" in str(c.type).upper() and c.name.startswith("id_") and c.name not in ("id_sistema",) and modelo in (EventoSessao, Log)
                else c.name
                for c in modelo.__table__.columns
            )
            con.exec_driver_sql(f"CREATE TABLE {modelo.__table__.fullname} ({colunas})")
        con.exec_driver_sql("INSERT INTO core.tb_sistema (id_sistema, nome_sistema) VALUES (0, 'Workspace'), (3, 'Integrador')")
        con.exec_driver_sql(
            "INSERT INTO core.tb_usuario (codigo_usuario, login_usuario, nome_usuario, status_online, id_sessao_atual,"
            " total_logins) VALUES (1, 'ana', 'Ana', 1, 's_a1', 2), (2, 'bia', 'Bia', 1, 's_b1', 1)"
        )
        linhas = [
            # id, sistema, usuario, login, status, expira
            ("s_a1", 0, 1, "ana", "ATIVA", agora + timedelta(hours=1)),
            ("s_a2", 0, 1, "ana", "ATIVA", agora + timedelta(hours=1)),
            ("s_b1", 3, 2, "bia", "ATIVA", agora + timedelta(hours=1)),
            ("s_b_velha", 3, 2, "bia", "ATIVA", agora - timedelta(hours=1)),  # ja expirou
            ("s_visitante", 0, None, None, "ATIVA", agora + timedelta(hours=1)),
            ("s_fim", 0, 1, "ana", "FINALIZADA", agora + timedelta(hours=1)),
        ]
        for id_sessao, sis, cod, login, status, expira in linhas:
            con.exec_driver_sql(
                "INSERT INTO core.tb_sessao (id_sessao, id_sistema, codigo_usuario, login_usuario, ip_origem, status,"
                " total_renovacoes, dados_sessao, criada_em, ultima_atividade, expira_em)"
                " VALUES (?, ?, ?, ?, '10.0.0.1', ?, 0, '{}', ?, ?, ?)",
                (id_sessao, sis, cod, login, status, agora - timedelta(hours=1), agora, expira),
            )
    return BancoSQLAlchemy("core", engine)


def _servico():
    banco = _banco()
    return ServicoControleSessoes(banco, ArmazenamentoSessoesPostgreSQL(banco)), banco


def _status(banco) -> dict[str, tuple[str, str | None]]:
    with banco.leitura() as db:
        return {s.id_sessao: (s.status, s.motivo_encerramento) for s in db.execute(select(Sessao)).scalars()}


def test_referencia_e_estavel_curta_e_nao_revela_o_id() -> None:
    assert referencia("s_a1") == referencia("s_a1") and len(referencia("s_a1")) == 20
    assert "s_a1" not in referencia("s_a1") and referencia("s_a1") != referencia("s_a2")


def test_encerra_uma_sessao_de_verdade() -> None:
    servico, banco = _servico()

    r = servico.encerrar_sessao(referencia("s_a2"), id_sistema=None, id_sessao_atual="s_a1")

    assert (r.encerradas, r.login, r.motivo_recusa) == (1, "ana", None)
    estado = _status(banco)
    assert estado["s_a2"] == ("REVOGADA", "REVOGADA_ADMIN") and estado["s_a1"][0] == "ATIVA"  # só a escolhida
    with banco.leitura() as db:
        evento = db.execute(select(EventoSessao).where(EventoSessao.id_sessao == "s_a2")).scalar_one()
    assert evento.tipo_evento == "REVOGACAO"


def test_nao_encerra_a_propria_sessao() -> None:
    servico, banco = _servico()

    r = servico.encerrar_sessao(referencia("s_a1"), id_sistema=None, id_sessao_atual="s_a1")

    assert r.encerradas == 0 and r.motivo_recusa == "propria"
    assert _status(banco)["s_a1"][0] == "ATIVA"


@pytest.mark.parametrize("sessao", ["s_b_velha", "s_visitante", "s_fim", "inexistente"])
def test_so_encerra_sessao_ativa_de_pessoa_logada(sessao: str) -> None:
    servico, banco = _servico()
    antes = _status(banco)

    r = servico.encerrar_sessao(referencia(sessao), id_sistema=None, id_sessao_atual="outra")

    assert r.motivo_recusa == "nao_encontrada" and r.encerradas == 0
    assert _status(banco) == antes


def test_desconectar_pessoa_encerra_todas_as_dela_menos_a_sua() -> None:
    servico, banco = _servico()

    r = servico.encerrar_pessoa(1, id_sistema=None, id_sessao_atual="s_a1")  # a Ana desconectando a si mesma

    assert (r.encerradas, r.login) == (1, "ana")
    assert _status(banco)["s_a1"][0] == "ATIVA" and _status(banco)["s_a2"][0] == "REVOGADA"

    so_a_propria = servico.encerrar_pessoa(1, id_sistema=None, id_sessao_atual="s_a1")
    assert so_a_propria.motivo_recusa == "propria"


def test_desconectar_pessoa_marca_offline_quando_nao_resta_sessao() -> None:
    servico, banco = _servico()

    r = servico.encerrar_pessoa(2, id_sistema=None, id_sessao_atual="s_a1")

    assert r.encerradas == 1  # a s_b_velha ja tinha expirado e nao conta
    with banco.leitura() as db:
        bia = db.get(Usuario, 2)
        assert bia.status_online is False or bia.status_online == 0


def test_desconectar_todos_poupa_a_sessao_do_administrador() -> None:
    servico, banco = _servico()

    r = servico.encerrar_todas(id_sistema=None, id_sessao_atual="s_a1")

    assert (r.encerradas, r.pessoas) == (2, 2)  # s_a2 e s_b1
    estado = _status(banco)
    assert estado["s_a1"][0] == "ATIVA" and estado["s_a2"][0] == "REVOGADA" and estado["s_b1"][0] == "REVOGADA"
    assert estado["s_visitante"][0] == "ATIVA" and estado["s_b_velha"][0] == "ATIVA"  # fora do alcance: intactas


def test_no_escopo_de_um_sistema_so_alcanca_quem_o_usa() -> None:
    servico, banco = _servico()
    agora = agora_local()
    with banco.unidade_trabalho() as db:
        # A Ana entrou pelo Workspace (0), mas nos ultimos minutos esta no Integrador (3).
        db.connection().exec_driver_sql(
            "INSERT INTO core.tb_logs (id_sistema, codigo_usuario, login_usuario, data_hora) VALUES (3, 1, 'ana', ?)",
            (agora - timedelta(minutes=2),),
        )

    r = servico.encerrar_todas(id_sistema=3, id_sessao_atual="outra")

    assert r.pessoas == 2 and r.encerradas == 3  # s_a1 e s_a2 (Ana usa o 3) e s_b1 (Bia entrou pelo 3)


def test_escopo_de_um_sistema_nao_alcanca_quem_nao_o_usa() -> None:
    servico, banco = _servico()

    r = servico.encerrar_todas(id_sistema=3, id_sessao_atual="outra")

    assert r.pessoas == 1 and _status(banco)["s_a1"][0] == "ATIVA"  # a Ana nunca usou o sistema 3


# ---- HTTP: mensagens, auditoria e proteção ---------------------------------------------------


def test_resposta_http_traduz_resultados_e_audita(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase.observabilidade.controle_sessoes import ResultadoEncerramento
    from luftbase.web import auditoria

    auditados: list[dict] = []
    monkeypatch.setattr(auditoria, "registrar_alteracao_auditoria", lambda **dados: auditados.append(dados))

    with Flask("t").app_context():
        ok, = (auditoria._resposta_controle(ResultadoEncerramento(2, 1, "ana"), "feito", acao="DESCONECTAR_PESSOA", recurso_id="1", descricao="d"),)
        propria = auditoria._resposta_controle(ResultadoEncerramento(0, login="ana", motivo_recusa="propria"), "x", acao="A", recurso_id="1", descricao="d")
        nada = auditoria._resposta_controle(ResultadoEncerramento(0, motivo_recusa="nao_encontrada"), "x", acao="A", recurso_id="1", descricao="d")

    assert ok.get_json()["data"] == {"encerradas": 2, "pessoas": 1, "propria": False} and ok.status_code == 200
    assert propria[1] == 409 and "Sair" in propria[0].get_json()["message"]
    assert nada[1] == 404
    assert len(auditados) == 1 and auditados[0]["acao"] == "DESCONECTAR_PESSOA"  # só o que de fato aconteceu


@pytest.mark.parametrize("nome", ["api_revogar_sessao", "api_revogar_pessoa", "api_revogar_todas"])
def test_rotas_de_controle_exigem_login_e_permissao(nome: str) -> None:
    from luftbase.web import auditoria

    assert getattr(getattr(auditoria, nome), "__wrapped__", None) is not None


def test_pedidos_invalidos_sao_recusados() -> None:
    from werkzeug.exceptions import HTTPException

    from luftbase.web import auditoria

    corpo_ruim = [
        (auditoria.api_revogar_sessao, {"ref": "../etc/passwd"}),
        (auditoria.api_revogar_pessoa, {"codigo_usuario": "abc"}),
        (auditoria.api_revogar_todas, {"confirmacao": "talvez"}),
    ]
    app = Flask("t")
    app.config["SECRET_KEY"] = "x"
    for view, corpo in corpo_ruim:
        funcao = view
        while hasattr(funcao, "__wrapped__"):
            funcao = funcao.__wrapped__
        with app.test_request_context("/", method="POST", json=corpo):
            from unittest.mock import patch

            with patch.object(auditoria, "validar_csrf_requisicao", lambda: None), pytest.raises(HTTPException) as erro:
                funcao()
        assert erro.value.code == 400, view.__name__


def test_lista_de_sessoes_traz_referencia_e_nao_o_id() -> None:
    from luftbase.observabilidade.analise import FiltroAuditoria, PaginaAuditoria
    from luftbase.observabilidade.insights import ServicoInsights

    _servico_, banco = _servico()
    agora = agora_local()

    r = ServicoInsights(banco).listar_sessoes(
        FiltroAuditoria(inicio=agora - timedelta(days=1), fim=agora + timedelta(minutes=1)),
        PaginaAuditoria(1, 50),
        id_sessao_atual="s_a1",
    )

    por_ref = {i["ref"]: i for i in r["itens"]}
    assert referencia("s_a1") in por_ref and "id" not in r["itens"][0]
    assert por_ref[referencia("s_a1")]["atual"] is True and por_ref[referencia("s_a2")]["atual"] is False
    assert por_ref[referencia("s_a2")]["ativa"] is True and por_ref[referencia("s_fim")]["ativa"] is False
    assert por_ref[referencia("s_b_velha")]["ativa"] is False  # expirada: sem botão de encerrar
    assert "s_a1" not in str(r)  # o identificador real nunca sai do servidor
    assert SimpleNamespace  # (import usado apenas para manter o módulo enxuto)


def test_front_do_controle_esta_ligado_ao_modelo() -> None:
    import re
    from pathlib import Path

    from luftbase import servidor

    raiz = Path(servidor.__file__).resolve().parent / "interface"
    modelo = (raiz / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
    controle = (raiz / "static" / "js" / "auditoria_controle.js").read_text(encoding="utf-8")
    ao_vivo = (raiz / "static" / "js" / "auditoria_ao_vivo.js").read_text(encoding="utf-8")
    principal = (raiz / "static" / "js" / "auditoria.js").read_text(encoding="utf-8")

    ids = set(re.findall(r'id="([^"]+)"', modelo))
    citados = set(re.findall(r"\$\('([A-Za-z]+)'\)", controle)) | {"auditLiveDesconectarTodos"}
    assert not (citados - ids), sorted(citados - ids)
    for atributo in ("data-revogar-sessao-url", "data-revogar-pessoa-url", "data-revogar-todas-url"):
        assert atributo in modelo, atributo
    assert modelo.index("auditoria_controle.js") < modelo.index("auditoria.js")
    # a pessoa só aparece com botão se o servidor disse que o usuário pode revogar, e nunca para si mesmo
    assert "estado.podeRevogar && !p.voce" in ao_vivo and "podeRevogar && item.ativa" in principal
    assert "sua sessão" in principal  # a sessão atual não tem botão de encerrar
    # a ação sempre pede confirmação; "desconectar todos" exige digitar
    assert "digitar: 'DESCONECTAR'" in controle and "dialogo.showModal()" in controle
    assert "X-CSRF-Token" in controle


def test_so_a_propria_sessao_ativa_tem_mensagem_clara() -> None:
    servico, banco = _servico()
    with banco.unidade_trabalho() as db:  # deixa so a sessao s_a1 ativa
        db.connection().exec_driver_sql("UPDATE core.tb_sessao SET status = 'FINALIZADA' WHERE id_sessao <> 's_a1'")

    r = servico.encerrar_todas(id_sistema=None, id_sessao_atual="s_a1")

    assert r.encerradas == 0 and r.motivo_recusa == "so_a_propria"
    assert _status(banco)["s_a1"][0] == "ATIVA"


def test_desconectar_todos_pode_incluir_a_propria_sessao_se_pedido() -> None:
    servico, banco = _servico()

    r = servico.encerrar_todas(id_sistema=None, id_sessao_atual="s_a1", incluir_propria=True)

    assert (r.encerradas, r.pessoas, r.propria_encerrada) == (3, 2, True)  # s_a1, s_a2 e s_b1
    assert all(_status(banco)[i][0] == "REVOGADA" for i in ("s_a1", "s_a2", "s_b1"))
    with banco.leitura() as db:
        ordem = [e.id_sessao for e in db.execute(select(EventoSessao).order_by(EventoSessao.id_evento_sessao)).scalars()]
    assert ordem[-1] == "s_a1"  # a sua cai por ultimo


def test_so_a_propria_vira_409_com_a_dica_da_opcao(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase.observabilidade.controle_sessoes import ResultadoEncerramento
    from luftbase.web import auditoria

    monkeypatch.setattr(auditoria, "registrar_alteracao_auditoria", lambda **_: None)
    with Flask("t").app_context():
        resposta, codigo = auditoria._resposta_controle(
            ResultadoEncerramento(0, motivo_recusa="so_a_propria"), "x", acao="A", recurso_id="1", descricao="d"
        )
        ok = auditoria._resposta_controle(
            ResultadoEncerramento(3, 2, propria_encerrada=True), "x", acao="A", recurso_id="1", descricao="d"
        )

    assert codigo == 409 and "Incluir a minha sessão" in resposta.get_json()["message"]
    assert ok.get_json()["data"]["propria"] is True
