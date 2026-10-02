"""Sinal efemero de conteudo; nunca substitui a consulta ao PostgreSQL."""

from __future__ import annotations

import json
from typing import Protocol


class ArmazenamentoChaveValor(Protocol):
    """Subconjunto do adaptador Redis necessario para os sinais."""

    def obter(self, chave: str) -> bytes | None:
        """Le um valor binario."""

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        """Grava um valor com expiracao."""


class SinalizadorConteudoRedis:
    """Mantem apenas o ultimo cursor para acordar ou orientar consumidores."""

    def __init__(
        self,
        armazenamento: ArmazenamentoChaveValor,
        *,
        ttl_segundos: int = 86_400,
    ) -> None:
        self._armazenamento = armazenamento
        self._ttl_segundos = ttl_segundos

    def publicar(self, tipo: str, id_sistema: int, cursor: int) -> bool:
        """Atualiza o sinal em melhor esforco, sem afetar o commit principal."""

        carga = json.dumps(
            {"cursor": cursor},
            separators=(",", ":"),
        ).encode("utf-8")
        try:
            self._armazenamento.salvar(
                self._chave(tipo, id_sistema),
                carga,
                self._ttl_segundos,
            )
        except Exception:
            return False
        return True

    def obter_cursor(self, tipo: str, id_sistema: int) -> int | None:
        """Le um sinal valido; ausencia ou corrupcao equivale a cache vazio."""

        try:
            carga = self._armazenamento.obter(self._chave(tipo, id_sistema))
            if carga is None:
                return None
            valor = json.loads(carga.decode("utf-8"))
            cursor = valor.get("cursor") if isinstance(valor, dict) else None
            return cursor if isinstance(cursor, int) and cursor >= 0 else None
        except Exception:
            return None

    @staticmethod
    def _chave(tipo: str, id_sistema: int) -> str:
        return f"luftbase:conteudo:{tipo}:{id_sistema}:cursor"
