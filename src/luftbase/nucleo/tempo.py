"""Relogio unico da plataforma: horario de Brasilia, independente do fuso do servidor.

Servidores Windows usam o horario local e os Linux costumam rodar em UTC. `datetime.now()` devolve
o horario DA MAQUINA, entao o mesmo codigo gravava 14:55 num e 17:55 no outro. Tudo que o
LuftBase persiste ou mostra como horario passa por `agora_local()`, e o processo inteiro e
levado ao mesmo fuso por `aplicar_fuso_do_processo()` (cobre o codigo das aplicacoes e os logs).

O fuso padrao e `America/Sao_Paulo`; `LUFT_FUSO_HORARIO` o substitui.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

FUSO_PADRAO = "America/Sao_Paulo"
_logger = logging.getLogger("luftbase.tempo")


def nome_do_fuso() -> str:
    return (os.environ.get("LUFT_FUSO_HORARIO") or "").strip() or FUSO_PADRAO


def agora_local() -> datetime:
    """Horario atual no fuso da plataforma, sem tzinfo (formato das colunas `timestamp`)."""

    return datetime.now(ZoneInfo(nome_do_fuso())).replace(tzinfo=None)


def de_timestamp(valor: float) -> datetime:
    """Converte um epoch (ex.: `st_mtime`, `record.created`) para o horario da plataforma."""

    return datetime.fromtimestamp(valor, ZoneInfo(nome_do_fuso())).replace(tzinfo=None)


class FormatadorDeLog(logging.Formatter):
    """`logging.Formatter` cujo `%(asctime)s` e sempre o horario da plataforma.

    O formatter padrao usa `time.localtime`, isto e, o fuso da maquina; em Windows isso nao e
    controlavel pelo processo. Todo log gravado ou exibido pela plataforma deve usar esta classe.
    """

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        momento = de_timestamp(record.created)
        if datefmt:
            return momento.strftime(datefmt)
        return f"{momento:%Y-%m-%d %H:%M:%S},{int(record.msecs):03d}"


def aplicar_fuso_do_processo() -> None:
    """Poe o processo inteiro no fuso da plataforma (Linux; no Windows o fuso e do sistema).

    No Linux faz `datetime.now()`, `time.localtime()` e os `%(asctime)s` dos logs, inclusive os do
    codigo das aplicacoes, concordarem com `agora_local()`. No Windows nao altera nada (ver abaixo);
    os logs do LuftBase la dependem do `FormatadorDeLog`. Idempotente.
    """

    fuso = nome_do_fuso()
    tzset = getattr(time, "tzset", None)
    if tzset is None:
        # Windows: o runtime C nao entende nomes IANA em `TZ` ("America/Sao_Paulo" vira UTC) e
        # o fuso do processo nao muda em execucao. Nao tocar em `TZ`; os horarios gravados e os
        # logs usam `agora_local()`/`FormatadorDeLog`, que independem do fuso da maquina.
        return
    os.environ["TZ"] = fuso
    tzset()
    esperado = datetime.now(ZoneInfo(fuso)).utcoffset()
    local = time.localtime().tm_gmtoff
    if esperado is not None and local != int(esperado.total_seconds()):
        _logger.warning(
            "O fuso %s nao foi aplicado ao processo (falta o pacote tzdata do sistema?); "
            "os horarios gravados continuam corretos, mas os logs seguem o fuso da maquina.",
            fuso,
        )


__all__ = [
    "FUSO_PADRAO",
    "FormatadorDeLog",
    "agora_local",
    "aplicar_fuso_do_processo",
    "de_timestamp",
    "nome_do_fuso",
]
