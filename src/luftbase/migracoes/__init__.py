"""Migrations Alembic empacotadas e controladas pelo LuftBase."""

from importlib.resources import files
from pathlib import Path


def obter_diretorio_migracoes() -> Path:
    """Retorna o diretorio das migrations quando o pacote estiver no sistema de arquivos."""

    recurso = files(__package__)
    return Path(str(recurso))


__all__ = ["obter_diretorio_migracoes"]
