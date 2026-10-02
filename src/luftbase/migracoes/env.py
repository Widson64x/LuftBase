"""Ambiente Alembic interno do LuftBase."""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, Engine, engine_from_config, pool

from luftbase.persistencia import core as _modelos_core  # noqa: F401
from luftbase.persistencia.base import BaseLuft

config = context.config
target_metadata = BaseLuft.metadata


def _configurar_contexto(conexao: Connection) -> None:
    context.configure(
        connection=conexao,
        target_metadata=target_metadata,
        include_schemas=True,
        version_table="alembic_version",
        version_table_schema="core",
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
    )


def executar_offline() -> None:
    """Produz SQL sem abrir uma conexao."""

    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        version_table_schema="core",
    )
    with context.begin_transaction():
        context.run_migrations()


def executar_online() -> None:
    """Usa a conexao fornecida pelo comando ou cria uma engine temporaria."""

    conexao_existente = config.attributes.get("connection")
    if isinstance(conexao_existente, Connection):
        _configurar_contexto(conexao_existente)
        with context.begin_transaction():
            context.run_migrations()
        return

    conectavel: Engine = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        with conectavel.connect() as conexao:
            _configurar_contexto(conexao)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        conectavel.dispose()


if context.is_offline_mode():
    executar_offline()
else:
    executar_online()
