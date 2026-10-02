"""Politica central de resolucao e validacao de escopo administrativo do LuftBase."""

from __future__ import annotations

import logging

from flask import abort
from flask_login import current_user

from luftbase.identidade.modelos import UsuarioAutenticado

logger = logging.getLogger(__name__)


def usuario_autenticado_atual() -> UsuarioAutenticado:
    """Obtem o usuario autenticado atual ou dispara 401."""

    usuario = current_user._get_current_object()
    if not isinstance(usuario, UsuarioAutenticado):
        abort(401)
    return usuario


def sistema_aplicacao_atual() -> int:
    """Retorna o id_sistema configurado para a aplicacao atual."""

    from luftbase.plataforma import obter_luftbase

    id_sistema = obter_luftbase().configuracao.aplicacao.sistema_id
    if id_sistema is None:
        abort(503, description="Identificador da aplicacao nao configurado.")
    return id_sistema


def eh_sistema_master() -> bool:
    """Informa se a aplicacao atual opera como Hub Master (sistema 0)."""

    return sistema_aplicacao_atual() == 0


def resolver_escopo_sistema(
    sistema_solicitado: int | str | None = None,
    *,
    permitir_global_master: bool = True,
) -> int:
    """Resolve e valida o escopo de sistema permitido para a requisicao atual.

    Regras:
    1. Se a aplicacao atual e master (sistema 0):
       - Se nenhum sistema for informado, assume 0 (se permitir_global_master) ou busca o primeiro.
       - Se um id_sistema for informado, permite operar sobre ele (0 ou qualquer outro).
    2. Se a aplicacao atual NAO e master (sistema != 0):
       - So pode administrar seu proprio id_sistema.
       - Se nenhum sistema for informado, assume o sistema da aplicacao.
       - Se um id_sistema diferente for solicitado pela query string ou payload, bloqueia com 403.
    """

    id_app = sistema_aplicacao_atual()

    if sistema_solicitado is None or str(sistema_solicitado).strip() == "":
        return 0 if id_app == 0 and permitir_global_master else id_app

    try:
        id_alvo = int(sistema_solicitado)
    except (TypeError, ValueError):
        abort(400, description="Identificador de sistema invalido.")

    if id_alvo < 0:
        abort(400, description="Identificador de sistema nao pode ser negativo.")

    if id_app == 0:
        # Sistema master pode administrar escopo global (0) ou sistemas especificos.
        return id_alvo

    # Sistema nao-master so pode operar sobre o seu proprio escopo.
    if id_alvo != id_app:
        logger.warning(
            "Tentativa de operacao cross-system negada: app=%s tentou operar sobre sistema=%s",
            id_app,
            id_alvo,
        )
        abort(403, description="Acesso negado: operacao restrita ao escopo da aplicacao atual.")

    return id_alvo


def validar_sistema_alteravel_manutencao(id_sistema: int) -> None:
    """Garante que o sistema 0 nunca seja colocado em manutencao."""

    if id_sistema == 0:
        abort(
            403,
            description="O sistema base (ID 0) e protegido e nao pode entrar em manutencao.",
        )


__all__ = [
    "eh_sistema_master",
    "resolver_escopo_sistema",
    "sistema_aplicacao_atual",
    "usuario_autenticado_atual",
    "validar_sistema_alteravel_manutencao",
]
