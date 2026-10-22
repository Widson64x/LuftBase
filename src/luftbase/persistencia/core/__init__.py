"""Modelos fixos das tabelas compartilhadas no schema ``core``."""

from luftbase.persistencia.core.alertas import Alerta, AlertaControle
from luftbase.persistencia.core.auditoria import (
    Log,
    LogAcesso,
    LogAlteracao,
    LogDetalhe,
    LogEvento,
)
from luftbase.persistencia.core.email_fila import EmailFila
from luftbase.persistencia.core.notificacoes import (
    Notificacao,
    NotificacaoLeitura,
    NotificacaoOculta,
)
from luftbase.persistencia.core.preferencias import ModoTema, RevisaoCache
from luftbase.persistencia.core.publicacoes import (
    NotaAtualizacaoItem,
    Publicacao,
    PublicacaoGrupo,
    PublicacaoImagem,
    PublicacaoLeitura,
    PublicacaoNotificacao,
)
from luftbase.persistencia.core.seguranca import (
    Modulo,
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    Sistema,
)
from luftbase.persistencia.core.sessoes import EventoSessao, Sessao
from luftbase.persistencia.core.sistemas import RepositorioSistemas
from luftbase.persistencia.core.usuario import Usuario

__all__ = [
    "Alerta",
    "AlertaControle",
    "EmailFila",
    "EventoSessao",
    "Log",
    "LogAcesso",
    "LogAlteracao",
    "LogDetalhe",
    "LogEvento",
    "Modulo",
    "ModoTema",
    "NotaAtualizacaoItem",
    "Notificacao",
    "NotificacaoLeitura",
    "NotificacaoOculta",
    "Permissao",
    "PermissaoGrupo",
    "PermissaoUsuario",
    "Publicacao",
    "PublicacaoGrupo",
    "PublicacaoImagem",
    "PublicacaoLeitura",
    "PublicacaoNotificacao",
    "RepositorioSistemas",
    "RevisaoCache",
    "Sessao",
    "Sistema",
    "Usuario",
]
