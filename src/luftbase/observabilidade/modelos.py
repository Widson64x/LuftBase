"""Eventos imutaveis das fronteiras de auditoria."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SeveridadeAuditoria(StrEnum):
    """Severidades persistidas pelo schema core."""

    BAIXA = "BAIXA"
    MEDIA = "MEDIA"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


@dataclass(frozen=True, slots=True)
class EventoAcessoHttp:
    """Retrato resumido de uma resposta HTTP, sem corpo ou cabecalhos."""

    rota: str
    metodo: str
    status_http: int
    duracao_ms: int
    id_correlacao: str
    codigo_usuario: int | None = None
    login_usuario: str | None = None
    codigo_grupo: int | None = None
    nome_grupo: str | None = None
    ip_origem: str | None = None
    user_agent: str | None = None
    permissao_exigida: str | None = None
    acesso_permitido: bool | None = None
    parametros: str | None = None


@dataclass(frozen=True, slots=True)
class EventoDominio:
    """Mudanca de negocio registrada explicitamente pelo servico que a executou."""

    acao: str
    recurso: str
    descricao: str
    id_recurso: str | None = None
    dados_anteriores: object | None = field(default=None, repr=False)
    dados_novos: object | None = field(default=None, repr=False)
    severidade: SeveridadeAuditoria = SeveridadeAuditoria.BAIXA
    codigo_usuario: int | None = None
    login_usuario: str | None = None
    codigo_grupo: int | None = None
    nome_grupo: str | None = None
    ip_origem: str | None = None
    user_agent: str | None = None
    id_correlacao: str | None = None
    id_log: int | None = None
    id_logacesso: int | None = None  # alias de compatibilidade
    traceback: str | None = None
