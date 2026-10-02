"""Modelos persistentes de sessao e eventos de sessao no schema core."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.seguranca import Sistema
    from luftbase.persistencia.core.usuario import Usuario


class Sessao(BaseLuft):
    """Sessao autenticada persistida no banco corporativo core."""

    __tablename__ = "tb_sessao"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ATIVA', 'FINALIZADA', 'EXPIRADA', 'REVOGADA')",
            name="ck_core_sessao_status",
        ),
    )

    id_sessao: Mapped[str] = mapped_column(String(128), primary_key=True)
    id_sistema: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_sessao_sistema",
            ondelete="CASCADE",
        )
    )
    codigo_usuario: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_sessao_usuario",
            ondelete="CASCADE",
        )
    )
    login_usuario: Mapped[str | None] = mapped_column(String(100))
    ip_origem: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    dados_sessao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="ATIVA",
    )
    total_renovacoes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    criada_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    ultima_atividade: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    expira_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
    )
    encerrada_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    motivo_encerramento: Mapped[str | None] = mapped_column(String(100))

    sistema: Mapped[Sistema | None] = relationship(back_populates="sessoes")
    usuario: Mapped[Usuario | None] = relationship(
        foreign_keys=[codigo_usuario],
        back_populates="sessoes",
    )
    eventos: Mapped[list[EventoSessao]] = relationship(
        back_populates="sessao",
        cascade="all, delete-orphan",
    )


class EventoSessao(BaseLuft):
    """Registro de evento do ciclo de vida da sessao."""

    __tablename__ = "tb_sessao_evento"
    __table_args__ = (
        CheckConstraint(
            "tipo_evento IN ('INICIO', 'RENOVACAO', 'LOGOUT', 'TIMEOUT', 'REVOGACAO')",
            name="ck_core_sessaoevento_tipo",
        ),
    )

    id_evento_sessao: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sessao: Mapped[str] = mapped_column(
        ForeignKey(
            "core.tb_sessao.id_sessao",
            name="fk_core_sessaoevento_sessao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_sistema: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_sessaoevento_sistema",
            ondelete="CASCADE",
        )
    )
    codigo_usuario: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_sessaoevento_usuario",
            ondelete="SET NULL",
        )
    )
    login_usuario: Mapped[str | None] = mapped_column(String(100))
    tipo_evento: Mapped[str] = mapped_column(String(50), nullable=False)
    ip_origem: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    data_hora: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    detalhes: Mapped[str | None] = mapped_column(Text)

    sessao: Mapped[Sessao] = relationship(back_populates="eventos")


Index("ix_core_sessao_status_expira", Sessao.status, Sessao.expira_em)
Index("ix_core_sessao_usuario", Sessao.codigo_usuario)
Index("ix_core_sessao_sistema", Sessao.id_sistema)
Index("ix_core_sessao_ultima_atividade", Sessao.ultima_atividade.desc())

Index("ix_core_sessaoevento_sessao", EventoSessao.id_sessao)
Index(
    "ix_core_sessaoevento_usuario_data",
    EventoSessao.codigo_usuario,
    EventoSessao.data_hora.desc(),
)
Index("ix_core_sessaoevento_data", EventoSessao.data_hora.desc())
