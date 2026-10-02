"""Normalizacao de enderecos de e-mail sem dependencias externas."""

from __future__ import annotations

import re
from collections.abc import Iterable

from luftbase.nucleo.excecoes import ErroEmail

# Validacao pragmatica: rejeita o que quebraria o cabecalho SMTP sem tentar cobrir a RFC 5322.
_ROTULO_DOMINIO = r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
_PADRAO_ENDERECO = re.compile(
    rf"^[^@\s<>(),;:\"\[\]\\]+@{_ROTULO_DOMINIO}(?:\.{_ROTULO_DOMINIO})+$"
)
_SEPARADORES = re.compile(r"[;,\s]+")


def validar_endereco_email(valor: object) -> str:
    """Devolve o endereco limpo ou falha indicando o valor recusado."""

    endereco = str(valor or "").strip()
    if len(endereco) > 254 or not _PADRAO_ENDERECO.fullmatch(endereco):
        raise ErroEmail(f"Endereco de e-mail invalido: {endereco!r}.")
    return endereco


def normalizar_enderecos_email(valores: str | Iterable[object] | None) -> tuple[str, ...]:
    """Aceita texto separado por `;`, `,` ou espacos, ou uma colecao, sem repeticoes."""

    if valores is None:
        return ()
    if isinstance(valores, str):
        brutos: Iterable[object] = _SEPARADORES.split(valores)
    else:
        brutos = valores

    vistos: set[str] = set()
    enderecos: list[str] = []
    for bruto in brutos:
        if not str(bruto or "").strip():
            continue
        endereco = validar_endereco_email(bruto)
        chave = endereco.casefold()
        if chave not in vistos:
            vistos.add(chave)
            enderecos.append(endereco)
    return tuple(enderecos)
