"""Logging tecnico estruturado sem configurar handlers globais."""

from __future__ import annotations

import logging
import os
import traceback

from luftbase.observabilidade.arquivo_fisico import LoggerFisicoAuditoria
from luftbase.observabilidade.buffer_temp import BufferLogsTemporarios
from luftbase.observabilidade.sanitizacao import serializar_dados_seguro


def resumir_excecao(erro: BaseException, *, quadros: int = 8) -> dict[str, object]:
    """Descreve ONDE e DE QUE TIPO foi uma excecao, sem nenhum valor (mensagem ou parametros).

    Mensagens de erro de banco costumam carregar dados e credenciais, entao nunca entram. Fica a
    cadeia de tipos (causa -> efeito) e as ultimas linhas da pilha (arquivo, linha e funcao),
    o suficiente para localizar o defeito num servico sem console.
    """

    cadeia: list[str] = []
    atual: BaseException | None = erro
    raiz: BaseException = erro
    while atual is not None and len(cadeia) < 6:
        cadeia.append(f"{type(atual).__module__}.{type(atual).__qualname__}")
        raiz = atual
        atual = atual.__cause__ or (None if atual.__suppress_context__ else atual.__context__)

    def linhas(excecao: BaseException) -> list[str]:
        pilha = traceback.extract_tb(excecao.__traceback__)[-quadros:]
        return [f"{os.path.basename(q.filename)}:{q.lineno} {q.name}" for q in pilha]

    resumo: dict[str, object] = {"cadeia": cadeia, "pilha": linhas(erro)}
    if raiz is not erro:
        # Onde o erro NASCEU (ex.: o driver do banco), distinto de quem o embrulhou.
        resumo["origem"] = linhas(raiz)
    return resumo


class LoggerTecnico:
    """Usa o logger da aplicacao e nunca registra a mensagem bruta de excecoes."""

    def __init__(
        self,
        logger: logging.Logger,
        *,
        logger_fisico: LoggerFisicoAuditoria | None = None,
        buffer_temp: BufferLogsTemporarios | None = None,
    ) -> None:
        self._logger = logger
        self._logger_fisico = logger_fisico
        self._buffer_temp = buffer_temp

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
        if self._buffer_temp is not None:
            self._buffer_temp.adicionar(
                "ERROR",
                evento,
                id_correlacao=id_correlacao,
                acao="ERRO_TECNICO",
                recurso="SISTEMA",
                detalhes={"tipo_erro": type(erro).__name__, "dados": dados},
            )
