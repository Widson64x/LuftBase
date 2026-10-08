"""Alertas para o desenvolvedor: um registro por problema aberto (`tb_alerta`) e a trava do avaliador."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS


class Alerta(BaseLuft):
    """Um problema detectado (ex.: erros 500 de uma pessoa numa rota), aberto ate parar de ocorrer."""

    __tablename__ = "tb_alerta"
    __table_args__ = (
        CheckConstraint("status IN ('ABERTO', 'RESOLVIDO')", name="ck_core_alerta_status"),
        Index("ix_core_alerta_status", "status", "ultima_ocorrencia"),
        Index("ix_core_alerta_chave", "chave", "status"),
    )

    id_alerta: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    chave: Mapped[str] = mapped_column(String(400), nullable=False)
    regra: Mapped[str] = mapped_column(String(40), nullable=False)
    id_sistema: Mapped[int | None] = mapped_column(Integer)
    login_usuario: Mapped[str | None] = mapped_column(String(100))
    rota: Mapped[str | None] = mapped_column(String(500))
    status_http: Mapped[int | None] = mapped_column(SmallInteger)
    ip_origem: Mapped[str | None] = mapped_column(String(50))
    id_correlacao: Mapped[str | None] = mapped_column(String(64))
    detalhe: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="ABERTO")
    ocorrencias: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocorrencias_notificadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primeira_ocorrencia: Mapped[datetime] = mapped_column(TIMESTAMP_MILISSEGUNDOS, nullable=False)
    ultima_ocorrencia: Mapped[datetime] = mapped_column(TIMESTAMP_MILISSEGUNDOS, nullable=False)
    aberto_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS, nullable=False, server_default=DATA_HORA_LOCAL
    )
    ultima_notificacao: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    resolvido_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    silenciado_ate: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    texto_extra: Mapped[str | None] = mapped_column(Text)


class AlertaControle(BaseLuft):
    """Estado do avaliador: ate onde olhou e a trava que impede dois executores ao mesmo tempo."""

    __tablename__ = "tb_alerta_controle"

    chave: Mapped[str] = mapped_column(String(50), primary_key=True)
    ultima_execucao_ate: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    em_execucao_ate: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)


__all__ = ["Alerta", "AlertaControle"]
