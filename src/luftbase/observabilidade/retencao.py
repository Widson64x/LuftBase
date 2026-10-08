"""Retencao e arquivamento da trilha de auditoria e das sessoes.

Prazos (dias, ajustaveis por variavel de ambiente; os valores sao um ponto de partida, nao exigencia legal):

| Tabela                              | Variavel                   | Padrao |
|-------------------------------------|----------------------------|--------|
| `tb_logs` (acesso HTTP)             | `LUFT_RETENCAO_ACESSO_DIAS`  | 180    |
| `tb_sessao` (+ `tb_sessao_evento`)  | `LUFT_RETENCAO_SESSOES_DIAS` | 365    |
| `tb_logevento` (+ `tb_logdetalhe`)  | `LUFT_RETENCAO_EVENTOS_DIAS` | 730    |
| `tb_alerta` (so os resolvidos)      | `LUFT_RETENCAO_ALERTAS_DIAS` | 180    |

A trilha e encadeada (`tb_logs` -> `tb_logevento` -> `tb_logdetalhe`, todas com `ON DELETE CASCADE`). Como o acesso
HTTP vence antes dos eventos, antes de apagar um lote de `tb_logs` os eventos e detalhes que ainda estao no prazo sao
**desligados** do acesso (`id_log = NULL`), para o CASCADE nao levar embora a trilha de alteracao que deve ficar.

Antes de apagar, cada lote pode ser **arquivado** em CSV compactado (`--arquivar-em`). Se a gravacao do arquivo falhar,
nada e apagado. O padrao do comando e **simular**.
"""

from __future__ import annotations

import contextlib
import csv
import gzip
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.engine import Row

from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core.alertas import Alerta
from luftbase.persistencia.core.auditoria import Log, LogDetalhe, LogEvento
from luftbase.persistencia.core.sessoes import EventoSessao, Sessao

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.catalogo import CatalogoBancos

logger = logging.getLogger(__name__)

TAMANHO_LOTE_PADRAO = 1000
TABELAS_MEDIDAS = (
    "tb_logs",
    "tb_logevento",
    "tb_logdetalhe",
    "tb_sessao",
    "tb_sessao_evento",
    "tb_alerta",
    "tb_notificacao",
)


def _dias(variavel: str, padrao: int) -> int:
    try:
        valor = int(os.environ.get(variavel) or padrao)
    except ValueError:
        return padrao
    return max(valor, 1)


@dataclass(frozen=True, slots=True)
class Politica:
    """Quantos dias cada tabela guarda."""

    acesso_dias: int = 180
    sessoes_dias: int = 365
    eventos_dias: int = 730
    alertas_dias: int = 180

    @classmethod
    def de_ambiente(cls) -> Politica:
        return cls(
            acesso_dias=_dias("LUFT_RETENCAO_ACESSO_DIAS", 180),
            sessoes_dias=_dias("LUFT_RETENCAO_SESSOES_DIAS", 365),
            eventos_dias=_dias("LUFT_RETENCAO_EVENTOS_DIAS", 730),
            alertas_dias=_dias("LUFT_RETENCAO_ALERTAS_DIAS", 180),
        )

    def cortes(self, agora: datetime) -> dict[str, datetime]:
        return {
            "acesso": agora - timedelta(days=self.acesso_dias),
            "sessoes": agora - timedelta(days=self.sessoes_dias),
            "eventos": agora - timedelta(days=self.eventos_dias),
            "alertas": agora - timedelta(days=self.alertas_dias),
        }


@dataclass(slots=True)
class ResultadoTabela:
    tabela: str
    corte: datetime
    vencidas: int = 0
    apagadas: int = 0
    arquivadas: int = 0
    desligadas: int = 0  # eventos/detalhes preservados que perderam o vinculo com o acesso
    arquivo: str | None = None


@dataclass(slots=True)
class ResultadoRetencao:
    simulado: bool
    tabelas: list[ResultadoTabela] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def total_apagadas(self) -> int:
        return sum(t.apagadas for t in self.tabelas)


# --------------------------------------------------------------------------- consultas de vencimento


