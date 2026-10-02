"""Modelo persistente da tabela de usuarios central do schema core."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.auditoria import Log, LogEvento
    from luftbase.persistencia.core.seguranca import PermissaoUsuario
    from luftbase.persistencia.core.sessoes import Sessao


class Usuario(BaseLuft):
    """Usuario corporativo mantido no PostgreSQL com espelhamento do LuftInforma."""

    __tablename__ = "tb_usuario"
    __table_args__ = (
        UniqueConstraint("login_usuario", name="uq_core_usuario_login"),
        Index("ix_core_usuario_email", "email_usuario"),
        Index("ix_core_usuario_grupo", "codigo_usuariogrupo"),
        Index("ix_core_usuario_online", "status_online"),
        Index("ix_core_usuario_ultimo_acesso", text("ultimo_acesso DESC NULLS LAST")),
    )

    # Identificadores e dados alinhados ao LuftInforma
    codigo_usuario: Mapped[int] = mapped_column(Integer, primary_key=True)
    login_usuario: Mapped[str] = mapped_column(String(100), nullable=False)
    nome_usuario: Mapped[str] = mapped_column(String(255), nullable=False)
    email_usuario: Mapped[str | None] = mapped_column(String(255))
    codigo_usuariogrupo: Mapped[int | None] = mapped_column(Integer)
    sigla_usuariogrupo: Mapped[str | None] = mapped_column(String(100))
    descricao_usuariogrupo: Mapped[str | None] = mapped_column(String(255))

    # Presença, perfil e imagem
    foto_perfil: Mapped[str | None] = mapped_column(Text)
    status_online: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    id_sessao_atual: Mapped[str | None] = mapped_column(
        String(128),
        ForeignKey(
            "core.tb_sessao.id_sessao",
            name="fk_core_usuario_sessao_atual",
            ondelete="SET NULL",
            use_alter=True,
        ),
    )

    # Dados funcionais e corporativos
    telefone_usuario: Mapped[str | None] = mapped_column(String(50))
    celular_usuario: Mapped[str | None] = mapped_column(String(50))
    cargo_usuario: Mapped[str | None] = mapped_column(String(150))
    departamento_usuario: Mapped[str | None] = mapped_column(String(150))
    unidade_filial: Mapped[str | None] = mapped_column(String(150))
    codigo_empresa: Mapped[int | None] = mapped_column(Integer)
    codigo_filial: Mapped[int | None] = mapped_column(Integer)
    gestor_imediato: Mapped[str | None] = mapped_column(String(150))
    codigo_gestor: Mapped[int | None] = mapped_column(Integer)

    # Telemetria e acesso
    ultimo_acesso: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    ultimo_ip: Mapped[str | None] = mapped_column(String(50))
    ultimo_user_agent: Mapped[str | None] = mapped_column(String(500))
    total_logins: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )

    # Preferências de interface incorporadas
    tema_preferido: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="luft",
    )
    modo_tema: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="SISTEMA",
    )
    idioma: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        server_default="pt-BR",
    )

    # Governança
    ativo: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("true"),
    )
    bloqueado: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    motivo_bloqueio: Mapped[str | None] = mapped_column(String(255))
    metadados_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB().with_variant(Text(), "sqlite")
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
    )

    # Relacionamentos
    sessoes: Mapped[list[Sessao]] = relationship(
        "Sessao",
        foreign_keys="Sessao.codigo_usuario",
        back_populates="usuario",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sessao_atual: Mapped[Sessao | None] = relationship(
        "Sessao",
        foreign_keys=[id_sessao_atual],
        post_update=True,
    )
    permissoes: Mapped[list[PermissaoUsuario]] = relationship(
        "PermissaoUsuario",
        back_populates="usuario",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    logs: Mapped[list[Log]] = relationship(
        "Log",
        foreign_keys="Log.codigo_usuario",
        back_populates="usuario",
        passive_deletes=True,
    )
    eventos: Mapped[list[LogEvento]] = relationship(
        "LogEvento",
        foreign_keys="LogEvento.codigo_usuario",
        back_populates="usuario",
        passive_deletes=True,
    )


__all__ = ["Usuario"]

