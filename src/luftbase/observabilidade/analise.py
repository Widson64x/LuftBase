"""Consultas analiticas, paginadas e somente leitura da auditoria persistente."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.orm import Session

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.persistencia.core import Log, LogDetalhe, LogEvento, Sistema

# Aliases de compatibilidade para evitar quebras em codigos legados
LogAcesso = Log
LogAlteracao = LogDetalhe


@dataclass(frozen=True, slots=True)
class FiltroAuditoria:
    """Recorte validado usado por todas as consultas do painel."""

    inicio: datetime
    fim: datetime
    id_sistema: int | None = None
    codigo_usuario: int | None = None
    codigo_grupo: int | None = None
    termo: str | None = None
    resultado_http: str | None = None
    severidade: str | None = None


@dataclass(frozen=True, slots=True)
class PaginaAuditoria:
    """Pagina limitada para impedir consultas sem fronteira."""

    numero: int = 1
    tamanho: int = 50

    @property
    def deslocamento(self) -> int:
        return (self.numero - 1) * self.tamanho


class ServicoAnaliseAuditoria:
    """Produz indicadores e linhas da auditoria sem alterar o Core."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def obter_resumo(self, filtro: FiltroAuditoria) -> dict[str, Any]:
        """Consolida KPIs, serie temporal e rankings do recorte."""

        condicoes_acesso = self._condicoes_acesso(filtro)
        condicoes_detalhe = self._condicoes_detalhe(filtro)
        with self._banco.leitura() as sessao:
            indicadores = sessao.execute(
                select(
                    func.count(Log.id_log),
                    func.count(func.distinct(Log.codigo_usuario)).filter(
                        Log.codigo_usuario.is_not(None)
                    ),
                    func.count(Log.id_log).filter(Log.status_http >= 500),
                    func.count(Log.id_log).filter(
                        and_(Log.status_http >= 400, Log.status_http < 500)
                    ),
                    func.count(Log.id_log).filter(
                        Log.acesso_permitido.is_(False)
                    ),
                    func.coalesce(func.avg(Log.duracao_ms), 0),
                ).where(*condicoes_acesso)
            ).one()
            detalhes = sessao.execute(
                select(
                    func.count(LogEvento.id_logevento),
                    func.count(LogEvento.id_logevento).filter(
                        LogEvento.severidade.in_(("ALTA", "CRITICA"))
                    ),
                ).where(*condicoes_detalhe)
            ).one()
            alteracoes = sessao.scalar(
                select(func.count(LogDetalhe.id_logdetalhe))
                .join(LogEvento, LogEvento.id_logevento == LogDetalhe.id_logevento)
                .where(*condicoes_detalhe)
            )
            serie = self._obter_serie(sessao, filtro, condicoes_acesso)
            rotas = self._ranking(
                sessao,
                Log.rota_acessada,
                condicoes_acesso,
                rotulo_nulo="Rota desconhecida",
            )
            usuarios = self._ranking(
                sessao,
                Log.login_usuario,
                condicoes_acesso,
                rotulo_nulo="Anonimo",
            )
            grupos = self._ranking(
                sessao,
                Log.nome_grupo,
                condicoes_acesso,
                rotulo_nulo="Sem grupo",
            )
            sistemas = self._ranking_sistemas(sessao, condicoes_acesso)

        total = int(indicadores[0] or 0)
        erros_servidor = int(indicadores[2] or 0)
        return {
            "indicadores": {
                "requisicoes": total,
                "usuarios": int(indicadores[1] or 0),
                "erros_servidor": erros_servidor,
                "erros_cliente": int(indicadores[3] or 0),
                "acessos_negados": int(indicadores[4] or 0),
                "duracao_media_ms": round(float(indicadores[5] or 0), 1),
                "taxa_erro": round((erros_servidor / total * 100) if total else 0, 2),
                "detalhes": int(detalhes[0] or 0),
                "detalhes_criticos": int(detalhes[1] or 0),
                "alteracoes": int(alteracoes or 0),
            },
            "serie": serie,
            "rankings": {
                "rotas": rotas,
                "usuarios": usuarios,
                "grupos": grupos,
                "sistemas": sistemas,
            },
        }

    def listar_acessos(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        """Lista requisicoes HTTP em ordem decrescente e com total separado."""

        condicoes = self._condicoes_acesso(filtro)
        declaracao = (
            select(
                Log.id_log,
                Log.data_hora,
                Log.id_sistema,
                Sistema.nome_sistema,
                Log.codigo_usuario,
                Log.login_usuario,
                Log.codigo_grupo,
                Log.nome_grupo,
                Log.metodo_http,
                Log.rota_acessada,
                Log.status_http,
                Log.duracao_ms,
                Log.acesso_permitido,
                Log.ip_origem,
                Log.id_correlacao,
            )
            .outerjoin(Sistema, Sistema.id_sistema == Log.id_sistema)
            .where(*condicoes)
            .order_by(desc(Log.data_hora), desc(Log.id_log))
            .offset(pagina.deslocamento)
            .limit(pagina.tamanho)
        )
        with self._banco.leitura() as sessao:
            total = sessao.scalar(select(func.count(Log.id_log)).where(*condicoes))
            linhas = sessao.execute(declaracao).all()

        return {
            "total": int(total or 0),
            "pagina": pagina.numero,
            "tamanho": pagina.tamanho,
            "itens": [
                {
                    "id": linha[0],
                    "id_log": linha[0],
                    "data_hora": _data_iso(linha[1]),
                    "sistema_id": linha[2],
                    "sistema": linha[3] or f"Sistema {linha[2]}",
                    "usuario_id": linha[4],
                    "usuario": linha[5] or "Anonimo",
                    "grupo_id": linha[6],
                    "grupo": linha[7] or "Sem grupo",
                    "metodo": linha[8],
                    "rota": linha[9],
                    "status": linha[10],
                    "duracao_ms": linha[11],
                    "acesso_permitido": linha[12],
                    "ip": linha[13],
                    "correlacao": linha[14],
                }
                for linha in linhas
            ],
        }

    def listar_detalhes(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        """Lista acoes, erros e detalhes persistidos em tb_logevento."""

        condicoes = self._condicoes_detalhe(filtro)
        declaracao = (
            select(
                LogEvento.id_logevento,
                LogEvento.data_hora,
                LogEvento.id_sistema,
                Sistema.nome_sistema,
                LogEvento.codigo_usuario,
                LogEvento.login_usuario,
                LogEvento.codigo_grupo,
                LogEvento.nome_grupo,
                LogEvento.acao,
                LogEvento.recurso,
                LogEvento.id_recurso,
                LogEvento.descricao,
                LogEvento.severidade,
                LogEvento.id_correlacao,
                LogEvento.id_log,
            )
            .join(Sistema, Sistema.id_sistema == LogEvento.id_sistema)
            .where(*condicoes)
            .order_by(desc(LogEvento.data_hora), desc(LogEvento.id_logevento))
            .offset(pagina.deslocamento)
            .limit(pagina.tamanho)
        )
        with self._banco.leitura() as sessao:
            total = sessao.scalar(select(func.count(LogEvento.id_logevento)).where(*condicoes))
            linhas = sessao.execute(declaracao).all()

        return {
            "total": int(total or 0),
            "pagina": pagina.numero,
            "tamanho": pagina.tamanho,
            "itens": [
                {
                    "id": linha[0],
                    "id_logevento": linha[0],
                    "id_log": linha[14],
                    "data_hora": _data_iso(linha[1]),
                    "sistema_id": linha[2],
                    "sistema": linha[3],
                    "usuario_id": linha[4],
                    "usuario": linha[5] or "Sistema",
                    "grupo_id": linha[6],
                    "grupo": linha[7] or "Sem grupo",
                    "acao": linha[8],
                    "recurso": linha[9],
                    "recurso_id": linha[10],
                    "descricao": linha[11],
                    "severidade": linha[12],
                    "correlacao": linha[13],
                }
                for linha in linhas
            ],
        }

    def listar_alteracoes(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        """Lista os retratos antes/depois associados aos detalhes auditados."""

        condicoes = self._condicoes_detalhe(filtro)
        declaracao = (
            select(
                LogDetalhe.id_logdetalhe,
                LogDetalhe.data_hora,
                LogEvento.id_sistema,
                Sistema.nome_sistema,
                LogEvento.codigo_usuario,
                LogEvento.login_usuario,
                LogEvento.codigo_grupo,
                LogEvento.nome_grupo,
                LogEvento.acao,
                LogEvento.recurso,
                LogEvento.id_recurso,
                LogDetalhe.tipo_alteracao,
                LogDetalhe.campos_alterados_json,
                LogEvento.id_correlacao,
                LogDetalhe.id_logevento,
                LogDetalhe.id_log,
            )
            .join(LogEvento, LogEvento.id_logevento == LogDetalhe.id_logevento)
            .join(Sistema, Sistema.id_sistema == LogEvento.id_sistema)
            .where(*condicoes)
            .order_by(desc(LogDetalhe.data_hora), desc(LogDetalhe.id_logdetalhe))
            .offset(pagina.deslocamento)
            .limit(pagina.tamanho)
        )
        with self._banco.leitura() as sessao:
            total = sessao.scalar(
                select(func.count(LogDetalhe.id_logdetalhe))
                .join(LogEvento, LogEvento.id_logevento == LogDetalhe.id_logevento)
                .where(*condicoes)
            )
            linhas = sessao.execute(declaracao).all()

        return {
            "total": int(total or 0),
            "pagina": pagina.numero,
            "tamanho": pagina.tamanho,
            "itens": [
                {
                    "id": linha[0],
                    "id_logdetalhe": linha[0],
                    "id_log": linha[15],
                    "data_hora": _data_iso(linha[1]),
                    "sistema_id": linha[2],
                    "sistema": linha[3],
                    "usuario_id": linha[4],
                    "usuario": linha[5] or "Sistema",
                    "grupo_id": linha[6],
                    "grupo": linha[7] or "Sem grupo",
                    "acao": linha[8],
                    "recurso": linha[9],
                    "recurso_id": linha[10],
                    "tipo_alteracao": linha[11],
                    "campos_alterados": linha[12],
                    "correlacao": linha[13],
                    "detalhe_id": linha[14],
                    "evento_id": linha[14],
                    "id_logevento": linha[14],
                }
                for linha in linhas
            ],
        }

    def obter_detalhe(
        self,
        tipo: str,
        identificador: int,
        *,
        incluir_sensiveis: bool,
        id_sistema: int | None = None,
    ) -> dict[str, Any] | None:
        """Carrega um registro isolado no escopo permitido e oculta payloads."""

        with self._banco.leitura() as sessao:
            if tipo in {"acesso", "log"}:
                consulta_acesso = select(Log).where(Log.id_log == identificador)
                if id_sistema is not None:
                    consulta_acesso = consulta_acesso.where(Log.id_sistema == id_sistema)
                registro = sessao.scalar(consulta_acesso)
                if registro is None:
                    return None
                resultado = {
                    "tipo": "acesso",
                    "id": registro.id_log,
                    "id_log": registro.id_log,
                    "data_hora": _data_iso(registro.data_hora),
                    "sistema_id": registro.id_sistema,
                    "usuario_id": registro.codigo_usuario,
                    "usuario": registro.login_usuario,
                    "grupo_id": registro.codigo_grupo,
                    "grupo": registro.nome_grupo,
                    "rota": registro.rota_acessada,
                    "metodo": registro.metodo_http,
                    "status": registro.status_http,
                    "duracao_ms": registro.duracao_ms,
                    "ip": registro.ip_origem,
                    "user_agent": registro.user_agent,
                    "permissao": registro.permissao_exigida,
                    "acesso_permitido": registro.acesso_permitido,
                    "correlacao": registro.id_correlacao,
                }
                resultado["parametros"] = (
                    registro.parametros_requisicao if incluir_sensiveis else None
                )
                resultado["resposta"] = registro.resposta_acao if incluir_sensiveis else None
                resultado["dados_sensiveis_ocultos"] = not incluir_sensiveis
                return resultado

            if tipo in {"detalhe", "evento"}:
                consulta_evento = select(LogEvento).where(
                    LogEvento.id_logevento == identificador
                )
                if id_sistema is not None:
                    consulta_evento = consulta_evento.where(LogEvento.id_sistema == id_sistema)
                registro_evento = sessao.scalar(consulta_evento)
                if registro_evento is None:
                    return None
                resultado_evento = {
                    "tipo": "detalhe",
                    "id": registro_evento.id_logevento,
                    "id_logevento": registro_evento.id_logevento,
                    "id_log": registro_evento.id_log,
                    "data_hora": _data_iso(registro_evento.data_hora),
                    "sistema_id": registro_evento.id_sistema,
                    "acesso_id": registro_evento.id_log,
                    "usuario_id": registro_evento.codigo_usuario,
                    "usuario": registro_evento.login_usuario,
                    "grupo_id": registro_evento.codigo_grupo,
                    "grupo": registro_evento.nome_grupo,
                    "acao": registro_evento.acao,
                    "recurso": registro_evento.recurso,
                    "recurso_id": registro_evento.id_recurso,
                    "descricao": registro_evento.descricao,
                    "severidade": registro_evento.severidade,
                    "ip": registro_evento.ip_origem,
                    "user_agent": registro_evento.user_agent,
                    "correlacao": registro_evento.id_correlacao,
                }
                alteracoes = sessao.scalars(
                    select(LogDetalhe)
                    .where(LogDetalhe.id_logevento == registro_evento.id_logevento)
                    .order_by(LogDetalhe.id_logdetalhe)
                ).all()
                resultado_evento.update(
                    {
                        "traceback": registro_evento.traceback if incluir_sensiveis else None,
                        "alteracoes": [
                            _alteracao_como_dict(item, incluir_sensiveis=incluir_sensiveis)
                            for item in alteracoes
                        ],
                        "dados_sensiveis_ocultos": not incluir_sensiveis,
                    }
                )
                return resultado_evento

            if tipo in {"alteracao", "detalhe_alteracao"}:
                consulta_alteracao = (
                    select(LogDetalhe, LogEvento)
                    .join(LogEvento, LogEvento.id_logevento == LogDetalhe.id_logevento)
                    .where(LogDetalhe.id_logdetalhe == identificador)
                )
                if id_sistema is not None:
                    consulta_alteracao = consulta_alteracao.where(
                        LogEvento.id_sistema == id_sistema
                    )
                linha = sessao.execute(consulta_alteracao).one_or_none()
                if linha is None:
                    return None
                alteracao, evento = linha
                return {
                    "tipo": "alteracao",
                    "id": alteracao.id_logdetalhe,
                    "id_logdetalhe": alteracao.id_logdetalhe,
                    "id_log": alteracao.id_log,
                    "detalhe_id": evento.id_logevento,
                    "evento_id": evento.id_logevento,
                    "acesso_id": alteracao.id_log,
                    "sistema_id": evento.id_sistema,
                    "usuario_id": evento.codigo_usuario,
                    "usuario": evento.login_usuario,
                    "grupo_id": evento.codigo_grupo,
                    "grupo": evento.nome_grupo,
                    "acao": evento.acao,
                    "recurso": evento.recurso,
                    "recurso_id": evento.id_recurso,
                    "correlacao": evento.id_correlacao,
                    **_alteracao_como_dict(
                        alteracao,
                        incluir_sensiveis=incluir_sensiveis,
                    ),
                    "dados_sensiveis_ocultos": not incluir_sensiveis,
                }
        return None

    def obter_opcoes(
        self,
        filtro: FiltroAuditoria,
        *,
        id_sistema_escopo: int | None = None,
    ) -> dict[str, Any]:
        """Retorna opcoes observadas no periodo para filtros do painel.

        `id_sistema_escopo` limita a lista de sistemas ao da aplicacao que consulta: so o escopo
        global (sistema 0, `None`) enxerga os demais sistemas.
        """

        condicoes = self._condicoes_acesso(filtro, ignorar_identidade=True)
        consulta_sistemas = select(Sistema.id_sistema, Sistema.nome_sistema).where(
            Sistema.ativo.is_(True)
        )
        if id_sistema_escopo is not None:
            consulta_sistemas = consulta_sistemas.where(Sistema.id_sistema == id_sistema_escopo)
        with self._banco.leitura() as sessao:
            sistemas = sessao.execute(consulta_sistemas.order_by(Sistema.nome_sistema)).all()
            usuarios = sessao.execute(
                select(Log.codigo_usuario, Log.login_usuario)
                .where(
                    *condicoes,
                    Log.codigo_usuario.is_not(None),
                )
                .distinct()
                .order_by(Log.login_usuario)
                .limit(500)
            ).all()
            grupos = sessao.execute(
                select(Log.codigo_grupo, Log.nome_grupo)
                .where(
                    *condicoes,
                    Log.codigo_grupo.is_not(None),
                )
                .distinct()
                .order_by(Log.nome_grupo)
                .limit(200)
            ).all()
        return {
            "sistemas": [{"id": linha[0], "nome": linha[1]} for linha in sistemas],
            "usuarios": [
                {"id": linha[0], "nome": linha[1] or f"Usuario {linha[0]}"} for linha in usuarios
            ],
            "grupos": [
                {"id": linha[0], "nome": linha[1] or f"Grupo {linha[0]}"} for linha in grupos
            ],
        }

    @staticmethod
    def _condicoes_acesso(
        filtro: FiltroAuditoria,
        *,
        ignorar_identidade: bool = False,
    ) -> list[Any]:
        condicoes: list[Any] = [
            Log.data_hora >= filtro.inicio,
            Log.data_hora <= filtro.fim,
        ]
        if filtro.id_sistema is not None:
            condicoes.append(Log.id_sistema == filtro.id_sistema)
        if not ignorar_identidade and filtro.codigo_usuario is not None:
            condicoes.append(Log.codigo_usuario == filtro.codigo_usuario)
        if not ignorar_identidade and filtro.codigo_grupo is not None:
            condicoes.append(Log.codigo_grupo == filtro.codigo_grupo)
        if filtro.termo:
            termo = f"%{filtro.termo}%"
            condicoes.append(
                or_(
                    Log.login_usuario.ilike(termo),
                    Log.nome_grupo.ilike(termo),
                    Log.rota_acessada.ilike(termo),
                    Log.ip_origem.ilike(termo),
                    Log.id_correlacao.ilike(termo),
                    Log.permissao_exigida.ilike(termo),
                )
            )
        if filtro.resultado_http == "sucesso":
            condicoes.extend((Log.status_http >= 200, Log.status_http < 400))
        elif filtro.resultado_http == "cliente":
            condicoes.extend((Log.status_http >= 400, Log.status_http < 500))
        elif filtro.resultado_http == "servidor":
            condicoes.append(Log.status_http >= 500)
        elif filtro.resultado_http == "negado":
            condicoes.append(Log.acesso_permitido.is_(False))
        return condicoes

    @staticmethod
    def _condicoes_detalhe(filtro: FiltroAuditoria) -> list[Any]:
        condicoes: list[Any] = [
            LogEvento.data_hora >= filtro.inicio,
            LogEvento.data_hora <= filtro.fim,
        ]
        if filtro.id_sistema is not None:
            condicoes.append(LogEvento.id_sistema == filtro.id_sistema)
        if filtro.codigo_usuario is not None:
            condicoes.append(LogEvento.codigo_usuario == filtro.codigo_usuario)
        if filtro.codigo_grupo is not None:
            condicoes.append(LogEvento.codigo_grupo == filtro.codigo_grupo)
        if filtro.severidade:
            condicoes.append(LogEvento.severidade == filtro.severidade)
        if filtro.termo:
            termo = f"%{filtro.termo}%"
            condicoes.append(
                or_(
                    LogEvento.login_usuario.ilike(termo),
                    LogEvento.nome_grupo.ilike(termo),
                    LogEvento.acao.ilike(termo),
                    LogEvento.recurso.ilike(termo),
                    LogEvento.descricao.ilike(termo),
                    LogEvento.id_correlacao.ilike(termo),
                )
            )
        return condicoes

    @staticmethod
    def _obter_serie(
        sessao: Session,
        filtro: FiltroAuditoria,
        condicoes: list[Any],
    ) -> list[dict[str, Any]]:
        periodo = "hour" if (filtro.fim - filtro.inicio).days <= 2 else "day"
        intervalo = func.date_trunc(periodo, Log.data_hora).label("intervalo")
        linhas = sessao.execute(
            select(
                intervalo,
                func.count(Log.id_log),
                func.count(Log.id_log).filter(Log.status_http >= 500),
                func.count(Log.id_log).filter(Log.acesso_permitido.is_(False)),
            )
            .where(*condicoes)
            .group_by(intervalo)
            .order_by(intervalo)
        ).all()
        return [
            {
                "intervalo": _data_iso(linha[0]),
                "total": int(linha[1]),
                "erros": int(linha[2]),
                "negados": int(linha[3]),
            }
            for linha in linhas
        ]

    @staticmethod
    def _ranking(
        sessao: Session,
        coluna: Any,
        condicoes: list[Any],
        *,
        rotulo_nulo: str,
    ) -> list[dict[str, Any]]:
        rotulo = func.coalesce(coluna, rotulo_nulo).label("rotulo")
        linhas = sessao.execute(
            select(rotulo, func.count(Log.id_log).label("total"))
            .where(*condicoes)
            .group_by(rotulo)
            .order_by(desc("total"), rotulo)
            .limit(8)
        ).all()
        return [{"rotulo": linha[0], "total": int(linha[1])} for linha in linhas]

    @staticmethod
    def _ranking_sistemas(
        sessao: Session,
        condicoes: list[Any],
    ) -> list[dict[str, Any]]:
        rotulo = func.coalesce(Sistema.nome_sistema, "Sistema removido").label("rotulo")
        linhas = sessao.execute(
            select(rotulo, func.count(Log.id_log).label("total"))
            .select_from(Log)
            .outerjoin(Sistema, Sistema.id_sistema == Log.id_sistema)
            .where(*condicoes)
            .group_by(rotulo)
            .order_by(desc("total"), rotulo)
            .limit(8)
        ).all()
        return [{"rotulo": linha[0], "total": int(linha[1])} for linha in linhas]


def _data_iso(valor: datetime | None) -> str | None:
    return valor.isoformat(timespec="milliseconds") if valor else None


def _alteracao_como_dict(
    alteracao: LogDetalhe,
    *,
    incluir_sensiveis: bool,
) -> dict[str, Any]:
    return {
        "id": alteracao.id_logdetalhe,
        "id_logdetalhe": alteracao.id_logdetalhe,
        "id_log": alteracao.id_log,
        "id_logevento": alteracao.id_logevento,
        "data_hora": _data_iso(alteracao.data_hora),
        "tipo_alteracao": alteracao.tipo_alteracao,
        "campos_alterados": alteracao.campos_alterados_json,
        "dados_anteriores": (alteracao.dados_anteriores_json if incluir_sensiveis else None),
        "dados_novos": alteracao.dados_novos_json if incluir_sensiveis else None,
    }


__all__ = ["FiltroAuditoria", "PaginaAuditoria", "ServicoAnaliseAuditoria"]