def _filtros(cortes: dict[str, datetime]) -> list[tuple[str, Any, Any, Any]]:
    """(rotulo, modelo, coluna_id, condicao_de_vencida), na ordem segura de remocao."""

    return [
        ("tb_logs", Log, Log.id_log, Log.data_hora < cortes["acesso"]),
        ("tb_logevento", LogEvento, LogEvento.id_logevento, LogEvento.data_hora < cortes["eventos"]),
        (
            "tb_sessao",
            Sessao,
            Sessao.id_sessao,
            (Sessao.status != "ATIVA")
            & (func.coalesce(Sessao.encerrada_em, Sessao.ultima_atividade) < cortes["sessoes"]),
        ),
        (
            "tb_alerta",
            Alerta,
            Alerta.id_alerta,
            (Alerta.status == "RESOLVIDO") & (Alerta.resolvido_em < cortes["alertas"]),
        ),
    ]


def _corte_da_tabela(rotulo: str, cortes: dict[str, datetime]) -> datetime:
    return cortes[
        {"tb_logs": "acesso", "tb_logevento": "eventos", "tb_sessao": "sessoes", "tb_alerta": "alertas"}[
            rotulo
        ]
    ]


def simular(db: Any, politica: Politica, agora: datetime | None = None) -> list[ResultadoTabela]:
    """Conta o que venceria, sem tocar em nada."""

    cortes = politica.cortes(agora or agora_local())
    resultado = []
    for rotulo, _modelo, coluna_id, condicao in _filtros(cortes):
        vencidas = db.execute(select(func.count()).select_from(coluna_id.class_).where(condicao)).scalar_one()
        resultado.append(ResultadoTabela(rotulo, _corte_da_tabela(rotulo, cortes), vencidas=int(vencidas)))
    return resultado


# --------------------------------------------------------------------------- arquivo


class _Arquivador:
    """Escreve linhas em `<pasta>/<tabela>-<carimbo>.csv.gz`, um arquivo por tabela e execucao."""

    def __init__(self, pasta: Path | None, carimbo: str) -> None:
        self._pasta = pasta
        self._carimbo = carimbo
        self._abertos: dict[str, tuple[Any, Any]] = {}
        self._pilha = contextlib.ExitStack()
        if pasta is not None:
            pasta.mkdir(parents=True, exist_ok=True)

    @property
    def ativo(self) -> bool:
        return self._pasta is not None

    def caminho(self, tabela: str) -> str | None:
        return str(self._pasta / f"{tabela}-{self._carimbo}.csv.gz") if self._pasta else None

    def gravar(self, tabela: str, colunas: list[str], linhas: list[Row[Any]]) -> int:
        """Grava e da flush; levanta se nao conseguir (quem chama NAO apaga nesse caso)."""

        if self._pasta is None:
            return 0
        if tabela not in self._abertos:
            arquivo = self._pilha.enter_context(
                gzip.open(str(self.caminho(tabela)), "wt", encoding="utf-8", newline="")  # noqa: SIM115
            )
            escritor = csv.writer(arquivo)
            escritor.writerow(colunas)
            self._abertos[tabela] = (arquivo, escritor)
        arquivo, escritor = self._abertos[tabela]
        for linha in linhas:
            escritor.writerow(["" if v is None else v for v in linha])
        arquivo.flush()
        return len(linhas)

    def fechar(self) -> None:
        self._pilha.close()
        self._abertos.clear()


# --------------------------------------------------------------------------- execucao


def _lote_ids(db: Any, coluna_id: Any, condicao: Any, tamanho: int) -> list[Any]:
    return list(db.execute(select(coluna_id).where(condicao).order_by(coluna_id).limit(tamanho)).scalars())


def _arquivar_lote(
    db: Any, arquivador: _Arquivador, tabela: Any, coluna_id: Any, ids: list[Any], rotulo: str
) -> int:
    if not arquivador.ativo:
        return 0
    colunas = [c.name for c in tabela.__table__.columns]
    linhas = db.execute(select(*tabela.__table__.columns).where(coluna_id.in_(ids))).all()
    return arquivador.gravar(rotulo, colunas, linhas)


