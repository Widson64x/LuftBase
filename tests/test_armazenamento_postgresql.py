"""Testes do adaptador de sessoes corporativas PostgreSQL."""

import json
from datetime import datetime

from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.persistencia.core.sessoes import EventoSessao, Sessao


def _preparar_armazenamento() -> tuple[ArmazenamentoSessoesPostgreSQL, BancoSQLAlchemy]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_core(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("ATTACH DATABASE ':memory:' AS core")
        cursor.close()

    with engine.begin() as conexao:
        conexao.exec_driver_sql("""
            CREATE TABLE core.tb_sessao (
                id_sessao VARCHAR(128) PRIMARY KEY,
                id_sistema INTEGER,
                codigo_usuario INTEGER,
                login_usuario VARCHAR(100),
                ip_origem VARCHAR(50),
                user_agent VARCHAR(500),
                dados_sessao TEXT,
                status VARCHAR(20) DEFAULT 'ATIVA' NOT NULL,
                total_renovacoes INTEGER DEFAULT 0 NOT NULL,
                criada_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                ultima_atividade TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                expira_em TIMESTAMP NOT NULL,
                encerrada_em TIMESTAMP,
                motivo_encerramento VARCHAR(100)
            );
        """)
        conexao.exec_driver_sql("""
            CREATE TABLE core.tb_sessao_evento (
                id_evento_sessao INTEGER PRIMARY KEY AUTOINCREMENT,
                id_sessao VARCHAR(128) NOT NULL,
                id_sistema INTEGER,
                codigo_usuario INTEGER,
                login_usuario VARCHAR(100),
                tipo_evento VARCHAR(30) NOT NULL,
                ip_origem VARCHAR(50),
                user_agent VARCHAR(500),
                data_hora TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                detalhes TEXT
            );
        """)

    banco = BancoSQLAlchemy("core", engine)
    return ArmazenamentoSessoesPostgreSQL(banco), banco


def test_ignora_chaves_fora_do_padrao_sessao() -> None:
    armazenamento, banco = _preparar_armazenamento()

    # Chaves de cache de autorizacao ou sinais nao devem ser salvas nem lidas
    armazenamento.salvar("luft:autorizacao:revisao", b"1", 60)
    armazenamento.salvar("luft:autorizacao:resultado:0:2280:abc", b"{}", 60)
    armazenamento.salvar("luft:conteudo:sinal", b"{}", 60)

    assert armazenamento.obter("luft:autorizacao:revisao") is None
    assert armazenamento.obter("luft:autorizacao:resultado:0:2280:abc") is None

    with banco.leitura() as db:
        qtd_sessoes = db.scalar(select(Sessao))
        qtd_eventos = db.scalar(select(EventoSessao))

    assert qtd_sessoes is None
    assert qtd_eventos is None


def test_sessao_anonima_nao_gera_evento_inicio_nem_aparece_em_online() -> None:
    armazenamento, banco = _preparar_armazenamento()

    payload_anonimo = json.dumps(
        {
            "versao": 1,
            "salva_em": datetime.now().isoformat(),
            "dados": {"_fresh": True, "luftbase_csrf": "token123"},
        }
    ).encode("utf-8")

    armazenamento.salvar("luft:sessao:token_anonimo", payload_anonimo, 600)

    # Verifica que salvou os dados da sessao para o CSRF funcionar
    assert armazenamento.obter("luft:sessao:token_anonimo") == payload_anonimo

    with banco.leitura() as db:
        sessao = db.execute(select(Sessao).where(Sessao.id_sessao == "token_anonimo")).scalar_one()
        assert sessao.codigo_usuario is None
        assert sessao.status == "ATIVA"

        # Nenhum evento de INICIO para sessao anonima
        eventos = db.execute(select(EventoSessao)).scalars().all()
        assert len(eventos) == 0

    # Nao deve constar na lista de usuarios online
    assert len(armazenamento.listar_usuarios_online()) == 0
    assert armazenamento.contar_online() == 0


def test_login_autenticado_gera_evento_inicio_e_aparece_online() -> None:
    armazenamento, banco = _preparar_armazenamento()

    payload_autenticado = json.dumps(
        {
            "versao": 1,
            "salva_em": datetime.now().isoformat(),
            "dados": {
                "_user_id": "2280",
                "luftbase_usuario": {
                    "id_usuario": 2280,
                    "login": "widson.araujo",
                },
            },
        }
    ).encode("utf-8")

    armazenamento.salvar("luft:sessao:sessao_widson", payload_autenticado, 600)

    # Deve gerar evento de INICIO
    with banco.leitura() as db:
        eventos = db.execute(select(EventoSessao)).scalars().all()
        assert len(eventos) == 1
        assert eventos[0].tipo_evento == "INICIO"
        assert eventos[0].codigo_usuario == 2280
        assert eventos[0].login_usuario == "widson.araujo"

    # Deve aparecer como online
    online = armazenamento.listar_usuarios_online()
    assert len(online) == 1
    assert online[0]["codigo_usuario"] == 2280
    assert online[0]["login_usuario"] == "widson.araujo"
    assert armazenamento.contar_online() == 1


def test_rotacao_sessao_anonima_nao_gera_logout_em_evento() -> None:
    armazenamento, banco = _preparar_armazenamento()

    payload_anonimo = json.dumps(
        {
            "versao": 1,
            "dados": {"_fresh": True},
        }
    ).encode("utf-8")

    armazenamento.salvar("luft:sessao:anonimo_pre_login", payload_anonimo, 600)
    armazenamento.remover("luft:sessao:anonimo_pre_login")

    with banco.leitura() as db:
        sessao = db.execute(
            select(Sessao).where(Sessao.id_sessao == "anonimo_pre_login")
        ).scalar_one()
        assert sessao.status == "FINALIZADA"
        assert sessao.motivo_encerramento == "ROTACAO_SESSAO"

        # Nenhum evento gravado no historico
        eventos = db.execute(select(EventoSessao)).scalars().all()
        assert len(eventos) == 0


def _payload_usuario(codigo: int = 3049, login: str = "teste.ti") -> bytes:
    return json.dumps(
        {
            "versao": 1,
            "salva_em": datetime.now().isoformat(),
            "dados": {
                "_user_id": str(codigo),
                "luftbase_usuario": {"id_usuario": codigo, "login": login},
            },
        }
    ).encode("utf-8")


def test_gravacao_tardia_nao_ressuscita_sessao_encerrada_no_logout() -> None:
    # Uma requisicao em segundo plano (outra aba) termina DEPOIS do logout e regrava a mesma
    # sessao. Isso nao pode reativar a sessao nem devolver o usuario ao estado online.
    armazenamento, banco = _preparar_armazenamento()
    armazenamento.salvar("luft:sessao:s1", _payload_usuario(), 600)
    assert armazenamento.contar_online() == 1

    armazenamento.remover("luft:sessao:s1")
    assert armazenamento.contar_online() == 0

    armazenamento.salvar("luft:sessao:s1", _payload_usuario(), 600)  # gravacao tardia

    with banco.leitura() as db:
        registro = db.execute(select(Sessao).where(Sessao.id_sessao == "s1")).scalar_one()
        assert registro.status == "FINALIZADA"
        assert registro.motivo_encerramento == "LOGOUT_VOLUNTARIO"
    assert armazenamento.contar_online() == 0
    assert armazenamento.listar_usuarios_online() == []


def test_sessao_nova_depois_do_logout_volta_a_ficar_online() -> None:
    # O login seguinte rotaciona o id: sessao nova, sem registro anterior. Continua funcionando.
    armazenamento, _ = _preparar_armazenamento()
    armazenamento.salvar("luft:sessao:s1", _payload_usuario(), 600)
    armazenamento.remover("luft:sessao:s1")

    armazenamento.salvar("luft:sessao:s2", _payload_usuario(), 600)

    assert armazenamento.contar_online() == 1
    assert armazenamento.listar_usuarios_online()[0]["id_sessao"] == "s2"


def test_renovacao_normal_de_sessao_ativa_continua_funcionando() -> None:
    armazenamento, banco = _preparar_armazenamento()
    armazenamento.salvar("luft:sessao:s1", _payload_usuario(), 600)

    armazenamento.salvar("luft:sessao:s1", _payload_usuario(), 600)

    with banco.leitura() as db:
        registro = db.execute(select(Sessao).where(Sessao.id_sessao == "s1")).scalar_one()
        assert registro.status == "ATIVA" and registro.total_renovacoes == 1


def test_presenca_so_vale_para_sessao_ativa_e_exige_o_id_da_sessao() -> None:
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from sqlalchemy.dialects import postgresql

    from luftbase.identidade.repositorio_core import RepositorioUsuariosPostgreSQL

    executados: list[object] = []
    sessao = MagicMock()
    sessao.execute.side_effect = executados.append

    @contextmanager
    def unidade():  # type: ignore[no-untyped-def]
        yield sessao

    banco = MagicMock()
    banco.unidade_trabalho = unidade
    repo = RepositorioUsuariosPostgreSQL(banco)

    repo.atualizar_presenca(3049, id_sessao=None)
    assert executados == []  # sem o id da sessao nao ha como validar: nao toca no usuario

    repo.atualizar_presenca(3049, id_sessao="s1")
    sql = str(executados[0].compile(dialect=postgresql.dialect()))  # type: ignore[attr-defined]
    assert "EXISTS" in sql and "tb_sessao" in sql and "status" in sql


def test_id_da_sessao_atual_vem_do_objeto_da_sessao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    from luftbase.identidade.sessoes import SessaoServidor
    from luftbase.interface import web

    # O id nunca esteve no dicionario da sessao: ler session["_id"] devolvia sempre vazio.
    sessao_real = SessaoServidor({"qualquer": "coisa"}, identificador="abc123", nova=False)
    monkeypatch.setattr(web, "session", SimpleNamespace(_get_current_object=lambda: sessao_real))

    assert sessao_real.get("_id") is None
    assert web.id_sessao_atual() == "abc123"
