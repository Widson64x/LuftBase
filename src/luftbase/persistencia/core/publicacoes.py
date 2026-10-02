"""Modelos de publicacoes, audiencias, leituras e notas de atualizacao."""

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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.notificacoes import Notificacao
    from luftbase.persistencia.core.seguranca import Sistema


class Publicacao(BaseLuft):
    """Comunicado ou nota de atualizacao publicado para uma audiencia."""

    __tablename__ = "tb_publicacao"
    __table_args__ = (
        CheckConstraint(
            "tipo_publicacao IN ('COMUNICADO', 'ATUALIZACAO')",
            name="ck_core_publicacao_tipo",
        ),
        CheckConstraint(
            "status_publicacao IN ('RASCUNHO', 'AGENDADO', 'PUBLICADO', 'ARQUIVADO')",
            name="ck_core_publicacao_status",
        ),
        CheckConstraint(
            "tipo_audiencia IN ('GERAL', 'GRUPOS')",
            name="ck_core_publicacao_audiencia",
        ),
        CheckConstraint(
            "prioridade IN ('BAIXA', 'NORMAL', 'ALTA', 'CRITICA')",
            name="ck_core_publicacao_prioridade",
        ),
        CheckConstraint(
            "fonte IN ('INTERNO', 'GMAIL', 'API')",
            name="ck_core_publicacao_fonte",
        ),
        CheckConstraint(
            "tipo_publicacao <> 'ATUALIZACAO' OR NULLIF(BTRIM(versao), '') IS NOT NULL",
            name="ck_core_publicacao_versao",
        ),
        CheckConstraint(
            "expira_em IS NULL OR exibir_a_partir_de IS NULL OR expira_em > exibir_a_partir_de",
            name="ck_core_publicacao_vigencia",
        ),
        CheckConstraint(
            "metadados_json IS NULL OR metadados_json::jsonb IS NOT NULL",
            name="ck_core_publicacao_metadados_json",
        ),
        Index(
            "ux_core_publicacao_fonte_id_externo",
            "fonte",
            "id_externo",
            unique=True,
            postgresql_where=text("id_externo IS NOT NULL"),
        ),
    )

    id_publicacao: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_publicacao_sistema",
            ondelete="CASCADE",
        ),
        nullable=False,
        server_default="0",
    )
    tipo_publicacao: Mapped[str] = mapped_column(String(20), nullable=False)
    status_publicacao: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="RASCUNHO",
    )
    tipo_audiencia: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="GERAL",
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    resumo: Mapped[str | None] = mapped_column(String(500))
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    prioridade: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="NORMAL",
    )
    versao: Mapped[str | None] = mapped_column(String(50))
    notificar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    fixado: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    exibir_a_partir_de: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    expira_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    data_publicacao: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    data_criacao: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    data_atualizacao: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    criado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_publicacao_criadopor",
            ondelete="SET NULL",
        )
    )
    criado_por: Mapped[str] = mapped_column(String(150), nullable=False)
    atualizado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_publicacao_atualizadopor",
            ondelete="SET NULL",
        )
    )
    atualizado_por: Mapped[str | None] = mapped_column(String(150))
    fonte: Mapped[str] = mapped_column(String(20), nullable=False, server_default="INTERNO")
    id_externo: Mapped[str | None] = mapped_column(String(255))
    thread_externo: Mapped[str | None] = mapped_column(String(255))
    remetente_externo: Mapped[str | None] = mapped_column(String(255))
    url_externa: Mapped[str | None] = mapped_column(String(500))
    metadados_json: Mapped[str | None] = mapped_column(Text)

    sistema: Mapped[Sistema] = relationship(back_populates="publicacoes")
    grupos: Mapped[list[PublicacaoGrupo]] = relationship(
        back_populates="publicacao",
        cascade="all, delete-orphan",
    )
    leituras: Mapped[list[PublicacaoLeitura]] = relationship(
        back_populates="publicacao",
        cascade="all, delete-orphan",
    )
    notificacoes: Mapped[list[PublicacaoNotificacao]] = relationship(
        back_populates="publicacao",
        cascade="all, delete-orphan",
    )
    itens_atualizacao: Mapped[list[NotaAtualizacaoItem]] = relationship(
        back_populates="publicacao",
        cascade="all, delete-orphan",
        order_by="NotaAtualizacaoItem.ordem",
    )


