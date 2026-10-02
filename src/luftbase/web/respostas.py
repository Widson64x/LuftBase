"""API publica padronizada em portugues para respostas e mensagens do LuftBase."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, ParamSpec, TypeVar, cast

from flask import (
    Response,
    abort,
    get_flashed_messages,
    has_request_context,
    jsonify,
    request,
    session,
)

P = ParamSpec("P")
R = TypeVar("R")

_CHAVE_MENSAGENS_PENDENTES = "_luftbase_mensagens_pendentes"

_TIPOS_VALIDOS = frozenset({"success", "warning", "danger", "info"})


def _tipo_padrao(status_http: int, sucesso: bool) -> str:
    if sucesso:
        return "success"
    if status_http >= 500:
        return "danger"
    if status_http in {400, 401, 403, 404, 409, 422}:
        return "warning"
    return "danger"


def _titulo_padrao(tipo: str, sucesso: bool) -> str:
    if sucesso:
        return "Operação concluída"
    if tipo == "warning":
        return "Atenção necessária"
    if tipo == "danger":
        return "Não foi possível concluir"
    return "Aviso do sistema"


def _icone_padrao(tipo: str) -> str:
    return {
        "success": "ph-check-circle",
        "warning": "ph-warning-circle",
        "danger": "ph-warning-octagon",
        "info": "ph-info",
    }.get(tipo, "ph-info")


def _enfileirar_mensagem_sessao(payload: dict[str, Any]) -> dict[str, Any]:
    """Enfileira mensagem na sessao Flask para consumo pelo endpoint /_luftbase/mensagens."""

    if has_request_context():
        mensagens = session.get(_CHAVE_MENSAGENS_PENDENTES)
        if not isinstance(mensagens, list):
            mensagens = []
        mensagens.append(payload)
        session[_CHAVE_MENSAGENS_PENDENTES] = mensagens
    return payload


def enfileirar_toast(
    mensagem: str,
    tipo: str = "info",
    *,
    titulo: str | None = None,
    duracao_ms: int = 5000,
    icone: str | None = None,
) -> dict[str, Any]:
    """Enfileira um toast para exibicao na interface pelo script corporativo."""

    tipo_limpo = tipo if tipo in _TIPOS_VALIDOS else "info"
    payload = {
        "tipo": tipo_limpo,
        "titulo": titulo or _titulo_padrao(tipo_limpo, tipo_limpo == "success"),
        "mensagem": mensagem,
        "icone": icone or _icone_padrao(tipo_limpo),
        "duracao": duracao_ms,
    }
    return _enfileirar_mensagem_sessao(payload)


_CATEGORIAS_FLASH = {"error": "danger", "erro": "danger", "message": "info", "sucesso": "success"}


def consumir_flashes() -> list[dict[str, Any]]:
    """Converte as mensagens de `flask.flash` pendentes em toasts do padrao corporativo.

    Aplicacoes migradas usam `flash(texto, categoria)`; sem esta ponte as mensagens ficariam
    presas na sessao, porque o layout do LuftBase so exibe a fila propria de mensagens.
    """

    toasts = []
    # Com `with_categories=True` o Flask devolve pares, mas a tipagem publica nao distingue.
    pares = cast(list[tuple[str, str]], get_flashed_messages(with_categories=True))
    for categoria, mensagem in pares:
        tipo = _CATEGORIAS_FLASH.get(categoria, categoria)
        tipo = tipo if tipo in _TIPOS_VALIDOS else "info"
        toasts.append(
            {
                "tipo": tipo,
                "titulo": _titulo_padrao(tipo, tipo == "success"),
                "mensagem": str(mensagem),
                "icone": _icone_padrao(tipo),
                "duracao": 5000,
            }
        )
    return toasts


def mensagem_sucesso(
    mensagem: str = "Operação realizada com sucesso.",
    *,
    status_http: int = 200,
    chave_popup: str | None = None,
    titulo: str | None = None,
    emitir_popup: bool = True,
    **opcoes: Any,
) -> dict[str, Any] | None:
    """Enfileira mensagem de sucesso e devolve o payload estruturado."""

    if not emitir_popup:
        return None
    tipo = "success"
    payload = {
        "tipo": tipo,
        "titulo": titulo or _titulo_padrao(tipo, True),
        "mensagem": mensagem,
        "icone": _icone_padrao(tipo),
        "chave_popup": chave_popup,
        **opcoes,
    }
    return _enfileirar_mensagem_sessao(payload)


def mensagem_erro(
    mensagem: str = "Ocorreu um erro na requisição.",
    *,
    status_http: int = 400,
    chave_popup: str | None = None,
    titulo: str | None = None,
    emitir_popup: bool = True,
    **opcoes: Any,
) -> dict[str, Any] | None:
    """Enfileira mensagem de erro e devolve o payload estruturado."""

    if not emitir_popup:
        return None
    tipo = _tipo_padrao(status_http, False)
    payload = {
        "tipo": tipo,
        "titulo": titulo or _titulo_padrao(tipo, False),
        "mensagem": mensagem,
        "icone": _icone_padrao(tipo),
        "chave_popup": chave_popup,
        **opcoes,
    }
    return _enfileirar_mensagem_sessao(payload)


def resposta_api_sucesso(
    dados: Any = None,
    mensagem: str = "Operação realizada com sucesso.",
    status_http: int = 200,
    *,
    chave_popup: str | None = None,
    emitir_popup: bool | None = None,
    **opcoes: Any,
) -> tuple[Response, int]:
    """Retorna envelope JSON de sucesso padronizado: {status: success, message, data}."""

    resposta: dict[str, Any] = {"status": "success", "message": mensagem}
    if dados is not None:
        resposta["data"] = dados

    deve_emitir = emitir_popup if emitir_popup is not None else False
    if deve_emitir:
        mensagem_sucesso(
            mensagem,
            status_http=status_http,
            chave_popup=chave_popup,
            **opcoes,
        )

    return jsonify(resposta), status_http


def resposta_api_erro(
    mensagem: str = "Ocorreu um erro na requisição.",
    detalhes: Any = None,
    status_http: int = 400,
    *,
    acao: str | None = None,
    chave_popup: str | None = None,
    emitir_popup: bool | None = None,
    **opcoes: Any,
) -> tuple[Response, int]:
    """Retorna envelope JSON de erro padronizado: {status: error, message, details, action}."""

    resposta: dict[str, Any] = {"status": "error", "message": mensagem}
    if detalhes is not None:
        resposta["details"] = detalhes
    if acao is not None:
        resposta["action"] = acao

    deve_emitir = emitir_popup if emitir_popup is not None else False
    if deve_emitir:
        mensagem_erro(
            mensagem,
            status_http=status_http,
            chave_popup=chave_popup,
            **opcoes,
        )

    return jsonify(resposta), status_http


def resposta_json(payload: Any) -> Response:
    """Normaliza e serializa qualquer carga em resposta JSON padronizada."""

    if isinstance(payload, dict):
        if "status" not in payload:
            sucesso = not any(payload.get(k) for k in ("erro", "error"))
            payload["status"] = "success" if sucesso else "error"
        return jsonify(payload)
    return jsonify(payload)


def exigir_ajax(funcao: Callable[P, R]) -> Callable[P, R]:
    """Restringe a view a chamadas de script (`X-Requested-With` ou corpo JSON).

    Acesso direto pelo navegador recebe 404, para nao expor endpoints de API como paginas.
    """

    @wraps(funcao)
    def executar(*args: P.args, **kwargs: P.kwargs) -> R:
        chamada_script = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json
        )
        if not chamada_script:
            abort(404)
        return funcao(*args, **kwargs)

    return executar


__all__ = [
    "consumir_flashes",
    "enfileirar_toast",
    "exigir_ajax",
    "mensagem_erro",
    "mensagem_sucesso",
    "resposta_api_erro",
    "resposta_api_sucesso",
    "resposta_json",
]
