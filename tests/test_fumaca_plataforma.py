"""Fumaca por plataforma: o que so quebra num sistema operacional especifico.

Roda em Windows e Linux no CI. O bug do horario 3 h adiantado (0.1.0a88) so existia no Windows.
"""

from __future__ import annotations

import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from luftbase.nucleo import tempo
from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria


def _fechar(logger: LoggerFisicoAuditoria) -> None:
    for handler in list(logger._logger.handlers):  # noqa: SLF001
        handler.close()
        logger._logger.removeHandler(handler)  # noqa: SLF001


def test_log_fisico_grava_o_horario_de_brasilia(tmp_path: Path) -> None:
    logger = LoggerFisicoAuditoria(tmp_path, "fumaca.log")
    try:
        antes = tempo.agora_local()
        logger.info("linha de fumaca", login="teste")
        depois = tempo.agora_local()
    finally:
        _fechar(logger)

    linha = (tmp_path / "fumaca.log").read_text(encoding="utf-8").splitlines()[0]
    gravado = re.match(r"\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\]", linha)
    assert gravado, linha
    momento = datetime.strptime(gravado.group(1), "%Y-%m-%d %H:%M:%S")
    assert antes - timedelta(seconds=2) <= momento <= depois + timedelta(seconds=2)


def test_leitura_do_log_fisico_devolve_a_mesma_data(tmp_path: Path) -> None:
    logger = LoggerFisicoAuditoria(tmp_path, "leitura.log")
    try:
        logger.info("x", login="teste")
        registros = logger.ler_recentes()
        arquivos = logger.listar_arquivos()
    finally:
        _fechar(logger)

    assert registros and registros[0].data_hora
    momento = datetime.strptime(registros[0].data_hora, "%Y-%m-%d %H:%M:%S")
    assert abs(tempo.agora_local() - momento) < timedelta(seconds=5)
    modificado = datetime.fromisoformat(str(arquivos[0]["modificado_em"]))
    assert abs(tempo.agora_local() - modificado) < timedelta(seconds=5)


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="so existe no Linux/macOS")
def test_com_tzset_o_processo_vai_para_brasilia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LUFT_FUSO_HORARIO", raising=False)
    original = os.environ.get("TZ")
    try:
        tempo.aplicar_fuso_do_processo()
        assert time.localtime().tm_gmtoff == -3 * 3600
    finally:
        if original is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original
        time.tzset()


@pytest.mark.skipif(sys.platform != "win32", reason="regressao especifica do Windows")
def test_no_windows_o_tz_do_ambiente_nao_e_alterado(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TZ", raising=False)

    tempo.aplicar_fuso_do_processo()

    assert "TZ" not in os.environ  # senao o runtime C le "America/Sao_Paulo" como UTC


def test_formatador_ignora_o_fuso_da_maquina() -> None:
    registro = logging.LogRecord("t", logging.INFO, __file__, 1, "m", None, None)
    formatado = tempo.FormatadorDeLog("%(asctime)s", datefmt="%Y-%m-%d %H:%M:%S").format(registro)

    assert abs(tempo.agora_local() - datetime.strptime(formatado, "%Y-%m-%d %H:%M:%S")) < (
        timedelta(seconds=5)
    )
