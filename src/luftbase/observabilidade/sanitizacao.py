"""Redacao e serializacao segura de dados para logs e auditoria."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

_CHAVES_SENSIVEIS = re.compile(
    r"senha|password|token|authorization|cookie|secret|credencial|chave_assinatura",
    re.IGNORECASE,
)
_VALOR_REDACTADO = "[REDACTED]"


def sanitizar_dados(
    valor: object,
    *,
    profundidade: int = 0,
    maximo_profundidade: int = 5,
    maximo_itens: int = 50,
    maximo_texto: int = 1_000,
) -> Any:
    """Converte dados arbitrarios em tipos JSON limitados e sem segredos obvios."""

    if profundidade >= maximo_profundidade:
        return "[LIMITE_DE_PROFUNDIDADE]"
    if valor is None or isinstance(valor, bool | int):
        return valor
    if isinstance(valor, float):
        return valor if math.isfinite(valor) else str(valor)
    if isinstance(valor, str):
        if len(valor) <= maximo_texto:
            return valor
        return f"{valor[:maximo_texto]}...[TRUNCADO]"
    if isinstance(valor, bytes):
        return f"[BYTES:{len(valor)}]"
    if isinstance(valor, Mapping):
        resultado: dict[str, Any] = {}
        for indice, (chave, item) in enumerate(valor.items()):
            if indice >= maximo_itens:
                resultado["__truncado__"] = True
                break
            nome = str(chave)[:200]
            resultado[nome] = (
                _VALOR_REDACTADO
                if _CHAVES_SENSIVEIS.search(nome)
                else sanitizar_dados(
                    item,
                    profundidade=profundidade + 1,
                    maximo_profundidade=maximo_profundidade,
                    maximo_itens=maximo_itens,
                    maximo_texto=maximo_texto,
                )
            )
        return resultado
    if isinstance(valor, Sequence):
        itens = list(valor[:maximo_itens])
        itens_sanitizados = [
            sanitizar_dados(
                item,
                profundidade=profundidade + 1,
                maximo_profundidade=maximo_profundidade,
                maximo_itens=maximo_itens,
                maximo_texto=maximo_texto,
            )
            for item in itens
        ]
        if len(valor) > maximo_itens:
            itens_sanitizados.append("[TRUNCADO]")
        return itens_sanitizados
    return f"[OBJETO:{type(valor).__name__}]"


def serializar_dados_seguro(valor: object, *, maximo_caracteres: int = 12_000) -> str:
    """Serializa JSON valido e substitui payloads grandes por um resumo."""

    serializado = json.dumps(
        sanitizar_dados(valor),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(serializado) <= maximo_caracteres:
        return serializado
    return json.dumps(
        {"truncado": True, "tamanho_original": len(serializado)},
        separators=(",", ":"),
    )
