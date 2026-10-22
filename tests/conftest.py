"""Configuracao comum dos testes."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _logs_fisicos_em_pasta_temporaria(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """A plataforma grava `Logs/luftbase.log` ao subir; nos testes isso vai para uma pasta temporaria.

    Ao fim de cada teste o handler que captura o logger `luftbase` e retirado, para um teste nao
    escrever (nem herdar linhas) no arquivo de outro.
    """

    from luftbase import plataforma

    original = plataforma.LoggerFisicoAuditoria
    pasta = tmp_path_factory.mktemp("logs")

    def criar(diretorio_logs: str | Path = "Logs", *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        destino = pasta if str(diretorio_logs) == "Logs" else diretorio_logs
        return original(destino, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(plataforma, "LoggerFisicoAuditoria", criar)
    yield
    alvo = logging.getLogger("luftbase")
    for handler in list(alvo.handlers):
        if getattr(handler, "_luftbase_captura_fisica", False):
            alvo.removeHandler(handler)
            handler.close()
