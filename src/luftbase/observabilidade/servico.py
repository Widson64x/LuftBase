"""Casos de uso que integram a trilha estruturada e os logs fisicos.

tb_logacesso > tb_logdetalhe > tb_logs, alem dos arquivos de log (o da plataforma e o da aplicacao).
"""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Protocol

from luftbase.nucleo.excecoes import ErroAuditoria
from luftbase.observabilidade.arquivo_fisico import (
    NOME_LOG_APLICACAO,
    LoggerFisicoAuditoria,
    ler_log,
    listar_arquivos_log,
)
from luftbase.observabilidade.modelos import (
    EventoAcessoHttp,
    EventoDominio,
    SeveridadeAuditoria,
)

# Fontes de log fisico que o painel sabe mostrar: id -> rotulo.
FONTES_LOGS_FISICOS: dict[str, str] = {"luftbase": "LuftBase", "aplicacao": "Aplicação"}


class PersistenciaAuditoria(Protocol):
    """Fronteira substituivel da persistencia de auditoria."""

    def registrar_acesso(self, id_sistema: int, evento: EventoAcessoHttp) -> int:
        """Persiste um acesso HTTP."""

    def registrar_evento(self, id_sistema: int, evento: EventoDominio) -> int:
        """Persiste um evento de dominio."""


