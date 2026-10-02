"""Modelos da trilha estruturada de auditoria: tb_logs -> tb_logevento -> tb_logdetalhe."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.seguranca import Sistema
    from luftbase.persistencia.core.usuario import Usuario


class Log(BaseLuft):
    """Raiz da trilha de auditoria: requisicoes e rotas HTTP."""

    __tablename__ = "tb_logs"
    __table_args__ = (
        UniqueConstraint(
            "id_log",
            "id_sistema",
            name="uq_core_logs_id_sistema",
        ),
        CheckConstraint(
            "duracao_ms IS NULL OR duracao_ms >= 0",
            name="ck_core_logs_duracao",
        ),
        CheckConstraint(
            "status_http IS NULL OR status_http BETWEEN 100 AND 599",
            name="ck_core_logs_status_http",
        ),
    )

    id_log: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_logs_sistema",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    codigo_usuario: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_logs_usuario",
            ondelete="SET NULL",
        )
    )
    login_usuario: Mapped[str | None] = mapped_column(String(100))
    codigo_grupo: Mapped[int | None] = mapped_column(Integer)
    nome_grupo: Mapped[str | None] = mapped_column(String(100))
    rota_acessada: Mapped[str] = mapped_column(String(500), nullable=False)
    metodo_http: Mapped[str] = mapped_column(String(10), nullable=False)
    ip_origem: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    permissao_exigida: Mapped[str | None] = mapped_column(String(180))
    acesso_permitido: Mapped[bool | None]
    parametros_requisicao: Mapped[str | None] = mapped_column(Text)
    resposta_acao: Mapped[str | None] = mapped_column(Text)
    id_correlacao: Mapped[str] = mapped_column(String(64), nullable=False)
    duracao_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status_http: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    data_hora: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    sistema: Mapped[Sistema] = relationship(back_populates="logs")
    usuario: Mapped[Usuario | None] = relationship(
        foreign_keys=[codigo_usuario],
        back_populates="logs",
    )
    eventos: Mapped[list[LogEvento]] = relationship(
        back_populates="log",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    detalhes: Mapped[list[LogDetalhe]] = relationship(
        back_populates="log",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LogEvento(BaseLuft):
    """Eventos de dominio, acoes e ocorrencias disparadas entre a rota e os servicos."""

    __tablename__ = "tb_logevento"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id_log", "id_sistema"],
            ["core.tb_logs.id_log", "core.tb_logs.id_sistema"],
            name="fk_core_logevento_log",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "id_logevento",
            "id_sistema",
            name="uq_core_logevento_id_sistema",
        ),
        CheckConstraint(
            "severidade IN ('BAIXA', 'MEDIA', 'ALTA', 'CRITICA')",
            name="ck_core_logevento_severidade",
        ),
    )

    id_logevento: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_logevento_sistema",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_log: Mapped[int | None] = mapped_column(BigInteger)
    codigo_usuario: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_logevento_usuario",
            ondelete="SET NULL",
        )
    )
    login_usuario: Mapped[str | None] = mapped_column(String(100))
    codigo_grupo: Mapped[int | None] = mapped_column(Integer)
    nome_grupo: Mapped[str | None] = mapped_column(String(100))
    acao: Mapped[str] = mapped_column(String(80), nullable=False)
    recurso: Mapped[str] = mapped_column(String(150), nullable=False)
    id_recurso: Mapped[str | None] = mapped_column(String(150))
    descricao: Mapped[str] = mapped_column(String(1000), nullable=False)
    ip_origem: Mapped[str | None] = mapped_column(String(50))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    severidade: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="BAIXA",
    )
    traceback: Mapped[str | None] = mapped_column(Text)
    id_correlacao: Mapped[str | None] = mapped_column(String(64))
    data_hora: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    sistema: Mapped[Sistema] = relationship(back_populates="eventos", overlaps="eventos,log")
    usuario: Mapped[Usuario | None] = relationship(
        foreign_keys=[codigo_usuario],
        back_populates="eventos",
    )
    log: Mapped[Log | None] = relationship(back_populates="eventos", overlaps="eventos,sistema")
    detalhes: Mapped[list[LogDetalhe]] = relationship(
        back_populates="evento",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class LogDetalhe(BaseLuft):
    """Detalhes finos das alteracoes de dados no backend (antes -> depois)."""

    __tablename__ = "tb_logdetalhe"
    __table_args__ = (
        CheckConstraint(
            "tipo_alteracao IN ('CRIACAO', 'ALTERACAO', 'EXCLUSAO', 'SUBSTITUICAO')",
            name="ck_core_logdetalhe_tipo_alteracao",
        ),
    )

    id_logdetalhe: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_log: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_logs.id_log",
            name="fk_core_logdetalhe_log",
            ondelete="CASCADE",
        )
    )
    id_logevento: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_logevento.id_logevento",
            name="fk_core_logdetalhe_logevento",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tipo_alteracao: Mapped[str] = mapped_column(String(20), nullable=False)
    campos_alterados_json: Mapped[str | None] = mapped_column(Text)
    dados_anteriores_json: Mapped[str | None] = mapped_column(Text)
    dados_novos_json: Mapped[str | None] = mapped_column(Text)
    data_hora: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    log: Mapped[Log | None] = relationship(back_populates="detalhes")
    evento: Mapped[LogEvento] = relationship(back_populates="detalhes")


# Aliases de compatibilidade para evitar quebras em codigos legados
LogAcesso = Log
LogAlteracao = LogDetalhe

Index("ix_core_logs_data", Log.data_hora.desc())
Index("ix_core_logs_sistema_data", Log.id_sistema, Log.data_hora.desc())
Index("ix_core_logs_usuario_data", Log.codigo_usuario, Log.data_hora.desc())
Index("ix_core_logs_grupo_data", Log.codigo_grupo, Log.data_hora.desc())
Index("ix_core_logs_correlacao", Log.id_sistema, Log.id_correlacao)

Index("ix_core_logevento_log", LogEvento.id_log)
Index("ix_core_logevento_sistema_data", LogEvento.id_sistema, LogEvento.data_hora.desc())
Index("ix_core_logevento_usuario_data", LogEvento.codigo_usuario, LogEvento.data_hora.desc())
Index("ix_core_logevento_grupo_data", LogEvento.codigo_grupo, LogEvento.data_hora.desc())
Index("ix_core_logevento_correlacao", LogEvento.id_sistema, LogEvento.id_correlacao)
Index(
    "ix_core_logevento_sistema_severidade_data",
    LogEvento.id_sistema,
    LogEvento.severidade,
    LogEvento.data_hora.desc(),
)
Index(
    "ix_core_logevento_recurso",
    LogEvento.recurso,
    LogEvento.id_recurso,
    LogEvento.data_hora.desc(),
)

Index("ix_core_logdetalhe_log", LogDetalhe.id_log)
Index("ix_core_logdetalhe_evento", LogDetalhe.id_logevento)
Index("ix_core_logdetalhe_tipo_data", LogDetalhe.tipo_alteracao, LogDetalhe.data_hora.desc())
