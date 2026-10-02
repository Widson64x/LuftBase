"""Persistencia explicita e transacional da trilha de auditoria: tb_logs -> tb_logevento -> tb_logdetalhe."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import insert, select, update

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroAuditoria
from luftbase.observabilidade.modelos import EventoAcessoHttp, EventoDominio
from luftbase.observabilidade.sanitizacao import serializar_dados_seguro
from luftbase.persistencia.core import Log, LogDetalhe, LogEvento


class RepositorioAuditoria:
    """Grava logs (rotas), logevento (acoes) e logdetalhe (deltas) amarrados pelo id_log."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def registrar_acesso(self, id_sistema: int, evento: EventoAcessoHttp) -> int:
        """Persiste a resposta HTTP em tb_logs e vincula eventos e detalhes pendentes pelo id_log."""

        declaracao = (
            insert(Log)
            .values(
                id_sistema=id_sistema,
                codigo_usuario=evento.codigo_usuario,
                login_usuario=_limitar(evento.login_usuario, 100),
                codigo_grupo=evento.codigo_grupo,
                nome_grupo=_limitar(evento.nome_grupo, 100),
                rota_acessada=_limitar(evento.rota, 500) or "/",
                metodo_http=_limitar(evento.metodo, 10) or "GET",
                ip_origem=_limitar(evento.ip_origem, 50),
                user_agent=_limitar(evento.user_agent, 500),
                permissao_exigida=_limitar(evento.permissao_exigida, 180),
                acesso_permitido=evento.acesso_permitido,
                parametros_requisicao=evento.parametros,
                resposta_acao=f"Status HTTP: {evento.status_http}",
                id_correlacao=_limitar(evento.id_correlacao, 64) or "sem-correlacao",
                duracao_ms=max(evento.duracao_ms, 0),
                status_http=evento.status_http,
            )
            .returning(Log.id_log)
        )
        try:
            with self._banco.unidade_trabalho() as sessao:
                id_log = int(sessao.execute(declaracao).scalar_one())
                # Vincula eventos pendentes com a mesma correlacao
                sessao.execute(
                    update(LogEvento)
                    .where(
                        LogEvento.id_sistema == id_sistema,
                        LogEvento.id_correlacao == evento.id_correlacao,
                        LogEvento.id_log.is_(None),
                    )
                    .values(id_log=id_log)
                )
                # Vincula detalhes pendentes filhos desses eventos
                sessao.execute(
                    update(LogDetalhe)
                    .where(
                        LogDetalhe.id_logevento.in_(
                            select(LogEvento.id_logevento).where(LogEvento.id_log == id_log)
                        ),
                        LogDetalhe.id_log.is_(None),
                    )
                    .values(id_log=id_log)
                )
                return id_log
        except Exception as erro:
            raise ErroAuditoria("Nao foi possivel registrar a auditoria HTTP.") from erro

    def registrar_evento(self, id_sistema: int, evento: EventoDominio) -> int:
        """Persiste o evento em tb_logevento e seu detalhe em tb_logdetalhe na mesma transacao."""

        id_log = evento.id_log if evento.id_log is not None else evento.id_logacesso
        declaracao = (
            insert(LogEvento)
            .values(
                id_sistema=id_sistema,
                id_log=id_log,
                codigo_usuario=evento.codigo_usuario,
                login_usuario=_limitar(evento.login_usuario, 100),
                codigo_grupo=evento.codigo_grupo,
                nome_grupo=_limitar(evento.nome_grupo, 100),
                acao=_limitar(evento.acao, 80) or "REGISTRAR",
                recurso=_limitar(evento.recurso, 150) or "SISTEMA",
                id_recurso=_limitar(evento.id_recurso, 150),
                descricao=_limitar(evento.descricao, 1000) or "Evento sem descricao.",
                ip_origem=_limitar(evento.ip_origem, 50),
                user_agent=_limitar(evento.user_agent, 500),
                severidade=evento.severidade.value,
                traceback=evento.traceback,
                id_correlacao=_limitar(evento.id_correlacao, 64),
            )
            .returning(LogEvento.id_logevento)
        )
        try:
            with self._banco.unidade_trabalho() as sessao:
                id_logevento = int(sessao.execute(declaracao).scalar_one())
                if evento.dados_anteriores is not None or evento.dados_novos is not None:
                    sessao.execute(
                        insert(LogDetalhe).values(
                            id_log=id_log,
                            id_logevento=id_logevento,
                            tipo_alteracao=_tipo_alteracao(
                                evento.dados_anteriores,
                                evento.dados_novos,
                            ),
                            campos_alterados_json=serializar_dados_seguro(
                                _campos_alterados(
                                    evento.dados_anteriores,
                                    evento.dados_novos,
                                )
                            ),
                            dados_anteriores_json=_serializar_opcional(evento.dados_anteriores),
                            dados_novos_json=_serializar_opcional(evento.dados_novos),
                        )
                    )
                return id_logevento
        except Exception as erro:
            raise ErroAuditoria("Nao foi possivel registrar o evento de auditoria.") from erro

    def registrar_detalhe(self, id_sistema: int, evento: EventoDominio) -> int:
        """Alias para registrar_evento para manter compatibilidade total."""

        return self.registrar_evento(id_sistema, evento)


def _limitar(valor: str | None, tamanho: int) -> str | None:
    if valor is None:
        return None
    return valor.strip()[:tamanho] or None


def _serializar_opcional(valor: object | None) -> str | None:
    return None if valor is None else serializar_dados_seguro(valor)


def _tipo_alteracao(anterior: object | None, novo: object | None) -> str:
    if anterior is None:
        return "CRIACAO"
    if novo is None:
        return "EXCLUSAO"
    if isinstance(anterior, Mapping) and isinstance(novo, Mapping):
        return "ALTERACAO"
    return "SUBSTITUICAO"


def _campos_alterados(anterior: object | None, novo: object | None) -> list[str]:
    """Lista caminhos alterados sem serializar valores potencialmente sensiveis."""

    if not isinstance(anterior, Mapping) or not isinstance(novo, Mapping):
        return ["*"]

    campos: list[str] = []
    chaves = sorted(set(anterior) | set(novo))
    for chave in chaves:
        str_chave = str(chave)
        if chave not in anterior:
            campos.append(f"+{str_chave}")
        elif chave not in novo:
            campos.append(f"-{str_chave}")
        elif anterior[chave] != novo[chave]:
            campos.append(str_chave)
    return campos or ["*"]
