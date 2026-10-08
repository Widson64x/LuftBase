"""Retencao: o que vence, a trilha que fica, o arquivo antes de apagar e o modo simular."""

from __future__ import annotations

import csv
import gzip
import importlib
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from core_sqlite import motor_sqlite
from flask import Flask
from sqlalchemy import func, select

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.observabilidade import retencao
from luftbase.observabilidade.retencao import Politica, executar, simular
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.alertas import Alerta
from luftbase.persistencia.core.auditoria import Log, LogDetalhe, LogEvento
from luftbase.persistencia.core.sessoes import Sessao

# `luftbase.cli.banco` e o modulo e, no pacote, tambem o grupo exportado.
cli_banco = importlib.import_module("luftbase.cli.banco")

AGORA = datetime(2026, 10, 8, 12, 0, 0)
POLITICA = Politica(acesso_dias=180, sessoes_dias=365, eventos_dias=730, alertas_dias=180)


def _dias(n: int) -> datetime:
    return AGORA - timedelta(days=n)


class Bancos:
    def __init__(self) -> None:
        self.core = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))


def _log(s: Any, id_log: int, quando: datetime) -> None:
    s.add(
        Log(
            id_log=id_log,
            id_sistema=2,
            login_usuario="ana",
            rota_acessada="/x",
            metodo_http="GET",
            id_correlacao=f"c{id_log}",
            duracao_ms=10,
            status_http=200,
            data_hora=quando,
        )
    )


@pytest.fixture
def bancos() -> Bancos:
    b = Bancos()
    with b.core.unidade_trabalho() as s:
        _log(s, 1, _dias(400))  # acesso vencido, com evento antigo demais
        _log(s, 2, _dias(200))  # acesso vencido, com evento ainda no prazo
        _log(s, 3, _dias(10))  # recente
        s.flush()
        s.add(
            LogEvento(
                id_logevento=10, id_sistema=2, id_log=1, acao="A", recurso="R",
                descricao="x", severidade="BAIXA", data_hora=_dias(800),
            )
        )
        s.add(
            LogEvento(
                id_logevento=11, id_sistema=2, id_log=2, acao="A", recurso="R",
                descricao="trilha que deve ficar", severidade="ALTA", data_hora=_dias(200),
            )
        )
        s.flush()
        s.add(
            LogDetalhe(
                id_logdetalhe=1, id_log=2, id_logevento=11, tipo_alteracao="ALTERACAO",
                dados_novos_json="{}", data_hora=_dias(200),
            )
        )
        for sid, status, fim in (
            ("antiga", "REVOGADA", _dias(500)),
            ("recente", "REVOGADA", _dias(5)),
            ("ativa-velha", "ATIVA", None),
        ):
            s.add(
                Sessao(
                    id_sessao=sid, id_sistema=2, codigo_usuario=1, login_usuario="ana",
                    status=status, criada_em=_dias(600), ultima_atividade=_dias(600),
                    expira_em=_dias(599), encerrada_em=fim,
                )
            )
        for chave, status, resolvido in (
            ("velho", "RESOLVIDO", _dias(300)),
            ("novo", "RESOLVIDO", _dias(3)),
            ("aberto", "ABERTO", None),
        ):
            s.add(
                Alerta(
                    chave=chave, regra="ERRO_5XX", status=status, ocorrencias=1,
                    primeira_ocorrencia=_dias(300), ultima_ocorrencia=_dias(300),
                    resolvido_em=resolvido,
                )
            )
    return b


def _contar(bancos: Bancos, modelo: Any) -> int:
    with bancos.core.leitura() as s:
        return int(s.execute(select(func.count()).select_from(modelo)).scalar_one())


def test_simular_conta_o_que_venceria_sem_apagar(bancos: Bancos) -> None:
    with bancos.core.leitura() as s:
        itens = {i.tabela: i.vencidas for i in simular(s, POLITICA, AGORA)}

    assert itens == {"tb_logs": 2, "tb_logevento": 1, "tb_sessao": 1, "tb_alerta": 1}
    assert _contar(bancos, Log) == 3 and _contar(bancos, Sessao) == 3


def test_executar_apaga_so_o_vencido_e_preserva_a_trilha(bancos: Bancos) -> None:
    r = executar(bancos, POLITICA, agora=AGORA)  # type: ignore[arg-type]

    assert not r.erros
    assert _contar(bancos, Log) == 1  # so o recente
    with bancos.core.leitura() as s:
        eventos = {e.id_logevento: e.id_log for e in s.execute(select(LogEvento)).scalars()}
        detalhe_log = s.execute(select(LogDetalhe.id_log)).scalar_one()
        sessoes = set(s.execute(select(Sessao.id_sessao)).scalars())
        alertas = set(s.execute(select(Alerta.chave)).scalars())
    # evento de 800 dias vence; o de 200 dias fica, so que solto do acesso apagado
    assert eventos == {11: None}
    assert detalhe_log is None
    assert sessoes == {"recente", "ativa-velha"}  # sessao ATIVA nunca e apagada
    assert alertas == {"novo", "aberto"}  # so resolvidos antigos saem
    desligadas = next(t for t in r.tabelas if t.tabela == "tb_logs").desligadas
    assert desligadas == 2  # o evento 11 e o detalhe 1


