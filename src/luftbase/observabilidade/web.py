"""Hooks Flask de correlacao, metricas e auditoria HTTP."""

from __future__ import annotations

import re
import uuid
from time import perf_counter
from typing import Any

from flask import Flask, Response, g, has_request_context, request
from flask_login import current_user

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.observabilidade.metricas import RegistroMetricas
from luftbase.observabilidade.modelos import (
    EventoAcessoHttp,
    EventoDominio,
    SeveridadeAuditoria,
)
from luftbase.observabilidade.sanitizacao import serializar_dados_seguro
from luftbase.observabilidade.servico import ServicoAuditoria
from luftbase.observabilidade.tecnico import LoggerTecnico

_PADRAO_CORRELACAO = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_ROTAS_IGNORADAS_PADRAO = frozenset(
    {
        "/_luftbase/mensagens",
        "/_luftbase/notificacoes/contagem",
        "/_luftbase/saude",
        "/_luftbase/prontidao",
        "/_luftbase/metricas",
        "/favicon.ico",
    }
)
_PREFIXOS_IGNORADOS_PADRAO = (
    "/_luftbase/static/",
    "/static/",
    "/Static/",
)


def obter_id_correlacao() -> str | None:
    """Devolve o identificador da requisicao atual, quando existente."""

    if not has_request_context():
        return None
    valor = getattr(g, "luftbase_id_correlacao", None)
    return valor if isinstance(valor, str) else None


def ignorar_auditoria_requisicao() -> None:
    """Suprime o registro de auditoria HTTP para a requisicao atual."""

    if has_request_context():
        g.luftbase_ignorar_auditoria = True


