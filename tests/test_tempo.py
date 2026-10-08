"""Horario unico (Brasilia), igual em Windows e em Linux em UTC."""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.pool import StaticPool

from luftbase.identidade import armazenamento_postgresql as modulo
from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
from luftbase.infraestrutura.banco.conexoes import ConstrutorEngines
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco
from luftbase.nucleo import tempo
from luftbase.persistencia.core.sessoes import Sessao


def test_agora_local_e_brasilia_em_qualquer_maquina() -> None:
    # Brasilia esta 3 h atras do UTC (sem horario de verao). Comparar com o UTC torna o teste
    # valido num Windows em Brasilia e num Linux em UTC, onde o `datetime.now()` errava 3 h.
    diferenca = datetime.now(UTC).replace(tzinfo=None) - tempo.agora_local()

    assert abs(diferenca - timedelta(hours=3)) < timedelta(seconds=5)
    assert tempo.agora_local().tzinfo is None


def test_fuso_pode_ser_trocado_por_variavel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUFT_FUSO_HORARIO", "UTC")

    diferenca = datetime.now(UTC).replace(tzinfo=None) - tempo.agora_local()

    assert abs(diferenca) < timedelta(seconds=5)


def test_processo_e_levado_ao_fuso_da_plataforma(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[str] = []
    monkeypatch.setattr(time, "tzset", lambda: chamadas.append(os.environ["TZ"]), raising=False)
    monkeypatch.delenv("LUFT_FUSO_HORARIO", raising=False)
    monkeypatch.setenv("TZ", "UTC")

    tempo.aplicar_fuso_do_processo()

    assert os.environ["TZ"] == "America/Sao_Paulo"
    assert chamadas == ["America/Sao_Paulo"]


def test_sem_tzset_no_windows_nao_quebra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(time, "tzset", raising=False)

    tempo.aplicar_fuso_do_processo()  # no Windows o fuso e do sistema: so nao pode levantar erro


def test_aviso_quando_o_sistema_nao_tem_o_fuso(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(time, "tzset", lambda: None, raising=False)  # nao muda o fuso de fato
    monkeypatch.setattr(
        time, "localtime", lambda *a: time.struct_time((2026, 1, 1, 0, 0, 0, 0, 1, 0))
    )

    with caplog.at_level("WARNING", logger="luftbase.tempo"):
        tempo.aplicar_fuso_do_processo()

    assert "nao foi aplicado" in caplog.text


def test_sessoes_gravam_o_horario_de_brasilia_mesmo_com_o_servidor_em_utc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simula o Linux: o relogio da MAQUINA diz 17:55 (UTC) enquanto Brasilia e 14:55.
    fixo = datetime(2026, 10, 6, 14, 55, 0)
    monkeypatch.setattr(modulo, "agora_local", lambda: fixo)
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
            "dados": {"luftbase_usuario": {"id_usuario": 2280, "login": "widson.araujo"}},
        }
    ).encode("utf-8")

    armazenamento.salvar("luft:sessao:s1", carga, 600)

    with banco.leitura() as db:
        registro = db.execute(select(Sessao)).scalar_one()
        assert registro.ultima_atividade == fixo
        assert registro.criada_em == fixo
        assert registro.expira_em == fixo + timedelta(seconds=600)


def test_conexao_postgresql_fixa_o_fuso_da_sessao_do_banco() -> None:
    credencial = CredencialBanco(
        tipo=TipoBanco.POSTGRESQL,
        host="h",
        porta=5432,
        nome_banco="b",
        usuario="u",
        senha=Segredo("s"),
        esquema="x",
    )

    consulta = ConstrutorEngines().criar_url(credencial).query

    assert consulta["options"] == "-c timezone=America/Sao_Paulo"
    assert consulta["sslmode"] == "prefer"


def test_nao_sobrou_datetime_now_sem_fuso_nos_pontos_que_gravam() -> None:
    from pathlib import Path

    raiz = Path(tempo.__file__).resolve().parent.parent
    for relativo in (
        "identidade/armazenamento_postgresql.py",
        "observabilidade/buffer_temp.py",
        "integracoes/email/servico.py",
        "conteudo/repositorios.py",
    ):
        assert "datetime.now()" not in (raiz / relativo).read_text(encoding="utf-8"), relativo


def test_sem_tzset_nao_mexe_na_variavel_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    # No Windows, TZ="America/Sao_Paulo" e lido pelo runtime C como UTC e adianta os logs em 3 h.
    monkeypatch.delattr(time, "tzset", raising=False)
    monkeypatch.setenv("TZ", "valor-original")

    tempo.aplicar_fuso_do_processo()

    assert os.environ["TZ"] == "valor-original"


def test_formatador_de_log_usa_brasilia_e_nao_o_fuso_da_maquina() -> None:
    import logging

    registro = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
    registro.created = datetime(2026, 10, 8, 12, 20, 50, tzinfo=UTC).timestamp()

    formatador = tempo.FormatadorDeLog("%(asctime)s")

    assert formatador.format(registro).startswith("2026-10-08 09:20:50,")
    assert tempo.FormatadorDeLog("%(asctime)s", datefmt="%H:%M").format(registro) == "09:20"
