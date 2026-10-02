"""Modelos de notificacoes compartilhadas e suas leituras."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Identity,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.publicacoes import PublicacaoNotificacao
    from luftbase.persistencia.core.seguranca import Sistema


class Notificacao(BaseLuft):
    """Mensagem direcionada a usuario, grupo ou audiencia sistemica."""

    __tablename__ = "tb_notificacao"
    __table_args__ = (
        CheckConstraint(
            "tipo IN ('SISTEMA', 'ALERTA', 'INFO', 'SUCESSO', 'ERRO')",
            name="ck_core_notificacao_tipo",
        ),
        CheckConstraint(
            "categoria IN ('ETL', 'SEGURANCA', 'BANCO', 'SERVICO', 'GERAL', "
            "'USUARIO', 'CONFIGURACAO', 'INTEGRACAO', 'COMUNICADO', 'ATUALIZACAO')",
            name="ck_core_notificacao_categoria",
        ),
        Index(
            "ix_core_notificacao_expiracao",
            "expira_em",
            postgresql_where=text("expira_em IS NOT NULL"),
        ),
    )

    id_notificacao: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sistema: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_notificacao_sistema",
            ondelete="CASCADE",
        )
    )
    id_usuario_destino: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_notificacao_usuario",
            ondelete="SET NULL",
        )
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, server_default="INFO")
    categoria: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="GERAL",
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    mensagem: Mapped[str] = mapped_column(Text, nullable=False)
    icone: Mapped[str | None] = mapped_column(String(100))
    lida: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    data_criacao: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    data_leitura: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    criado_por: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        server_default="SISTEMA",
    )
    metadados_json: Mapped[str | None] = mapped_column(Text)
    expira_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    id_grupo_destino: Mapped[int | None] = mapped_column(Integer)
    exibir_a_partir_de: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)

    sistema: Mapped[Sistema | None] = relationship(back_populates="notificacoes")
    leituras: Mapped[list[NotificacaoLeitura]] = relationship(
        back_populates="notificacao",
        cascade="all, delete-orphan",
    )
    vinculos_publicacao: Mapped[list[PublicacaoNotificacao]] = relationship(
        back_populates="notificacao",
        cascade="all, delete-orphan",
    )


class NotificacaoLeitura(BaseLuft):
    """Confirmacao individual de leitura de uma notificacao."""

    __tablename__ = "tb_notificacao_leitura"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id_notificacao",
            "id_usuario",
            name="pk_core_notificacao_leitura",
        ),
    )

    id_notificacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_notificacao.id_notificacao",
            name="fk_core_notificacao_leitura_notificacao",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_notificacaoleitura_usuario",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    data_leitura: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    notificacao: Mapped[Notificacao] = relationship(back_populates="leituras")


Index("ix_core_notificacao_sistema_data", Notificacao.id_sistema, Notificacao.data_criacao.desc())
Index(
    "ix_core_notificacao_usuario_lida_data",
    Notificacao.id_usuario_destino,
    Notificacao.lida,
    Notificacao.data_criacao.desc(),
    postgresql_include=("tipo", "categoria", "titulo", "icone"),
)
Index(
    "ix_core_notificacao_grupo_sistema_data",
    Notificacao.id_grupo_destino,
    Notificacao.id_sistema,
    Notificacao.data_criacao.desc(),
)
Index(
    "ix_core_notificacao_leitura_usuario",
    NotificacaoLeitura.id_usuario,
    NotificacaoLeitura.data_leitura.desc(),
)