def test_arquivo_csv_gz_guarda_o_que_foi_apagado(bancos: Bancos, tmp_path: Path) -> None:
    r = executar(bancos, POLITICA, agora=AGORA, pasta_arquivo=tmp_path)  # type: ignore[arg-type]

    arquivos = sorted(p.name for p in tmp_path.iterdir())
    assert any(a.startswith("tb_logs-20261008-120000") for a in arquivos)
    with gzip.open(tmp_path / next(a for a in arquivos if a.startswith("tb_logs")), "rt") as f:
        linhas = list(csv.reader(f))
    assert linhas[0][0] == "id_log" and {linha[0] for linha in linhas[1:]} == {"1", "2"}
    assert next(t for t in r.tabelas if t.tabela == "tb_logs").arquivadas == 2


def test_se_o_arquivo_falhar_nada_e_apagado(
    bancos: Bancos, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falha(self: Any, *_a: Any, **_k: Any) -> int:
        raise OSError("disco cheio")

    monkeypatch.setattr(retencao._Arquivador, "gravar", falha)  # noqa: SLF001

    r = executar(bancos, POLITICA, agora=AGORA, pasta_arquivo=tmp_path)  # type: ignore[arg-type]

    assert r.erros and "disco cheio" in r.erros[0]
    assert _contar(bancos, Log) == 3 and _contar(bancos, Sessao) == 3
    assert _contar(bancos, Alerta) == 3


def test_apaga_em_lotes_pequenos(bancos: Bancos) -> None:
    r = executar(bancos, POLITICA, agora=AGORA, tamanho_lote=1)  # type: ignore[arg-type]

    assert next(t for t in r.tabelas if t.tabela == "tb_logs").apagadas == 2
    assert _contar(bancos, Log) == 1


def test_segunda_execucao_nao_tem_mais_nada_a_fazer(bancos: Bancos) -> None:
    executar(bancos, POLITICA, agora=AGORA)  # type: ignore[arg-type]

    r = executar(bancos, POLITICA, agora=AGORA)  # type: ignore[arg-type]

    assert r.total_apagadas == 0


def test_politica_le_o_ambiente_e_tolera_lixo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LUFT_RETENCAO_ACESSO_DIAS", "30")
    monkeypatch.setenv("LUFT_RETENCAO_EVENTOS_DIAS", "abc")
    monkeypatch.setenv("LUFT_RETENCAO_SESSOES_DIAS", "0")

    p = Politica.de_ambiente()

    assert (p.acesso_dias, p.eventos_dias, p.sessoes_dias, p.alertas_dias) == (30, 730, 1, 180)


def test_tamanho_e_mais_antigo(bancos: Bancos) -> None:
    with bancos.core.leitura() as s:
        tamanhos = {t["tabela"]: t["linhas"] for t in retencao.tamanho_tabelas(s)}
        antigos = retencao.mais_antigo(s)

    assert tamanhos["tb_logs"] == 3 and tamanhos["tb_alerta"] == 3
    assert antigos["tb_logs"] == _dias(400)


def _cli(monkeypatch: pytest.MonkeyPatch, bancos: Bancos, args: list[str]) -> Any:
    estado = SimpleNamespace(
        bancos=bancos, auditoria=SimpleNamespace(registrar_evento=lambda *_a, **_k: None)
    )
    monkeypatch.setattr(cli_banco, "obter_luftbase", lambda: estado)
    app = Flask(__name__)
    app.cli.add_command(cli_banco.banco)
    return app.test_cli_runner().invoke(args=["banco", *args])


def test_cli_padrao_e_simular(monkeypatch: pytest.MonkeyPatch, bancos: Bancos) -> None:
    saida = _cli(monkeypatch, bancos, ["retencao"])

    assert saida.exit_code == 0, saida.output
    assert "modo=simular" in saida.output and "tb_logs: vencidas=" in saida.output
    assert _contar(bancos, Log) >= 3  # nada apagado (os dados de teste sao de 2026-10-08, ha dias)


def test_cli_executar_exige_destino_do_arquivo(
    monkeypatch: pytest.MonkeyPatch, bancos: Bancos
) -> None:
    saida = _cli(monkeypatch, bancos, ["retencao", "--executar"])

    assert saida.exit_code != 0
    assert "--arquivar-em" in saida.output


def test_cli_executar_arquiva_e_apaga(
    monkeypatch: pytest.MonkeyPatch, bancos: Bancos, tmp_path: Path
) -> None:
    monkeypatch.setattr(retencao, "agora_local", lambda: AGORA)

    saida = _cli(monkeypatch, bancos, ["retencao", "--executar", "--arquivar-em", str(tmp_path)])

    assert saida.exit_code == 0, saida.output
    assert "tb_logs: apagadas=2" in saida.output
    assert any(p.name.startswith("tb_logs-") for p in tmp_path.iterdir())


def test_cli_tamanho_logs(monkeypatch: pytest.MonkeyPatch, bancos: Bancos) -> None:
    saida = _cli(monkeypatch, bancos, ["tamanho-logs"])

    assert saida.exit_code == 0, saida.output
    assert "tb_logs: linhas=3" in saida.output and "mais_antigo.tb_logs=" in saida.output
