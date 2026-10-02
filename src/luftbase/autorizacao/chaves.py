"""Validacao canonica das chaves de permissao."""

from __future__ import annotations

import re
from collections.abc import Iterable

from luftbase.nucleo.excecoes import ErroAutorizacao

_PADRAO_CHAVE = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,99}$")


def normalizar_chave(valor: object) -> str:
    """Normaliza uma chave e rejeita entradas ambiguas ou perigosas."""

    chave = str(valor or "").strip().upper()
    if not _PADRAO_CHAVE.fullmatch(chave):
        raise ErroAutorizacao("A chave de permissao deve possuir ate 100 caracteres alfanumericos.")
    return chave


def normalizar_chaves(valores: Iterable[object], *, maximo: int) -> tuple[str, ...]:
    """Remove duplicidades e limita o tamanho de uma consulta em lote."""

    chaves = tuple(sorted({normalizar_chave(valor) for valor in valores}))
    if len(chaves) > maximo:
        raise ErroAutorizacao(f"Uma consulta aceita no maximo {maximo} chaves de permissao.")
    return chaves
