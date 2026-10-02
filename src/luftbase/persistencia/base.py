"""Base declarativa unica e convencoes de metadados do LuftBase."""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

ESQUEMA_CORE = "core"

CONVENCAO_NOMES = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class BaseLuft(DeclarativeBase):
    """Base compartilhada exclusivamente pelos modelos mantidos no pacote."""

    metadata = MetaData(schema=ESQUEMA_CORE, naming_convention=CONVENCAO_NOMES)
