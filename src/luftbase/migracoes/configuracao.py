"""Configuracao programatica do Alembic sem arquivo ``alembic.ini`` externo."""

from __future__ import annotations

from alembic.config import Config
from sqlalchemy import Connection

from luftbase.migracoes import obter_diretorio_migracoes


def criar_configuracao_alembic(*, conexao: Connection | None = None) -> Config:
    """Cria a configuracao apontando para as migrations empacotadas."""

    configuracao = Config()
    diretorio = obter_diretorio_migracoes()
    configuracao.set_main_option("script_location", str(diretorio))
    configuracao.set_main_option("version_locations", str(diretorio / "versoes"))
    configuracao.set_main_option("prepend_sys_path", ".")
    configuracao.set_main_option("path_separator", "os")
    if conexao is not None:
        configuracao.attributes["connection"] = conexao
    return configuracao


__all__ = ["criar_configuracao_alembic"]
