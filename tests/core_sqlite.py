"""Banco SQLite com as tabelas reais do core/diretorio, para testes sem PostgreSQL."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Integer, MetaData, create_engine, text
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import DefaultClause


def motor_sqlite(base: Any, esquema: str) -> Any:
    opcoes = {"schema_translate_map": {esquema: None}}
    motor = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options=opcoes,
    )
    metadados = MetaData()
    for tabela in base.metadata.tables.values():
        copia = tabela.to_metadata(metadados)
        for restricao in [c for c in copia.constraints if isinstance(c, CheckConstraint)]:
            copia.constraints.discard(restricao)
        for indice in list(copia.indexes):
            copia.indexes.discard(indice)
        for coluna in copia.columns:
            if coluna.primary_key and isinstance(coluna.type, BigInteger):
                coluna.type = Integer()  # SQLite so autoincrementa INTEGER PRIMARY KEY
            padrao = coluna.server_default
            if padrao is not None and "TIME ZONE" in str(getattr(padrao, "arg", "")).upper():
                coluna.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    metadados.create_all(motor)
    return motor