def sem_log(view_func: Any) -> Any:
    """Decorator de rota que impede o registro em tb_logs."""

    from functools import wraps

    @wraps(view_func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        ignorar_auditoria_requisicao()
        return view_func(*args, **kwargs)

    return wrapper


ignorar_auditoria = sem_log


def marcar_decisao_autorizacao(chave: str, permitido: bool) -> None:
    """Compartilha com a auditoria a decisao tomada pelo decorator."""

    if has_request_context():
        g.luftbase_permissao_exigida = chave
        g.luftbase_acesso_permitido = permitido


class IntegracaoObservabilidadeFlask:
    """Instala hooks pertencentes somente a uma instancia Flask."""

    def __init__(
        self,
        auditoria: ServicoAuditoria,
        metricas: RegistroMetricas,
        logger: LoggerTecnico,
    ) -> None:
        self._auditoria = auditoria
        self._metricas = metricas
        self._logger = logger

    def instalar(self, app: Flask) -> None:
        """Registra hooks sem listeners globais ou acesso externo antecipado."""

        app.before_request(self._iniciar_requisicao)
        app.after_request(self._finalizar_requisicao)

    def _iniciar_requisicao(self) -> None:
        informado = request.headers.get("X-Correlation-ID", "").strip()
        g.luftbase_id_correlacao = (
            informado if _PADRAO_CORRELACAO.fullmatch(informado) else uuid.uuid4().hex
        )
        g.luftbase_inicio_requisicao = perf_counter()

    def _finalizar_requisicao(self, resposta: Response) -> Response:
        inicio = getattr(g, "luftbase_inicio_requisicao", perf_counter())
        duracao_ms = max(round((perf_counter() - inicio) * 1_000), 0)
        id_correlacao = obter_id_correlacao() or uuid.uuid4().hex
        resposta.headers["X-Correlation-ID"] = id_correlacao
        self._metricas.registrar_requisicao(request.method, resposta.status_code, duracao_ms)

        if (
            getattr(g, "luftbase_ignorar_auditoria", False)
            or request.path in _ROTAS_IGNORADAS_PADRAO
            or request.path.startswith(_PREFIXOS_IGNORADOS_PADRAO)
            or not self._auditoria.habilitada
        ):
            return resposta
        try:
            id_log = self._auditoria.registrar_acesso(
                self._montar_evento_acesso(
                    resposta.status_code,
                    duracao_ms,
                    id_correlacao,
                )
            )
            g.luftbase_id_log = id_log
            g.luftbase_id_log_acesso = id_log
        except Exception as erro:
            self._metricas.registrar_falha_auditoria()
            self._logger.erro(
                "falha_auditoria_http",
                erro,
                id_correlacao=id_correlacao,
            )
        return resposta

    @staticmethod
    def _montar_evento_acesso(
        status_http: int,
        duracao_ms: int,
        id_correlacao: str,
    ) -> EventoAcessoHttp:
        usuario = current_user._get_current_object()
        identidade = usuario if isinstance(usuario, UsuarioAutenticado) else None
        regra = request.url_rule.rule if request.url_rule is not None else request.path
        parametros = serializar_dados_seguro({"query": request.args.to_dict(flat=False)})
        user_agent = request.user_agent.string if request.user_agent else None
        return EventoAcessoHttp(
            rota=regra,
            metodo=request.method,
            status_http=status_http,
            duracao_ms=duracao_ms,
            id_correlacao=id_correlacao,
            codigo_usuario=identidade.id_usuario if identidade else None,
            login_usuario=identidade.login if identidade else None,
            codigo_grupo=identidade.id_grupo if identidade else None,
            nome_grupo=identidade.nome_grupo if identidade else None,
            ip_origem=request.remote_addr,
            user_agent=user_agent[:500] if user_agent else None,
            permissao_exigida=getattr(g, "luftbase_permissao_exigida", None),
            acesso_permitido=getattr(g, "luftbase_acesso_permitido", None),
            parametros=parametros,
        )


def registrar_evento_auditoria(
    *,
    acao: str,
    recurso: str,
    descricao: str,
    id_recurso: str | None = None,
    dados_anteriores: object | None = None,
    dados_novos: object | None = None,
    severidade: SeveridadeAuditoria = SeveridadeAuditoria.BAIXA,
    id_log: int | None = None,
    id_logacesso: int | None = None,
    traceback: str | None = None,
) -> int:
    """Registra uma mudanca de dominio usando a identidade e correlacao atuais."""

    from luftbase.plataforma import obter_luftbase

    identidade: UsuarioAutenticado | None = None
    ip_origem: str | None = None
    user_agent: str | None = None
    id_log_contextual = id_log if id_log is not None else id_logacesso
    if has_request_context():
        usuario = current_user._get_current_object()
        identidade = usuario if isinstance(usuario, UsuarioAutenticado) else None
        ip_origem = request.remote_addr
        if request.user_agent:
            user_agent = request.user_agent.string[:500]
        if id_log_contextual is None:
            id_log_contextual = getattr(g, "luftbase_id_log", getattr(g, "luftbase_id_log_acesso", None))

    evento = EventoDominio(
        acao=acao,
        recurso=recurso,
        descricao=descricao,
        id_recurso=id_recurso,
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        severidade=severidade,
        codigo_usuario=identidade.id_usuario if identidade else None,
        login_usuario=identidade.login if identidade else None,
        codigo_grupo=identidade.id_grupo if identidade else None,
        nome_grupo=identidade.nome_grupo if identidade else None,
        ip_origem=ip_origem,
        user_agent=user_agent,
        id_correlacao=obter_id_correlacao(),
        id_log=id_log_contextual,
        id_logacesso=id_log_contextual,
        traceback=traceback,
    )
    return obter_luftbase().auditoria.registrar_evento(evento)


def registrar_alteracao_auditoria(
    *,
    recurso: str,
    id_recurso: str | int | None,
    acao: str,
    descricao: str,
    dados_anteriores: object | None = None,
    dados_novos: object | None = None,
    severidade: SeveridadeAuditoria = SeveridadeAuditoria.BAIXA,
) -> int:
    """Registra uma alteracao de dados antes -> depois com contexto automatico."""

    return registrar_evento_auditoria(
        acao=acao,
        recurso=recurso,
        descricao=descricao,
        id_recurso=str(id_recurso) if id_recurso is not None else None,
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        severidade=severidade,
    )


def contexto_observabilidade() -> dict[str, Any]:
    """Expõe somente a correlacao atual para templates de erro e suporte."""

    return {"id_correlacao": obter_id_correlacao()}


__all__ = [
    "IntegracaoObservabilidadeFlask",
    "contexto_observabilidade",
    "ignorar_auditoria",
    "ignorar_auditoria_requisicao",
    "marcar_decisao_autorizacao",
    "obter_id_correlacao",
    "registrar_alteracao_auditoria",
    "registrar_evento_auditoria",
    "sem_log",
]
