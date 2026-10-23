"""Modelos fixos e somente de consulta do diretorio no SQL Server."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, MetaData, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ESQUEMA_DIRETORIO = "Luftinforma.dbo"


class BaseDiretorio(DeclarativeBase):
    """Base isolada: suas tabelas nunca participam das migrations PostgreSQL."""

    metadata = MetaData(schema=ESQUEMA_DIRETORIO)


class GrupoDiretorio(BaseDiretorio):
    """Grupo corporativo mantido pelo sistema Luftinforma."""

    __tablename__ = "usuariogrupo"

    id_grupo: Mapped[int] = mapped_column(
        "codigo_usuariogrupo",
        Integer,
        primary_key=True,
    )
    sigla: Mapped[str | None] = mapped_column("Sigla_UsuarioGrupo", String)
    descricao: Mapped[str | None] = mapped_column("Descricao_UsuarioGrupo", String)
    permite_cadastrar: Mapped[int | None] = mapped_column("Permite_Cadastrar", Integer)
    permite_alterar: Mapped[int | None] = mapped_column("Permite_Alterar", Integer)
    permite_excluir: Mapped[int | None] = mapped_column("Permite_Excluir", Integer)

    usuarios: Mapped[list[UsuarioDiretorio]] = relationship(back_populates="grupo")


class UsuarioDiretorio(BaseDiretorio):
    """Usuario corporativo consultado no Luftinforma."""

    __tablename__ = "usuario"

    id_usuario: Mapped[int] = mapped_column("Codigo_Usuario", Integer, primary_key=True)
    login: Mapped[str | None] = mapped_column("Login_Usuario", String)
    nome_completo: Mapped[str | None] = mapped_column("Nome_Usuario", String)
    email: Mapped[str | None] = mapped_column("Email_Usuario", String)
    id_grupo: Mapped[int | None] = mapped_column(
        "codigo_usuariogrupo",
        ForeignKey(f"{ESQUEMA_DIRETORIO}.usuariogrupo.codigo_usuariogrupo"),
    )
    # Bloqueio do cadastro corporativo (1 = bloqueado). E outro, alem do `core.tb_usuario.bloqueado` do LuftBase.
    # `deferred`: as consultas que carregam o usuario inteiro nao pedem esta coluna; so quem a seleciona a le.
    bloqueado: Mapped[int | None] = mapped_column("Usuario_Bloqueado", Integer, deferred=True)

    grupo: Mapped[GrupoDiretorio | None] = relationship(back_populates="usuarios")


__all__ = [
    "BaseDiretorio",
    "ESQUEMA_DIRETORIO",
    "GrupoDiretorio",
    "UsuarioDiretorio",
]
