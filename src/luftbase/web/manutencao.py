"""Middleware de disponibilidade: sistema descontinuado (inativo) e modo de manutencao."""

from __future__ import annotations

import logging
import time

from flask import Flask, Response, jsonify, make_response, render_template, request
from flask_login import current_user

from luftbase.autorizacao.catalogo import PermissaoLuftBase
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.persistencia.core.seguranca import Sistema

logger = logging.getLogger(__name__)

_ROTAS_ISENTAS_MANUTENCAO = frozenset(
    {
        "/_luftbase/saude",
        "/_luftbase/prontidao",
        "/_luftbase/metricas",
        "/login",
        "/logout",
    }
)

_PREFIXOS_ESTATICOS = (
    "/static/",
    "/_luftbase/static/",
    "/favicon.ico",
)

_EXTENSOES_ESTATICAS = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".json",
)

# Rotas que continuam respondendo num sistema descontinuado: so saude e encerramento de sessao.
_ROTAS_ISENTAS_DESCONTINUADO = frozenset(
    {"/_luftbase/saude", "/_luftbase/prontidao", "/_luftbase/metricas", "/logout", "/sair"}
)

# Cache em memoria por processo com TTL curto: (em_manutencao, ativo, expira_em)
_CACHE_MANUTENCAO: dict[int, tuple[bool, bool, float]] = {}
_TTL_CACHE_SEGUNDOS = 3.0


def invalidar_cache_manutencao(id_sistema: int | None = None) -> None:
    """Invalida o cache de manutencao de um sistema especifico ou de todos."""

    if id_sistema is None:
        _CACHE_MANUTENCAO.clear()
    else:
        _CACHE_MANUTENCAO.pop(id_sistema, None)


def _estado_sistema(id_sistema: int) -> tuple[bool, bool]:
    """Devolve (em_manutencao, ativo) com cache de curta duracao.

    Falha de consulta nao derruba a aplicacao: assume ativo e fora de manutencao.
    """

    if id_sistema == 0:
        return False, True

    agora = time.time()
    cached = _CACHE_MANUTENCAO.get(id_sistema)
    if cached is not None:
        em_manutencao, ativo, expira_em = cached
        if agora < expira_em:
            return em_manutencao, ativo

    from luftbase.plataforma import obter_luftbase

    try:
        estado = obter_luftbase()
        with estado.bancos.core.leitura() as sessao:
            sistema = sessao.get(Sistema, id_sistema)
            em_manutencao = bool(sistema.em_manutencao) if sistema else False
            ativo = bool(sistema.ativo) if sistema else True
            _CACHE_MANUTENCAO[id_sistema] = (em_manutencao, ativo, agora + _TTL_CACHE_SEGUNDOS)
            return em_manutencao, ativo
    except Exception as erro:
        logger.warning("Falha ao consultar estado do sistema %s: %s", id_sistema, erro)
        return False, True


def _sistema_em_manutencao(id_sistema: int) -> bool:
    """Consulta se o sistema esta em manutencao com cache de curta duracao."""

    return _estado_sistema(id_sistema)[0]


def _eh_estatico(caminho: str) -> bool:
    if any(caminho.startswith(prefixo) for prefixo in _PREFIXOS_ESTATICOS):
        return True
    caminho_base = caminho.split("?")[0].lower()
    return any(caminho_base.endswith(ext) for ext in _EXTENSOES_ESTATICAS)


def _espera_json() -> bool:
    return bool(
        request.is_json
        or request.path.startswith(("/api/", "/_luftbase/"))
        or request.headers.get("Accept") == "application/json"
    )


def _rota_isenta(caminho: str) -> bool:
    """Verifica se o caminho solicitado e isento de bloqueio de manutencao."""

    return caminho in _ROTAS_ISENTAS_MANUTENCAO or _eh_estatico(caminho)


def _operador_autorizado_bypass() -> bool:
    """Verifica se o usuario autenticado possui permissao para contornar manutencao."""

    usuario = current_user._get_current_object()
    if not isinstance(usuario, UsuarioAutenticado):
        return False

    from luftbase.plataforma import obter_luftbase

    try:
        autorizacao = obter_luftbase().autorizacao
        return bool(
            autorizacao.possui(usuario, PermissaoLuftBase.MANUTENCAO_GERENCIAR)
            or autorizacao.possui(usuario, PermissaoLuftBase.MANUTENCAO_IGNORAR)
        )
    except Exception:
        return False


def registrar_middleware_manutencao(app: Flask) -> None:
    """Instala o hook before_request para interceptar acessos durante manutencao."""

    @app.before_request
    def interceptar_manutencao() -> Response | None:
        if _eh_estatico(request.path):
            return None

        from luftbase.plataforma import obter_luftbase

        try:
            estado = obter_luftbase()
            id_sistema = estado.configuracao.aplicacao.sistema_id
        except Exception:
            return None

        if id_sistema is None or id_sistema == 0:
            return None

        em_manutencao, ativo = _estado_sistema(id_sistema)

        # Sistema descontinuado: vale para todos, sem bypass. Reativacao e feita pelo Workspace.
        if not ativo:
            if request.path in _ROTAS_ISENTAS_DESCONTINUADO:
                return None
            if _espera_json():
                resp = jsonify(
                    {
                        "status": "error",
                        "code": 410,
                        "message": "Este sistema foi descontinuado.",
                    }
                )
                resp.status_code = 410
                return resp
            return make_response(render_template("luftbase/pages/descontinuado.html"), 410)

        if not em_manutencao or _rota_isenta(request.path):
            return None

        if _operador_autorizado_bypass():
            return None

        # Bloqueio ativo
        if _espera_json():
            resp = jsonify(
                {
                    "status": "error",
                    "code": 503,
                    "message": "A aplicação está temporariamente em manutenção.",
                }
            )
            resp.status_code = 503
            return resp

        return make_response(render_template("luftbase/pages/maintenance.html"), 503)


__all__ = [
    "invalidar_cache_manutencao",
    "registrar_middleware_manutencao",
]
