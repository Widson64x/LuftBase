"""Casos de uso que integram a trilha estruturada e o diagnostico local.

tb_logacesso > tb_logdetalhe > tb_logs, alem de arquivo fisico e raiz temporaria.
"""

from __future__ import annotations

import traceback
from typing import Protocol

from luftbase.nucleo.excecoes import ErroAuditoria
from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria
from luftbase.observabilidade.buffer_temp import BufferLogsTemporarios, RegistroLogTemp
from luftbase.observabilidade.modelos import (
    EventoAcessoHttp,
    EventoDominio,
    SeveridadeAuditoria,
)


class PersistenciaAuditoria(Protocol):
    """Fronteira substituivel da persistencia de auditoria."""

    def registrar_acesso(self, id_sistema: int, evento: EventoAcessoHttp) -> int:
        """Persiste um acesso HTTP."""

    def registrar_evento(self, id_sistema: int, evento: EventoDominio) -> int:
        """Persiste um evento de dominio."""


class ServicoAuditoria:
    """Orquestra as tabelas encadeadas e as duas fontes locais de diagnostico."""

    def __init__(
        self,
        id_sistema: int,
        repositorio: PersistenciaAuditoria,
        *,
        logger_fisico: LoggerFisicoAuditoria | None = None,
        buffer_temp: BufferLogsTemporarios | None = None,
    ) -> None:
        self._id_sistema = id_sistema
        self._repositorio = repositorio
        self._logger_fisico = logger_fisico
        self._buffer_temp = buffer_temp

    @property
    def habilitada(self) -> bool:
        """Permite gravacao quando o id_sistema esta definido (inclusive sistema 0)."""

        return self._id_sistema is not None and self._id_sistema >= 0

    @property
    def buffer_temp(self) -> BufferLogsTemporarios | None:
        """Acesso direto ao buffer de logs temporarios."""

        return self._buffer_temp

    @property
    def logger_fisico(self) -> LoggerFisicoAuditoria | None:
        """Acesso direto ao logger fisico de auditoria."""

        return self._logger_fisico

    def registrar_acesso(self, evento: EventoAcessoHttp) -> int | None:
        """Registra requisicao HTTP nas camadas: tb_logacesso, log fisico e logs temp."""

        # 1. Log Fisico .log
        if self._logger_fisico is not None:
            self._logger_fisico.registrar_acesso(evento)

        # 2. Logs Temp (Buffer em memoria)
        if self._buffer_temp is not None:
            if evento.status_http >= 500:
                nivel = "ERROR"
            elif evento.status_http >= 400:
                nivel = "WARNING"
            else:
                nivel = "INFO"
            msg = f"{evento.metodo} {evento.rota} ({evento.status_http}) - {evento.duracao_ms}ms"
            self._buffer_temp.adicionar(
                nivel,
                msg,
                id_correlacao=evento.id_correlacao,
                codigo_usuario=evento.codigo_usuario,
                login_usuario=evento.login_usuario,
                codigo_grupo=evento.codigo_grupo,
                nome_grupo=evento.nome_grupo,
                acao=f"HTTP_{evento.metodo}",
                recurso="ROTA",
                detalhes={
                    "ip": evento.ip_origem,
                    "user_agent": evento.user_agent,
                    "status": evento.status_http,
                },
            )

        # 3. tb_logs (Banco PostgreSQL)
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
        """Registra evento detalhado nas camadas: tb_logevento, log fisico e logs temp."""

        evento = self._enriquecer_evento(evento)

        # 1. Log Fisico .log
        if self._logger_fisico is not None:
            self._logger_fisico.registrar_evento(evento)

        # 2. Logs Temp (Buffer em memoria)
        if self._buffer_temp is not None:
            nivel_temp = (
                "ERROR"
                if evento.severidade in {SeveridadeAuditoria.ALTA, SeveridadeAuditoria.CRITICA}
                else "INFO"
            )
            self._buffer_temp.adicionar(
                nivel_temp,
                evento.descricao,
                id_correlacao=evento.id_correlacao,
                codigo_usuario=evento.codigo_usuario,
                login_usuario=evento.login_usuario,
                codigo_grupo=evento.codigo_grupo,
                nome_grupo=evento.nome_grupo,
                acao=evento.acao,
                recurso=evento.recurso,
                detalhes={
                    "id_recurso": evento.id_recurso,
                    "severidade": evento.severidade.value,
                },
            )

        # 3. tb_logevento e tb_logdetalhe (Banco PostgreSQL)
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
    # METODOS DE CONVENIENCIA (LOG FISICO + LOGS TEMP + TB_LOGDETALHE OPCIONAL)
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

        if self._logger_fisico is not None:
            self._logger_fisico.info(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        if self._buffer_temp is not None:
            self._buffer_temp.adicionar(
                "INFO",
                mensagem,
                id_correlacao=id_correlacao,
                codigo_usuario=codigo_usuario,
                login_usuario=login_usuario,
                codigo_grupo=codigo_grupo,
                nome_grupo=nome_grupo,
                acao=acao,
                recurso=recurso,
            )
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

        if self._logger_fisico is not None:
            self._logger_fisico.aviso(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        if self._buffer_temp is not None:
            self._buffer_temp.adicionar(
                "WARNING",
                mensagem,
                id_correlacao=id_correlacao,
                codigo_usuario=codigo_usuario,
                login_usuario=login_usuario,
                codigo_grupo=codigo_grupo,
                nome_grupo=nome_grupo,
                acao=acao,
                recurso=recurso,
            )
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
        if self._logger_fisico is not None:
            self._logger_fisico.erro(
                mensagem,
                erro=erro,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        if self._buffer_temp is not None:
            self._buffer_temp.adicionar(
                "ERROR",
                f"{mensagem} ({type(erro).__name__})" if erro else mensagem,
                id_correlacao=id_correlacao,
                codigo_usuario=codigo_usuario,
                login_usuario=login_usuario,
                codigo_grupo=codigo_grupo,
                nome_grupo=nome_grupo,
                acao=acao,
                recurso=recurso,
                detalhes={"traceback": trace} if trace else None,
            )
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
        """Registra mensagem de depuracao exclusiva no arquivo fisico e logs temp."""

        if self._logger_fisico is not None:
            self._logger_fisico.debug(
                mensagem,
                correlacao=id_correlacao,
                login=login_usuario,
                acao=acao,
                recurso=recurso,
            )
        if self._buffer_temp is not None:
            self._buffer_temp.adicionar(
                "DEBUG",
                mensagem,
                id_correlacao=id_correlacao,
                login_usuario=login_usuario,
                acao=acao,
                recurso=recurso,
            )

    def obter_logs_temporarios(
        self,
        *,
        limite: int = 100,
        nivel: str | None = None,
        termo: str | None = None,
        codigo_usuario: int | None = None,
        codigo_grupo: int | None = None,
    ) -> list[RegistroLogTemp]:
        """Consulta os logs temporarios em memoria."""

        if self._buffer_temp is None:
            return []
        return self._buffer_temp.listar(
            limite=limite,
            nivel=nivel,
            termo=termo,
            codigo_usuario=codigo_usuario,
            codigo_grupo=codigo_grupo,
        )

    def limpar_logs_temporarios(self) -> None:
        """Limpa os logs temporarios em memoria."""

        if self._buffer_temp is not None:
            self._buffer_temp.limpar()

    def listar_arquivos_fisicos(self) -> list[dict[str, object]]:
        """Lista os arquivos rotativos pertencentes a esta aplicacao."""

        if self._logger_fisico is None:
            return []
        return self._logger_fisico.listar_arquivos()

    def obter_logs_fisicos(
        self,
        *,
        arquivo: str | None = None,
        limite: int = 200,
        nivel: str | None = None,
        termo: str | None = None,
    ) -> list[dict[str, str | None]]:
        """Le de forma limitada as linhas recentes de um arquivo fisico conhecido."""

        if self._logger_fisico is None:
            return []
        return [
            item.como_dict()
            for item in self._logger_fisico.ler_recentes(
                arquivo=arquivo,
                limite=limite,
                nivel=nivel,
                termo=termo,
            )
        ]

    def nome_arquivo_temporario(self) -> str | None:
        """Informa apenas o nome seguro do arquivo raiz do processo atual."""

        if self._buffer_temp is None or self._buffer_temp.caminho_arquivo is None:
            return None
        return self._buffer_temp.caminho_arquivo.name
