"""Redacao e serializacao segura de dados para logs e auditoria."""

from __future__ import annotations

import json
import math
import os
import re
import traceback
from collections.abc import Mapping, Sequence
from typing import Any

_CHAVES_SENSIVEIS = re.compile(
    r"senha|password|token|authorization|cookie|secret|credencial|chave_assinatura",
    re.IGNORECASE,
)
_VALOR_REDACTADO = "[REDACTED]"

# Texto livre (mensagens de log) nao tem chaves: mascara os padroes que costumam carregar segredo.
_SEGREDOS_EM_TEXTO = (
    re.compile(
        r"(?P<chave>senha|password|passwd|pwd|token|secret|authorization|api[_-]?key)(?P<sep>\s*[=:]\s*)"
        r"(?:Bearer\s+)?(?P<valor>[^\s,;&\"')]+)",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<esquema>[a-z][a-z0-9+.-]*://)(?P<usuario>[^/\s:@]+):(?P<senha>[^@\s/]+)@", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z0-9])hv[sbr]\.[A-Za-z0-9_-]{8,}"),
)


def mascarar_texto(texto: str, *, maximo: int = 2_000) -> str:
    """Esconde segredos obvios de um texto livre, junta as linhas e limita o tamanho (para uma linha de log)."""

    resultado = _SEGREDOS_EM_TEXTO[0].sub(
        lambda m: f"{m.group('chave')}{m.group('sep')}{_VALOR_REDACTADO}", texto
    )
    resultado = _SEGREDOS_EM_TEXTO[1].sub(
        lambda m: f"{m.group('esquema')}{m.group('usuario')}:{_VALOR_REDACTADO}@", resultado
    )
    resultado = _SEGREDOS_EM_TEXTO[2].sub(_VALOR_REDACTADO, resultado)
    resultado = " ↵ ".join(parte.strip() for parte in resultado.splitlines() if parte.strip())
    if len(resultado) > maximo:
        resultado = f"{resultado[:maximo]}...[TRUNCADO]"
    return resultado


def resumir_excecao(erro: BaseException, *, quadros: int = 8) -> dict[str, object]:
    """Descreve ONDE e DE QUE TIPO foi uma excecao, sem nenhum valor (mensagem ou parametros).

    Mensagens de erro de banco costumam carregar dados e credenciais, entao nunca entram. Fica a
    cadeia de tipos (causa -> efeito) e as ultimas linhas da pilha (arquivo, linha e funcao),
    o suficiente para localizar o defeito num servico sem console.
    """

    cadeia: list[str] = []
    atual: BaseException | None = erro
    raiz: BaseException = erro
    while atual is not None and len(cadeia) < 6:
        cadeia.append(f"{type(atual).__module__}.{type(atual).__qualname__}")
        raiz = atual
        atual = atual.__cause__ or (None if atual.__suppress_context__ else atual.__context__)

    def linhas(excecao: BaseException) -> list[str]:
        pilha = traceback.extract_tb(excecao.__traceback__)[-quadros:]
        return [f"{os.path.basename(q.filename)}:{q.lineno} {q.name}" for q in pilha]

    resumo: dict[str, object] = {"cadeia": cadeia, "pilha": linhas(erro)}
    if raiz is not erro:
        # Onde o erro NASCEU (ex.: o driver do banco), distinto de quem o embrulhou.
        resumo["origem"] = linhas(raiz)
    return resumo


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
