"""Caches de autorizacao por requisicao e no Redis compartilhado."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol

from flask import g, has_request_context


class ArmazenamentoCache(Protocol):
    """Operacoes de chave e valor usadas pelo cache distribuido."""

    def obter(self, chave: str) -> bytes | None:
        """Le um valor bruto."""

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        """Salva um valor com expiracao obrigatoria."""

    def remover(self, chave: str) -> None:
        """Remove uma chave."""


class CacheRequisicaoAutorizacao:
    """Evita repetir a mesma decisao dentro de uma requisicao Flask."""

    _atributo = "_luftbase_permissoes"

    def _dados(self) -> dict[str, bool]:
        if not has_request_context():
            return {}
        dados = getattr(g, self._atributo, None)
        if not isinstance(dados, dict):
            dados = {}
            setattr(g, self._atributo, dados)
        return dados

    def obter(self, chave: str) -> bool | None:
        """Devolve a decisao da requisicao, quando existente."""

        valor = self._dados().get(chave)
        return valor if isinstance(valor, bool) else None

    def salvar(self, chave: str, permitido: bool) -> None:
        """Memoriza uma decisao ate o fim da requisicao atual."""

        if has_request_context():
            self._dados()[chave] = permitido


class CacheAutorizacaoRedis:
    """Mantem revisao e lotes de decisoes em JSON com TTL curto."""

    _prefixo = "luft:autorizacao:"

    def __init__(
        self,
        armazenamento: ArmazenamentoCache,
        *,
        ttl_resultado_segundos: int,
        ttl_revisao_segundos: int,
    ) -> None:
        self._armazenamento = armazenamento
        self._ttl_resultado = ttl_resultado_segundos
        self._ttl_revisao = ttl_revisao_segundos

    @property
    def _chave_revisao(self) -> str:
        return f"{self._prefixo}revisao"

    def obter_revisao(self) -> int | None:
        """Le a revisao compartilhada, rejeitando payloads invalidos."""

        bruto = self._armazenamento.obter(self._chave_revisao)
        if bruto is None:
            return None
        try:
            revisao = int(bruto.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            self._armazenamento.remover(self._chave_revisao)
            return None
        return revisao if revisao >= 0 else None

    def salvar_revisao(self, revisao: int) -> None:
        """Publica a revisao com uma janela curta de revalidacao no banco."""

        self._armazenamento.salvar(
            self._chave_revisao,
            str(revisao).encode("ascii"),
            self._ttl_revisao,
        )

    def obter_resultados(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        revisao: int,
        chaves: tuple[str, ...],
    ) -> dict[str, bool] | None:
        """Le um lote somente se ele corresponder exatamente as chaves pedidas."""

        chave_cache = self._chave_resultado(
            id_sistema=id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            revisao=revisao,
            chaves=chaves,
        )
        bruto = self._armazenamento.obter(chave_cache)
        if bruto is None:
            return None
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._armazenamento.remover(chave_cache)
            return None
        if not isinstance(dados, dict) or set(dados) != set(chaves):
            self._armazenamento.remover(chave_cache)
            return None
        if not all(isinstance(valor, bool) for valor in dados.values()):
            self._armazenamento.remover(chave_cache)
            return None
        return {chave: dados[chave] for chave in chaves}

    def salvar_resultados(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        revisao: int,
        resultados: Mapping[str, bool],
    ) -> None:
        """Salva somente booleanos, sem dados pessoais ou nomes de usuario."""

        chaves = tuple(sorted(resultados))
        chave_cache = self._chave_resultado(
            id_sistema=id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            revisao=revisao,
            chaves=chaves,
        )
        bruto = json.dumps(
            {chave: bool(resultados[chave]) for chave in chaves},
            separators=(",", ":"),
        ).encode("utf-8")
        self._armazenamento.salvar(chave_cache, bruto, self._ttl_resultado)

    def _chave_resultado(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        revisao: int,
        chaves: tuple[str, ...],
    ) -> str:
        assinatura = hashlib.sha256("\x1f".join(chaves).encode("utf-8")).hexdigest()[:24]
        grupo = id_grupo if id_grupo is not None else 0
        return f"{self._prefixo}resultado:{revisao}:{id_sistema}:{id_usuario}:{grupo}:{assinatura}"