def executar(
    bancos: CatalogoBancos,
    politica: Politica,
    *,
    agora: datetime | None = None,
    pasta_arquivo: Path | None = None,
    tamanho_lote: int = TAMANHO_LOTE_PADRAO,
    maximo_lotes: int | None = None,
    ao_progresso: Callable[[str], None] | None = None,
) -> ResultadoRetencao:
    """Apaga (arquivando antes, se pedido) o que passou do prazo, em lotes pequenos com COMMIT por lote.

    Nunca levanta: um erro interrompe a tabela atual, fica em `erros` e nada daquele lote e apagado.
    """

    agora = agora or agora_local()
    cortes = politica.cortes(agora)
    resultado = ResultadoRetencao(simulado=False)
    arquivador = _Arquivador(pasta_arquivo, f"{agora:%Y%m%d-%H%M%S}")
    aviso = ao_progresso or (lambda _m: None)
    try:
        for rotulo, modelo, coluna_id, condicao in _filtros(cortes):
            item = ResultadoTabela(rotulo, _corte_da_tabela(rotulo, cortes), arquivo=arquivador.caminho(rotulo))
            resultado.tabelas.append(item)
            lotes = 0
            while maximo_lotes is None or lotes < maximo_lotes:
                try:
                    with bancos.core.unidade_trabalho() as db:
                        ids = _lote_ids(db, coluna_id, condicao, tamanho_lote)
                        if not ids:
                            break
                        item.vencidas += len(ids)
                        item.arquivadas += _arquivar_lote(db, arquivador, modelo, coluna_id, ids, rotulo)
                        if rotulo == "tb_logs":
                            item.desligadas += _desligar_trilha_preservada(db, ids, cortes["eventos"])
                        apagadas = db.execute(delete(modelo).where(coluna_id.in_(ids))).rowcount
                        item.apagadas += int(apagadas or 0)
                except Exception as erro:
                    logger.exception("Retencao: falha em %s", rotulo)
                    resultado.erros.append(f"{rotulo}: {type(erro).__name__}: {erro}")
                    break
                lotes += 1
                aviso(f"{rotulo}: {item.apagadas} apagadas")
    finally:
        arquivador.fechar()
    return resultado


def _desligar_trilha_preservada(db: Any, ids_logs: list[int], corte_eventos: datetime) -> int:
    """Antes de apagar acessos vencidos, solta (`id_log = NULL`) eventos e detalhes que ainda estao no prazo."""

    eventos = db.execute(
        update(LogEvento)
        .where(LogEvento.id_log.in_(ids_logs), LogEvento.data_hora >= corte_eventos)
        .values(id_log=None)
    ).rowcount
    detalhes = db.execute(
        update(LogDetalhe)
        .where(LogDetalhe.id_log.in_(ids_logs), LogDetalhe.data_hora >= corte_eventos)
        .values(id_log=None)
    ).rowcount
    return int((eventos or 0) + (detalhes or 0))


# --------------------------------------------------------------------------- tamanho


def tamanho_tabelas(db: Any) -> list[dict[str, Any]]:
    """Linhas e MB por tabela do core (MB so no PostgreSQL) para decidir prazos com dado real."""

    resultado: list[dict[str, Any]] = []
    postgres = db.bind.dialect.name == "postgresql"
    for nome in TABELAS_MEDIDAS:
        try:
            linhas = int(db.execute(text(f"SELECT COUNT(*) FROM core.{nome}" if postgres else f"SELECT COUNT(*) FROM {nome}")).scalar_one())
            mb = None
            if postgres:
                tamanho = db.execute(
                    text("SELECT pg_total_relation_size(CAST(:nome AS regclass))"),
                    {"nome": f"core.{nome}"},
                ).scalar_one()
                mb = round(int(tamanho) / (1024 * 1024), 1)
            resultado.append({"tabela": nome, "linhas": linhas, "mb": mb})
        except Exception as erro:
            logger.warning("Tamanho de %s indisponivel: %s", nome, erro)
            resultado.append({"tabela": nome, "linhas": None, "mb": None})
    return resultado


def mais_antigo(db: Any) -> dict[str, datetime | None]:
    """Data do registro mais antigo de cada tabela de log, para saber quanto ja acumulou."""

    return {
        "tb_logs": db.execute(select(func.min(Log.data_hora))).scalar_one(),
        "tb_logevento": db.execute(select(func.min(LogEvento.data_hora))).scalar_one(),
        "tb_sessao": db.execute(select(func.min(Sessao.criada_em))).scalar_one(),
        "tb_sessao_evento": db.execute(select(func.min(EventoSessao.data_hora))).scalar_one(),
    }


__all__ = [
    "Politica",
    "ResultadoRetencao",
    "ResultadoTabela",
    "executar",
    "mais_antigo",
    "simular",
    "tamanho_tabelas",
]
