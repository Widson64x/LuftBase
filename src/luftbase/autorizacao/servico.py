"""Decisoes de autorizacao sob demanda com cache em duas camadas."""

from __future__ import annotations

from collections.abc import Iterable
from contextlib import suppress
from typing import Protocol

from luftbase.autorizacao.cache import CacheAutorizacaoRedis, CacheRequisicaoAutorizacao
from luftbase.autorizacao.chaves import normalizar_chave, normalizar_chaves
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroAutorizacao


class FontePermissoes(Protocol):
    """Persistencia exigida pelo servico de autorizacao."""

    def consultar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        chaves: Iterable[str],
    ) -> dict[str, bool]:
        """Consulta as chaves informadas."""

    def obter_revisao(self) -> int:
        """Le a revisao atual."""

    def incrementar_revisao(self) -> int:
        """Incrementa a revisao atual."""


class ServicoAutorizacao:
    """Autoriza somente o que puder ser comprovado pelo cache ou PostgreSQL."""

    def __init__(
        self,
        *,
        id_sistema: int,
        repositorio: FontePermissoes,
        cache_distribuido: CacheAutorizacaoRedis,
        cache_requisicao: CacheRequisicaoAutorizacao | None = None,
        maximo_chaves_consulta: int = 100,
    ) -> None:
        self._id_sistema = id_sistema
        self._repositorio = repositorio
        self._cache_distribuido = cache_distribuido
        self._cache_requisicao = cache_requisicao or CacheRequisicaoAutorizacao()
        self._maximo_chaves = maximo_chaves_consulta

    def possui(self, usuario: UsuarioAutenticado, chave: str) -> bool:
        """Verifica uma chave sem carregar o catalogo completo do usuario."""

        chave_normalizada = normalizar_chave(chave)
        return self.consultar(usuario, (chave_normalizada,))[chave_normalizada]

    def consultar(
        self,
        usuario: UsuarioAutenticado,
        chaves: Iterable[object],
    ) -> dict[str, bool]:
        """Resolve um lote e conserva a ordem canonica das chaves."""

        chaves_normalizadas = normalizar_chaves(chaves, maximo=self._maximo_chaves)
        if not chaves_normalizadas:
            return {}

        resultados: dict[str, bool] = {}
        faltantes: list[str] = []
        for chave in chaves_normalizadas:
            chave_requisicao = self._chave_requisicao(usuario, chave)
            permitido = self._cache_requisicao.obter(chave_requisicao)
            if permitido is None:
                faltantes.append(chave)
            else:
                resultados[chave] = permitido
        if faltantes:
            resultados.update(self._consultar_faltantes(usuario, tuple(faltantes)))
        return {chave: resultados.get(chave, False) for chave in chaves_normalizadas}

    def invalidar_cache(self) -> int:
        """Incrementa a revisao depois de qualquer alteracao de permissoes."""

        revisao = self._repositorio.incrementar_revisao()
        # A revisao persistida continua sendo a fonte definitiva se o Redis falhar.
        with suppress(Exception):
            self._cache_distribuido.salvar_revisao(revisao)
        return revisao

    def _consultar_faltantes(
        self,
        usuario: UsuarioAutenticado,
        chaves: tuple[str, ...],
    ) -> dict[str, bool]:
        revisao = self._obter_revisao()
        resultados: dict[str, bool] | None = None
        try:
            resultados = self._cache_distribuido.obter_resultados(
                id_sistema=self._id_sistema,
                id_usuario=usuario.id_usuario,
                id_grupo=usuario.id_grupo,
                revisao=revisao,
                chaves=chaves,
            )
        except Exception:
            resultados = None

        if resultados is None:
            try:
                consultados = self._repositorio.consultar(
                    id_sistema=self._id_sistema,
                    id_usuario=usuario.id_usuario,
                    id_grupo=usuario.id_grupo,
                    chaves=chaves,
                )
            except ErroAutorizacao:
                raise
            except Exception as erro:
                raise ErroAutorizacao(
                    "Nao foi possivel comprovar as permissoes solicitadas."
                ) from erro
            resultados = {chave: consultados.get(chave, False) for chave in chaves}
            with suppress(Exception):
                self._cache_distribuido.salvar_resultados(
                    id_sistema=self._id_sistema,
                    id_usuario=usuario.id_usuario,
                    id_grupo=usuario.id_grupo,
                    revisao=revisao,
                    resultados=resultados,
                )

        for chave, permitido in resultados.items():
            self._cache_requisicao.salvar(
                self._chave_requisicao(usuario, chave),
                permitido,
            )
        return resultados

    def _obter_revisao(self) -> int:
        try:
            revisao = self._cache_distribuido.obter_revisao()
        except Exception:
            revisao = None
        if revisao is not None:
            return revisao
        try:
            revisao = self._repositorio.obter_revisao()
        except ErroAutorizacao:
            raise
        except Exception as erro:
            raise ErroAutorizacao("Nao foi possivel comprovar a revisao das permissoes.") from erro
        with suppress(Exception):
            self._cache_distribuido.salvar_revisao(revisao)
        return revisao

    def _chave_requisicao(self, usuario: UsuarioAutenticado, chave: str) -> str:
        grupo = usuario.id_grupo if usuario.id_grupo is not None else 0
        return f"{self._id_sistema}:{usuario.id_usuario}:{grupo}:{chave}"