class ServicoAuditoria:
    """Orquestra as tabelas encadeadas e os logs fisicos locais."""

    def __init__(
        self,
        id_sistema: int,
        repositorio: PersistenciaAuditoria,
        *,
        logger_fisico: LoggerFisicoAuditoria | None = None,
        arquivo_log_aplicacao: str = NOME_LOG_APLICACAO,
    ) -> None:
        self._id_sistema = id_sistema
        self._repositorio = repositorio
        self._logger_fisico = logger_fisico
        self._arquivo_log_aplicacao = arquivo_log_aplicacao

    @property
    def habilitada(self) -> bool:
        """Permite gravacao quando o id_sistema esta definido (inclusive sistema 0)."""

        return self._id_sistema is not None and self._id_sistema >= 0

    @property
    def logger_fisico(self) -> LoggerFisicoAuditoria | None:
        """Acesso direto ao logger fisico de auditoria."""

        return self._logger_fisico

    def registrar_acesso(self, evento: EventoAcessoHttp) -> int | None:
        """Registra a requisicao HTTP em tb_logacesso.

        As rotas ficam so no banco (tela "Rotas HTTP"): o arquivo de log fisico guarda mensagens do que
        o LuftBase fez, nao uma linha por requisicao.
        """

        if not self.habilitada:
            return None
        return self._repositorio.registrar_acesso(self._id_sistema, evento)

    def _enriquecer_evento(self, evento: EventoDominio) -> EventoDominio:
        """Completa campos de contexto (usuario, grupo, correlacao) quando ausentes."""
        from flask import g, has_request_context
        from flask_login import current_user

        from luftbase.identidade.modelos import UsuarioAutenticado

        codigo_usuario = evento.codigo_usuario
        login_usuario = evento.login_usuario
        codigo_grupo = evento.codigo_grupo
        nome_grupo = evento.nome_grupo
        id_correlacao = evento.id_correlacao
        id_log = evento.id_log if evento.id_log is not None else evento.id_logacesso

        if has_request_context():
            if id_correlacao is None:
                id_correlacao = getattr(g, "luftbase_id_correlacao", None)
            if id_log is None:
                id_log = getattr(g, "luftbase_id_log", None)
            try:
                usuario = current_user._get_current_object()
                if isinstance(usuario, UsuarioAutenticado):
                    if codigo_usuario is None:
                        codigo_usuario = usuario.id_usuario
                    if login_usuario is None:
                        login_usuario = usuario.login
                    if codigo_grupo is None:
                        codigo_grupo = usuario.id_grupo
                    if nome_grupo is None:
                        nome_grupo = usuario.nome_grupo
            except Exception:
                pass

        return EventoDominio(
            acao=evento.acao,
            recurso=evento.recurso,
            descricao=evento.descricao,
            id_recurso=evento.id_recurso,
            dados_anteriores=evento.dados_anteriores,
            dados_novos=evento.dados_novos,
            severidade=evento.severidade,
            codigo_usuario=codigo_usuario,
            login_usuario=login_usuario,
            codigo_grupo=codigo_grupo,
            nome_grupo=nome_grupo,
            ip_origem=evento.ip_origem,
            user_agent=evento.user_agent,
            id_correlacao=id_correlacao,
            id_log=id_log,
            id_logacesso=id_log,
            traceback=evento.traceback,
        )

    def registrar_evento(self, evento: EventoDominio) -> int:
        """Registra o evento no banco (tb_logevento) e como mensagem no log fisico."""

        evento = self._enriquecer_evento(evento)

        if self._logger_fisico is not None:
            self._logger_fisico.registrar_evento(evento)

        if not self.habilitada:
            raise ErroAuditoria("A aplicacao nao possui sistema valido para auditoria.")
        return self._repositorio.registrar_evento(self._id_sistema, evento)

    def registrar_alteracao(
        self,
        recurso: str,
        id_recurso: str | int | None,
        acao: str,
        descricao: str,
        dados_anteriores: object | None = None,
        dados_novos: object | None = None,
        severidade: SeveridadeAuditoria = SeveridadeAuditoria.BAIXA,
    ) -> int:
        """Registra operacao e seu delta de alteracao de dados com enriquecimento automatico."""

        evento = EventoDominio(
            acao=acao,
            recurso=recurso,
            id_recurso=str(id_recurso) if id_recurso is not None else None,
            descricao=descricao,
            dados_anteriores=dados_anteriores,
            dados_novos=dados_novos,
            severidade=severidade,
        )
        return self.registrar_evento(evento)

    # -------------------------------------------------------------------------
    # METODOS DE CONVENIENCIA (LOG FISICO + TB_LOGDETALHE OPCIONAL)
    # Com `salvar_banco` a mensagem sai pelo evento (que tambem vai ao log fisico), sem duplicar a linha.
    # -------------------------------------------------------------------------

    def info(
        self,
        mensagem: str,
        *,
        acao: str = "INFO",
        recurso: str = "SISTEMA",
        id_recurso: str | None = None,
        id_correlacao: str | None = None,
        codigo_usuario: int | None = None,
        login_usuario: str | None = None,
        codigo_grupo: int | None = None,
        nome_grupo: str | None = None,
        salvar_banco: bool = False,
    ) -> int | None:
        """Registra mensagem de nivel informativo."""

        if salvar_banco and self.habilitada:
            return self.registrar_evento(
                EventoDominio(
                    acao=acao,
                    recurso=recurso,
                    descricao=mensagem,
                    id_recurso=id_recurso,
                    severidade=SeveridadeAuditoria.BAIXA,
                    codigo_usuario=codigo_usuario,
                    login_usuario=login_usuario,
                    codigo_grupo=codigo_grupo,
                    nome_grupo=nome_grupo,
                    id_correlacao=id_correlacao,
                )
            )
        if self._logger_fisico is not None:
            self._logger_fisico.info(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        return None

    def aviso(
        self,
        mensagem: str,
        *,
        acao: str = "AVISO",
        recurso: str = "SISTEMA",
        id_recurso: str | None = None,
        id_correlacao: str | None = None,
        codigo_usuario: int | None = None,
        login_usuario: str | None = None,
        codigo_grupo: int | None = None,
        nome_grupo: str | None = None,
        salvar_banco: bool = False,
    ) -> int | None:
        """Registra mensagem de nivel aviso/warning."""

        if salvar_banco and self.habilitada:
            return self.registrar_evento(
                EventoDominio(
                    acao=acao,
                    recurso=recurso,
                    descricao=mensagem,
                    id_recurso=id_recurso,
                    severidade=SeveridadeAuditoria.MEDIA,
                    codigo_usuario=codigo_usuario,
                    login_usuario=login_usuario,
                    codigo_grupo=codigo_grupo,
                    nome_grupo=nome_grupo,
                    id_correlacao=id_correlacao,
                )
            )
        if self._logger_fisico is not None:
            self._logger_fisico.aviso(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        return None

    def erro(
        self,
        mensagem: str,
        erro: BaseException | None = None,
        *,
        acao: str = "ERRO",
        recurso: str = "SISTEMA",
        id_recurso: str | None = None,
        id_correlacao: str | None = None,
        codigo_usuario: int | None = None,
        login_usuario: str | None = None,
        codigo_grupo: int | None = None,
        nome_grupo: str | None = None,
        salvar_banco: bool = True,
    ) -> int | None:
        """Registra erro tecnico ou de negocio em todas as camadas cabiveis."""

        trace = "".join(traceback.format_exception(erro)) if erro else None
        if salvar_banco and self.habilitada:
            return self.registrar_evento(
                EventoDominio(
                    acao=acao,
                    recurso=recurso,
                    descricao=mensagem,
                    id_recurso=id_recurso,
                    severidade=SeveridadeAuditoria.ALTA,
                    codigo_usuario=codigo_usuario,
                    login_usuario=login_usuario,
                    codigo_grupo=codigo_grupo,
                    nome_grupo=nome_grupo,
                    id_correlacao=id_correlacao,
                    traceback=trace,
                )
            )
        if self._logger_fisico is not None:
            self._logger_fisico.erro(
                mensagem,
                erro=erro,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        return None

    def debug(
        self,
        mensagem: str,
        *,
        acao: str = "DEBUG",
        recurso: str = "SISTEMA",
        id_correlacao: str | None = None,
        login_usuario: str | None = None,
    ) -> None:
        """Registra mensagem de depuracao exclusiva no arquivo fisico."""

        if self._logger_fisico is not None:
            self._logger_fisico.debug(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )

    # -------------------------------------------------------------------------
    # LEITURA DOS LOGS FISICOS (tela "Logs fisicos")
    # -------------------------------------------------------------------------

    def _arquivo_da_fonte(self, fonte: str) -> tuple[Path, str] | None:
        """(pasta, nome do arquivo atual) de uma fonte conhecida; None se a fonte nao existe."""

        if self._logger_fisico is None or fonte not in FONTES_LOGS_FISICOS:
            return None
        nome = (
            self._logger_fisico.caminho_arquivo.name
            if fonte == "luftbase"
            else self._arquivo_log_aplicacao
        )
        return self._logger_fisico.diretorio, nome

    def listar_fontes_logs(self) -> list[dict[str, object]]:
        """As fontes de log fisico (LuftBase e Aplicacao) e se cada uma tem arquivo."""

        fontes: list[dict[str, object]] = []
        for identificador, rotulo in FONTES_LOGS_FISICOS.items():
            local = self._arquivo_da_fonte(identificador)
            arquivos = listar_arquivos_log(local[0], local[1]) if local else []
            fontes.append(
                {
                    "id": identificador,
                    "nome": rotulo,
                    "arquivo": local[1] if local else None,
                    "disponivel": bool(arquivos),
                }
            )
        return fontes

    def listar_arquivos_fisicos(self, fonte: str = "luftbase") -> list[dict[str, object]]:
        """Lista os arquivos (o atual e os rotacionados) de uma fonte de log."""

        local = self._arquivo_da_fonte(fonte)
        return listar_arquivos_log(local[0], local[1]) if local else []

    def obter_logs_fisicos(
        self,
        *,
        fonte: str = "luftbase",
        arquivo: str | None = None,
        limite: int = 200,
        nivel: str | None = None,
        termo: str | None = None,
    ) -> list[dict[str, str | None]]:
        """Le de forma limitada as mensagens recentes de um arquivo de log conhecido."""

        local = self._arquivo_da_fonte(fonte)
        if local is None:
            return []
        return [
            item.como_dict()
            for item in ler_log(
                local[0],
                local[1],
                arquivo=arquivo,
                limite=limite,
                nivel=nivel,
                termo=termo,
            )
        ]
