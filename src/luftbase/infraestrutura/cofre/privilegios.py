"""Leitura e replica de privilegios diretos de uma role PostgreSQL no banco atual.

Um banco criado com `CREATE DATABASE ... TEMPLATE` herda os GRANTs dos objetos, mas eles
citam as roles do ambiente de origem. Para uma role nova funcionar no banco clonado sem
ser membro da role de origem (o que a ligaria aos mesmos privilegios no banco de origem),
os privilegios diretos dela sao lidos do catalogo e reaplicados a role nova.

Cobre schemas, tabelas/views/sequences, funcoes/procedures e privilegios padrao
(`ALTER DEFAULT PRIVILEGES`). Privilegios em colunas e em outros tipos de objeto nao sao
replicados.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from luftbase.nucleo.excecoes import ErroConfiguracao

_PRIVILEGIO_VALIDO = re.compile(r"^[A-Z][A-Z ]{0,30}$")
_OBJETOS_PADRAO = {
    "r": "TABLES",
    "S": "SEQUENCES",
    "f": "FUNCTIONS",
    "T": "TYPES",
    "n": "SCHEMAS",
}

_FILTRO = "n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'"
_GRANTEE = "(SELECT oid FROM pg_catalog.pg_roles WHERE rolname = %s)"


@dataclass(frozen=True, slots=True)
class Privilegio:
    """Um privilegio direto de uma role sobre um objeto ou um padrao de objetos futuros."""

    categoria: str  # SCHEMA, TABLE, SEQUENCE, FUNCTION, PROCEDURE ou DEFAULT
    objeto: tuple[str, ...]
    privilegio: str
    com_grant: bool = False


def consultar_privilegios(cursor: Any, role: str) -> frozenset[Privilegio]:
    """Privilegios diretos da role no banco da conexao atual."""

    encontrados: set[Privilegio] = set()

    cursor.execute(
        f"""
        SELECT n.nspname, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_namespace n
        CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) a
        WHERE a.grantee = {_GRANTEE} AND {_FILTRO}
        """,
        (role,),
    )
    for schema, privilegio, grant in cursor.fetchall():
        encontrados.add(Privilegio("SCHEMA", (schema,), privilegio, bool(grant)))

    cursor.execute(
        f"""
        SELECT n.nspname, c.relname, c.relkind, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
        WHERE a.grantee = {_GRANTEE}
          AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S') AND {_FILTRO}
        """,
        (role,),
    )
    for schema, nome, tipo, privilegio, grant in cursor.fetchall():
        categoria = "SEQUENCE" if tipo == "S" else "TABLE"
        encontrados.add(Privilegio(categoria, (schema, nome), privilegio, bool(grant)))

    cursor.execute(
        f"""
        SELECT n.nspname, p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid),
               p.prokind, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) a
        WHERE a.grantee = {_GRANTEE} AND {_FILTRO}
        """,
        (role,),
    )
    for schema, nome, argumentos, tipo, privilegio, grant in cursor.fetchall():
        categoria = "PROCEDURE" if tipo == "p" else "FUNCTION"
        encontrados.add(Privilegio(categoria, (schema, nome, argumentos), privilegio, bool(grant)))

    cursor.execute(
        f"""
        SELECT pg_catalog.pg_get_userbyid(d.defaclrole), COALESCE(n.nspname, ''),
               d.defaclobjtype, a.privilege_type, a.is_grantable
        FROM pg_catalog.pg_default_acl d
        LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a
        WHERE a.grantee = {_GRANTEE}
        """,
        (role,),
    )
    for dono, schema, tipo, privilegio, grant in cursor.fetchall():
        if tipo not in _OBJETOS_PADRAO:
            continue
        encontrados.add(Privilegio("DEFAULT", (dono, schema, tipo), privilegio, bool(grant)))

    return frozenset(encontrados)


def usuario_atual(cursor: Any) -> str:
    """Usuario da conexao administrativa."""

    cursor.execute("SELECT current_user")
    return str(cursor.fetchone()[0])


def pode_criar_roles(cursor: Any) -> bool:
    """Se o usuario da conexao pode executar CREATE ROLE (superuser ou CREATEROLE)."""

    cursor.execute(
        "SELECT rolsuper OR rolcreaterole FROM pg_catalog.pg_roles WHERE rolname = current_user"
    )
    linha = cursor.fetchone()
    return bool(linha and linha[0])


def separar_padroes(
    privilegios: Iterable[Privilegio], dono_atual: str
) -> tuple[list[Privilegio], list[Privilegio]]:
    """Separa os privilegios aplicaveis dos padroes de outro dono (exigem ser aquele dono)."""

    aplicaveis: list[Privilegio] = []
    ignorados: list[Privilegio] = []
    for item in sorted(privilegios, key=lambda p: (p.categoria, p.objeto, p.privilegio)):
        if item.categoria == "DEFAULT" and item.objeto[0] != dono_atual:
            ignorados.append(item)
        else:
            aplicaveis.append(item)
    return aplicaveis, ignorados


def comando_grant(item: Privilegio, destino: str) -> Any:
    """Monta o GRANT (ou ALTER DEFAULT PRIVILEGES) equivalente, com identificadores citados."""

    from psycopg import sql

    if not _PRIVILEGIO_VALIDO.fullmatch(item.privilegio):
        raise ErroConfiguracao(f"Privilegio inesperado no catalogo: {item.privilegio!r}.")
    privilegio = sql.SQL(item.privilegio)
    alvo = sql.Identifier(destino)
    opcao = sql.SQL(" WITH GRANT OPTION") if item.com_grant else sql.SQL("")

    if item.categoria == "SCHEMA":
        modelo = sql.SQL("GRANT {} ON SCHEMA {} TO {}{}")
        return modelo.format(privilegio, sql.Identifier(item.objeto[0]), alvo, opcao)
    if item.categoria in {"TABLE", "SEQUENCE"}:
        modelo = sql.SQL("GRANT {} ON " + item.categoria + " {}.{} TO {}{}")
        return modelo.format(
            privilegio, sql.Identifier(item.objeto[0]), sql.Identifier(item.objeto[1]), alvo, opcao
        )
    if item.categoria in {"FUNCTION", "PROCEDURE"}:
        modelo = sql.SQL("GRANT {} ON " + item.categoria + " {}.{}({}) TO {}{}")
        return modelo.format(
            privilegio,
            sql.Identifier(item.objeto[0]),
            sql.Identifier(item.objeto[1]),
            sql.SQL(item.objeto[2]),
            alvo,
            opcao,
        )
    if item.categoria == "DEFAULT":
        dono, schema, tipo = item.objeto
        escopo = sql.SQL(" IN SCHEMA {}").format(sql.Identifier(schema)) if schema else sql.SQL("")
        modelo = sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {}{} GRANT {} ON "
            + _OBJETOS_PADRAO[tipo]
            + " TO {}{}"
        )
        return modelo.format(sql.Identifier(dono), escopo, privilegio, alvo, opcao)
    raise ErroConfiguracao(f"Categoria de privilegio desconhecida: {item.categoria!r}.")


def resumo_por_categoria(privilegios: Iterable[Privilegio]) -> dict[str, int]:
    """Contagem por categoria, para exibir no plano."""

    contagem: dict[str, int] = {}
    for item in privilegios:
        contagem[item.categoria] = contagem.get(item.categoria, 0) + 1
    return dict(sorted(contagem.items()))


def faltantes(esperados: Iterable[Privilegio], efetivos: Iterable[Privilegio]) -> list[Privilegio]:
    """Privilegios esperados que a role nova nao recebeu (ex.: faltou ser dono do objeto)."""

    recebidos = {(p.categoria, p.objeto, p.privilegio) for p in efetivos}
    return [p for p in esperados if (p.categoria, p.objeto, p.privilegio) not in recebidos]


__all__ = [
    "Privilegio",
    "comando_grant",
    "consultar_privilegios",
    "faltantes",
    "pode_criar_roles",
    "resumo_por_categoria",
    "separar_padroes",
    "usuario_atual",
]
