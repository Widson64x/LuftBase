"""Modelos relacionais do catalogo de sistemas e da autorizacao hierarquica."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from luftbase.autorizacao.catalogo import AcaoPermissao
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import TIMESTAMP_MILISSEGUNDOS

if TYPE_CHECKING:
    from luftbase.persistencia.core.auditoria import Log, LogEvento
    from luftbase.persistencia.core.notificacoes import Notificacao
    from luftbase.persistencia.core.publicacoes import Publicacao
    from luftbase.persistencia.core.sessoes import Sessao
    from luftbase.persistencia.core.usuario import Usuario


class Sistema(BaseLuft):
    """Sistema identificado pelo mesmo ``id_sistema`` usado no Vault."""

    __tablename__ = "tb_sistema"
    __table_args__ = (
        UniqueConstraint("nome_sistema", name="uq_core_sistema_nome"),
        CheckConstraint("ordem_exibicao >= 0", name="ck_core_sistema_ordem"),
        CheckConstraint(
            "categoria IN ('HUB', 'APLICACAO', 'SERVICO')",
            name="ck_core_sistema_categoria",
        ),
    )

    id_sistema: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nome_sistema: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao_sistema: Mapped[str | None] = mapped_column(String(500))
    categoria: Mapped[str] = mapped_column(String(20), nullable=False, server_default="APLICACAO")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    em_manutencao: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    ordem_exibicao: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
    )
    icone: Mapped[str | None] = mapped_column(String(255))
    cor: Mapped[str | None] = mapped_column(String(30))
    link: Mapped[str | None] = mapped_column(String(500))
    url_saude: Mapped[str | None] = mapped_column(String(500))
    responsavel: Mapped[str | None] = mapped_column(String(150))
    contato_suporte: Mapped[str | None] = mapped_column(String(255))
    schema_aplicacao: Mapped[str | None] = mapped_column(String(63))
    metadados_json: Mapped[dict[str, object] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite")
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    modulos: Mapped[list[Modulo]] = relationship(
        back_populates="sistema",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    permissoes: Mapped[list[Permissao]] = relationship(
        back_populates="sistema",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="modulo,permissoes",
    )
    logs: Mapped[list[Log]] = relationship(
        back_populates="sistema",
        passive_deletes=True,
    )
    eventos: Mapped[list[LogEvento]] = relationship(
        back_populates="sistema",
        passive_deletes=True,
        overlaps="eventos,log,sistema",
    )
    notificacoes: Mapped[list[Notificacao]] = relationship(
        back_populates="sistema", passive_deletes=True
    )
    publicacoes: Mapped[list[Publicacao]] = relationship(
        back_populates="sistema", passive_deletes=True
    )
    sessoes: Mapped[list[Sessao]] = relationship(back_populates="sistema", passive_deletes=True)


class Modulo(BaseLuft):
    """Modulo funcional que organiza as permissoes de um sistema."""

    __tablename__ = "tb_modulo"
    __table_args__ = (
        UniqueConstraint("id_sistema", "codigo_modulo", name="uq_core_modulo_codigo_sistema"),
        UniqueConstraint("id_modulo", "id_sistema", name="uq_core_modulo_id_sistema"),
        CheckConstraint(
            "codigo_modulo ~ '^[A-Z][A-Z0-9_]{1,49}$'",
            name="ck_core_modulo_codigo",
        ),
        CheckConstraint("ordem_exibicao >= 0", name="ck_core_modulo_ordem"),
    )

    id_modulo: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_modulo_sistema",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    codigo_modulo: Mapped[str] = mapped_column(String(50), nullable=False)
    nome_modulo: Mapped[str] = mapped_column(String(100), nullable=False)
    descricao_modulo: Mapped[str | None] = mapped_column(String(500))
    icone: Mapped[str | None] = mapped_column(String(100))
    ordem_exibicao: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    sistema: Mapped[Sistema] = relationship(back_populates="modulos")
    permissoes: Mapped[list[Permissao]] = relationship(
        back_populates="modulo",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="permissoes,sistema",
    )


class Permissao(BaseLuft):
    """No autorizavel de uma arvore pertencente a um modulo e sistema."""

    __tablename__ = "tb_permissao"
    __table_args__ = (
        UniqueConstraint(
            "chave_permissao",
            "id_sistema",
            name="uq_core_permissao_chave_sistema",
        ),
        UniqueConstraint(
            "id_permissao",
            "id_sistema",
            name="uq_core_permissao_id_sistema",
        ),
        ForeignKeyConstraint(
            ["id_modulo", "id_sistema"],
            ["core.tb_modulo.id_modulo", "core.tb_modulo.id_sistema"],
            name="fk_core_permissao_modulo",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["id_permissao_pai", "id_sistema"],
            ["core.tb_permissao.id_permissao", "core.tb_permissao.id_sistema"],
            name="fk_core_permissao_pai",
            ondelete="CASCADE",
            use_alter=True,
        ),
        CheckConstraint(
            "chave_permissao ~ '^[A-Z][A-Z0-9_]*(\\.[A-Z][A-Z0-9_]*){1,}$'",
            name="ck_core_permissao_chave",
        ),
        CheckConstraint(
            f"acao IN ({', '.join(repr(acao.value) for acao in AcaoPermissao)})",
            name="ck_core_permissao_acao",
        ),
        CheckConstraint(
            "id_permissao_pai IS NULL OR id_permissao_pai <> id_permissao",
            name="ck_core_permissao_pai_distinto",
        ),
        CheckConstraint("ordem_exibicao >= 0", name="ck_core_permissao_ordem"),
    )

    id_permissao: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_sistema: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_sistema.id_sistema",
            name="fk_core_permissao_sistema",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_modulo: Mapped[int] = mapped_column(Integer, nullable=False)
    id_permissao_pai: Mapped[int | None] = mapped_column(Integer)
    chave_permissao: Mapped[str] = mapped_column(String(180), nullable=False)
    recurso: Mapped[str] = mapped_column(String(80), nullable=False)
    acao: Mapped[str] = mapped_column(String(30), nullable=False)
    descricao_permissao: Mapped[str] = mapped_column(String(500), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sensivel: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    eh_acesso_sistema: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )
    ordem_exibicao: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        server_default="0",
    )
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    sistema: Mapped[Sistema] = relationship(
        back_populates="permissoes", overlaps="modulo,permissoes"
    )
    modulo: Mapped[Modulo] = relationship(
        back_populates="permissoes", overlaps="permissoes,sistema"
    )
    pai: Mapped[Permissao | None] = relationship(
        remote_side="Permissao.id_permissao",
        foreign_keys=[id_permissao_pai],
        back_populates="filhas",
        overlaps="modulo,permissoes,sistema",
    )
    filhas: Mapped[list[Permissao]] = relationship(
        back_populates="pai",
        cascade="all, delete-orphan",
        passive_deletes=True,
        overlaps="modulo,pai,permissoes,sistema",
    )
    grupos: Mapped[list[PermissaoGrupo]] = relationship(
        back_populates="permissao",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    usuarios: Mapped[list[PermissaoUsuario]] = relationship(
        back_populates="permissao",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PermissaoGrupo(BaseLuft):
    """Regra explicita de concessao ou negacao para um grupo do Luftinforma."""

    __tablename__ = "tb_permissaogrupo"
    __table_args__ = (
        UniqueConstraint(
            "codigo_usuariogrupo",
            "id_permissao",
            name="uq_core_permissaogrupo",
        ),
        CheckConstraint("codigo_usuariogrupo > 0", name="ck_core_permissaogrupo_codigo"),
    )

    id_vinculo: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    codigo_usuariogrupo: Mapped[int] = mapped_column(Integer, nullable=False)
    id_permissao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_permissao.id_permissao",
            name="fk_core_permissaogrupo_permissao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    conceder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    codigo_usuario_alteracao: Mapped[int | None] = mapped_column(Integer)
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
    )

    permissao: Mapped[Permissao] = relationship(back_populates="grupos")


class PermissaoUsuario(BaseLuft):
    """Excecao explicita de concessao ou negacao para um usuario do Luftinforma."""

    __tablename__ = "tb_permissaousuario"
    __table_args__ = (
        UniqueConstraint(
            "codigo_usuario",
            "id_permissao",
            name="uq_core_permissaousuario",
        ),
        CheckConstraint("codigo_usuario > 0", name="ck_core_permissaousuario_codigo"),
    )

    id_vinculo: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    codigo_usuario: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_usuario.codigo_usuario",
            name="fk_core_permissaousuario_usuario",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    id_permissao: Mapped[int] = mapped_column(
        ForeignKey(
            "core.tb_permissao.id_permissao",
            name="fk_core_permissaousuario_permissao",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    conceder: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    codigo_usuario_alteracao: Mapped[int | None] = mapped_column(Integer)
    atualizado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=func.now(),
    )

    permissao: Mapped[Permissao] = relationship(back_populates="usuarios")
    usuario: Mapped[Usuario] = relationship("Usuario", foreign_keys=[codigo_usuario], back_populates="permissoes")


Index("ix_core_sistema_ativo_ordem", Sistema.ativo, Sistema.ordem_exibicao)
Index("ix_core_modulo_sistema_ordem", Modulo.id_sistema, Modulo.ordem_exibicao)
Index("ix_core_permissao_sistema", Permissao.id_sistema)
Index("ix_core_permissao_modulo_ordem", Permissao.id_modulo, Permissao.ordem_exibicao)
Index("ix_core_permissao_pai", Permissao.id_permissao_pai)
Index(
    "ux_core_permissao_acesso_sistema",
    Permissao.id_sistema,
    unique=True,
    postgresql_where=Permissao.eh_acesso_sistema.is_(True),
)
Index("ix_core_permissaogrupo_permissao", PermissaoGrupo.id_permissao)
Index("ix_core_permissaogrupo_grupo", PermissaoGrupo.codigo_usuariogrupo)
Index("ix_core_permissaousuario_permissao", PermissaoUsuario.id_permissao)
Index("ix_core_permissaousuario_usuario", PermissaoUsuario.codigo_usuario)
