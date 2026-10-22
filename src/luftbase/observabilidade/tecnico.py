"""Logging tecnico estruturado sem configurar handlers globais."""

from __future__ import annotations

import logging

from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria
from luftbase.observabilidade.sanitizacao import resumir_excecao, serializar_dados_seguro

__all__ = ["LoggerTecnico", "resumir_excecao"]


class LoggerTecnico:
    """Usa o logger da aplicacao e nunca registra a mensagem bruta de excecoes."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        logger_fisico: LoggerFisicoAuditoria | None = None,
    ) -> None:
        self._logger = logger
        self._logger_fisico = logger_fisico

    def erro(
        self,
        evento: str,
        erro: BaseException,
        *,
        id_correlacao: str | None = None,
        dados: object | None = None,
    ) -> None:
        """Registra somente classe do erro e dados previamente sanitizados."""

        contexto = {
            "evento": evento,
            "tipo_erro": type(erro).__name__,
            "id_correlacao": id_correlacao,
            "dados": dados,
        }
        self._logger.error("luftbase %s", serializar_dados_seguro(contexto))
        if self._logger_fisico is not None:
            self._logger_fisico.registrar_tecnico(
                "ERROR",
                evento,
                id_correlacao=id_correlacao,
                dados=dados,
                tipo_erro=type(erro).__name__,
            )
