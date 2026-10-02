"""Integracao Flask da autorizacao corporativa."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import wraps
from typing import Any, ParamSpec, TypeVar

from flask import Flask, abort
from flask_login import current_user

from luftbase.autorizacao.chaves import normalizar_chave
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroAutorizacao
from luftbase.observabilidade.web import marcar_decisao_autorizacao

P = ParamSpec("P")
R = TypeVar("R")


def _usuario_atual() -> UsuarioAutenticado | None:
    usuario = current_user._get_current_object()
    return usuario if isinstance(usuario, UsuarioAutenticado) else None


def tem_permissao(chave: str) -> bool:
    """Consulta programaticamente a permissao do usuario da requisicao."""

    usuario = _usuario_atual()
    if usuario is None:
        return False
    from luftbase.plataforma import obter_luftbase

    try:
        return obter_luftbase().autorizacao.possui(usuario, chave)
    except ErroAutorizacao:
        return False


def consultar_permissoes(chaves: Iterable[str]) -> dict[str, bool]:
    """Consulta em lote para evitar chamadas repetidas em templates."""

    usuario = _usuario_atual()
    if usuario is None:
        return {}
    from luftbase.plataforma import obter_luftbase

    try:
        return obter_luftbase().autorizacao.consultar(usuario, chaves)
    except ErroAutorizacao:
        return {}


def exigir_permissao(chave: str) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Protege uma view e responde 401, 403 ou 503 sem conceder em falha."""

    chave_normalizada = normalizar_chave(chave)

    def decorar(funcao: Callable[P, R]) -> Callable[P, R]:
        @wraps(funcao)
        def executar(*args: P.args, **kwargs: P.kwargs) -> R:
            usuario = _usuario_atual()
            if usuario is None:
                marcar_decisao_autorizacao(chave_normalizada, False)
                abort(401)
            from luftbase.plataforma import obter_luftbase

            try:
                permitido = obter_luftbase().autorizacao.possui(
                    usuario,
                    chave_normalizada,
                )
            except ErroAutorizacao:
                marcar_decisao_autorizacao(chave_normalizada, False)
                abort(503)
            if not permitido:
                marcar_decisao_autorizacao(chave_normalizada, False)
                abort(403)
            marcar_decisao_autorizacao(chave_normalizada, True)
            return funcao(*args, **kwargs)

        return executar

    return decorar


def exigir_alguma_permissao(
    chaves: Iterable[str],
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Autoriza quando ao menos uma chave e comprovada, sem consultas repetidas."""

    chaves_normalizadas = tuple(dict.fromkeys(normalizar_chave(chave) for chave in chaves))
    if not chaves_normalizadas:
        raise ValueError("Informe ao menos uma permissao para proteger a view.")

    def decorar(funcao: Callable[P, R]) -> Callable[P, R]:
        @wraps(funcao)
        def executar(*args: P.args, **kwargs: P.kwargs) -> R:
            usuario = _usuario_atual()
            chave_auditoria = "UMA_DE:" + ",".join(chaves_normalizadas)
            if usuario is None:
                marcar_decisao_autorizacao(chave_auditoria, False)
                abort(401)
            from luftbase.plataforma import obter_luftbase

            try:
                decisoes = obter_luftbase().autorizacao.consultar(
                    usuario,
                    chaves_normalizadas,
                )
            except ErroAutorizacao:
                marcar_decisao_autorizacao(chave_auditoria, False)
                abort(503)
            permitido = any(decisoes.get(chave, False) for chave in chaves_normalizadas)
            marcar_decisao_autorizacao(chave_auditoria, permitido)
            if not permitido:
                abort(403)
            return funcao(*args, **kwargs)

        return executar

    return decorar


def registrar_contexto_jinja(app: Flask) -> None:
    """Registra helpers em portugues, mantendo o servico preso a esta aplicacao."""

    @app.context_processor
    def contexto_autorizacao() -> dict[str, Any]:
        return {
            "tem_permissao": tem_permissao,
            "consultar_permissoes": consultar_permissoes,
        }
