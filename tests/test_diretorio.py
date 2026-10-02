"""Testes dos modelos fixos e somente leitura do diretorio corporativo."""

import pytest
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable

from luftbase.identidade.repositorio import RepositorioUsuariosDiretorio
from luftbase.persistencia.diretorio import (
    BaseDiretorio,
    GrupoDiretorio,
    UsuarioDiretorio,
)


def test_diretorio_possui_somente_usuario_e_grupo() -> None:
    assert set(BaseDiretorio.metadata.tables) == {
        "Luftinforma.dbo.usuario",
        "Luftinforma.dbo.usuariogrupo",
    }


def test_modelos_preservam_nomes_fisicos_do_sqlserver() -> None:
    assert UsuarioDiretorio.id_usuario.property.columns[0].name == "Codigo_Usuario"
    assert UsuarioDiretorio.login.property.columns[0].name == "Login_Usuario"
    assert UsuarioDiretorio.nome_completo.property.columns[0].name == "Nome_Usuario"
    assert UsuarioDiretorio.email.property.columns[0].name == "Email_Usuario"
    assert GrupoDiretorio.sigla.property.columns[0].name == "Sigla_UsuarioGrupo"


def test_tabela_compila_com_nome_qualificado_sqlserver() -> None:
    ddl = str(CreateTable(UsuarioDiretorio.__table__).compile(dialect=mssql.dialect()))

    assert "[Luftinforma].dbo.usuario" in ddl
    assert "Codigo_Usuario" in ddl


def test_repositorio_recusa_banco_com_escrita() -> None:
    banco = type("Banco", (), {"somente_leitura": False})()

    with pytest.raises(ValueError, match="somente leitura"):
        RepositorioUsuariosDiretorio(banco)  # type: ignore[arg-type]