class PublicacaoGrupo(BaseLuft):
    """Grupo do Luftinforma incluido na audiencia de uma publicacao."""

    __tablename__ = "tb_publicacaogrupo"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id_publicacao",
            "id_grupo",
            name="pk_core_publicacaogrupo",
        ),
    )

    id_publicacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_publicacao.id_publicacao",
            name="fk_core_publicacaogrupo_publicacao",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    id_grupo: Mapped[int] = mapped_column(Integer, primary_key=True)

    publicacao: Mapped[Publicacao] = relationship(back_populates="grupos")


class PublicacaoLeitura(BaseLuft):
    """Confirmacao individual de leitura de uma publicacao."""

    __tablename__ = "tb_publicacaoleitura"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id_publicacao",
            "id_usuario",
            name="pk_core_publicacaoleitura",
        ),
    )

    id_publicacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_publicacao.id_publicacao",
            name="fk_core_publicacaoleitura_publicacao",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    id_usuario: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_publicacaoleitura_usuario",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )
    data_leitura: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    publicacao: Mapped[Publicacao] = relationship(back_populates="leituras")


class PublicacaoNotificacao(BaseLuft):
    """Vinculo rastreavel entre publicacao e notificacao emitida."""

    __tablename__ = "tb_publicacaonotificacao"
    __table_args__ = (
        UniqueConstraint(
            "id_publicacao",
            "id_notificacao",
            name="uq_core_publicacaonotificacao",
        ),
    )

    id_vinculo: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_publicacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_publicacao.id_publicacao",
            name="fk_core_publicacaonotificacao_publicacao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_notificacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_notificacao.id_notificacao",
            name="fk_core_publicacaonotificacao_notificacao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    data_criacao: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    publicacao: Mapped[Publicacao] = relationship(back_populates="notificacoes")
    notificacao: Mapped[Notificacao] = relationship(back_populates="vinculos_publicacao")


class NotaAtualizacaoItem(BaseLuft):
    """Item ordenado que descreve uma alteracao de versao publicada."""

    __tablename__ = "tb_notaatualizacaoitem"
    __table_args__ = (
        CheckConstraint(
            "tipo_item IN ('NOVO', 'MELHORIA', 'CORRECAO', 'SEGURANCA', 'TECNICO')",
            name="ck_core_nota_item_tipo",
        ),
    )

    id_item: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_publicacao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_publicacao.id_publicacao",
            name="fk_core_nota_item_publicacao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tipo_item: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="MELHORIA",
    )
    titulo: Mapped[str] = mapped_column(String(200), nullable=False)
    descricao: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    publicacao: Mapped[Publicacao] = relationship(back_populates="itens_atualizacao")


Index(
    "ix_core_publicacao_escopo_tipo_status_data",
    Publicacao.id_sistema,
    Publicacao.tipo_publicacao,
    Publicacao.status_publicacao,
    Publicacao.data_publicacao.desc(),
    postgresql_include=(
        "titulo",
        "resumo",
        "prioridade",
        "tipo_audiencia",
        "fixado",
        "exibir_a_partir_de",
        "expira_em",
    ),
)
Index(
    "ix_core_publicacaogrupo_grupo_publicacao",
    PublicacaoGrupo.id_grupo,
    PublicacaoGrupo.id_publicacao,
)
Index(
    "ix_core_publicacaoleitura_usuario",
    PublicacaoLeitura.id_usuario,
    PublicacaoLeitura.data_leitura.desc(),
)
Index(
    "ix_core_publicacaonotificacao_notificacao",
    PublicacaoNotificacao.id_notificacao,
)
Index(
    "ix_core_nota_item_publicacao_ordem",
    NotaAtualizacaoItem.id_publicacao,
    NotaAtualizacaoItem.ordem,
    NotaAtualizacaoItem.id_item,
)
