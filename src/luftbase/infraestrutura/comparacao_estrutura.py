"""Comparacao de estrutura entre dois ambientes e geracao do SQL para igualar o destino.

Fluxo de uso: o dev cria tabelas no schema do sistema em desenvolvimento; quando o sistema existe em
homologacao (cadastrado pelo Workspace, que cria o schema e a role), este modulo le a estrutura dos
dois lados e escreve um `.sql` que cria no destino o que so existe na origem.

Garantias:

- So leitura nos dois bancos: apenas `SELECT` no catalogo (`pg_catalog`); nenhum dado de tabela e lido.
- O resultado e um arquivo para revisao. Nada e aplicado por este modulo.
- O script so cria: `CREATE ... IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS` e constraints protegidas por
  verificacao no catalogo, entao e seguro repetir. Nunca emite `DROP`, nem altera tipo, nulidade ou
  valor padrao: essas divergencias vao para o relatorio como "revisao manual".
- Tudo corre em uma unica transacao (`BEGIN`/`COMMIT`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SCHEMAS_DO_SISTEMA = ("information_schema", "public")
_SEQUENCIA = re.compile(r"nextval\('([^']+)'")


@dataclass(frozen=True, slots=True)
class Coluna:
    nome: str
    tipo: str
    nao_nulo: bool
    padrao: str | None = None
    identidade: str = ""  # "" | "a" (ALWAYS) | "d" (BY DEFAULT)
    gerada: str = ""  # "" | "s" (STORED)


@dataclass(slots=True)
class Tabela:
    nome: str
    colunas: dict[str, Coluna] = field(default_factory=dict)
    restricoes: dict[str, tuple[str, str]] = field(
        default_factory=dict
    )  # nome -> (tipo, definicao)
    indices: dict[str, str] = field(default_factory=dict)  # nome -> definicao


@dataclass(slots=True)
class Estrutura:
    """Estrutura de um schema: so metadados do catalogo, nunca dados."""

    schema: str
    existe: bool = False
    tabelas: dict[str, Tabela] = field(default_factory=dict)
    sequencias: set[str] = field(default_factory=set)


@dataclass(frozen=True, slots=True)
class Diferenca:
    """Uma divergencia; `automatica` diz se o script resolve ou se exige decisao humana."""

    categoria: str
    descricao: str
    automatica: bool


@dataclass(slots=True)
class Resultado:
    schema: str
    diferencas: list[Diferenca] = field(default_factory=list)
    script: str = ""

    @property
    def iguais(self) -> bool:
        return not self.diferencas

    @property
    def manuais(self) -> list[Diferenca]:
        return [d for d in self.diferencas if not d.automatica]


def citar(nome: str) -> str:
    """Identificador entre aspas, com escape; nomes vem do catalogo mas o script e revisado por gente."""

    return '"' + nome.replace('"', '""') + '"'


def _literal(texto: str) -> str:
    return "'" + texto.replace("'", "''") + "'"


# --- Leitura --------------------------------------------------------------------------------


def listar_schemas(conexao: Any) -> list[str]:
    """Schemas de usuario: fora os do PostgreSQL, `public` e o `core` (que evolui por Alembic)."""

    with conexao.cursor() as cursor:
        cursor.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg\\_%%' "
            "AND nspname <> ALL(%s) AND nspname <> 'core' ORDER BY 1",
            (list(SCHEMAS_DO_SISTEMA),),
        )
        return [linha[0] for linha in cursor.fetchall()]


def ler_estrutura(conexao: Any, schema: str) -> Estrutura:
    """Le tabelas, colunas, constraints, indices e sequencias de um schema."""

    estrutura = Estrutura(schema)
    with conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,))
        if cursor.fetchone() is None:
            return estrutura
        estrutura.existe = True

        cursor.execute(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') ORDER BY 1",
            (schema,),
        )
        for (nome,) in cursor.fetchall():
            estrutura.tabelas[nome] = Tabela(nome)

        cursor.execute(
            "SELECT c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull, "
            "pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated "
            "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum "
            "WHERE n.nspname = %s AND c.relkind IN ('r', 'p') AND a.attnum > 0 "
            "AND NOT a.attisdropped ORDER BY c.relname, a.attnum",
            (schema,),
        )
        for tabela, nome, tipo, nao_nulo, padrao, identidade, gerada in cursor.fetchall():
            estrutura.tabelas[tabela].colunas[nome] = Coluna(
                nome, tipo, bool(nao_nulo), padrao, str(identidade or ""), str(gerada or "")
            )

        cursor.execute(
            "SELECT c.relname, k.conname, k.contype, pg_get_constraintdef(k.oid) "
            "FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND k.contype IN ('p', 'u', 'f', 'c') ORDER BY 1, 2",
            (schema,),
        )
        for tabela, nome, tipo, definicao in cursor.fetchall():
            if tabela in estrutura.tabelas:
                estrutura.tabelas[tabela].restricoes[nome] = (str(tipo), definicao)

        cursor.execute(
            "SELECT c.relname, i.relname, pg_get_indexdef(x.indexrelid) "
            "FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid "
            "JOIN pg_class c ON c.oid = x.indrelid JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND NOT EXISTS (SELECT 1 FROM pg_constraint k "
            "WHERE k.conindid = x.indexrelid AND k.contype IN ('p', 'u', 'x')) ORDER BY 1, 2",
            (schema,),
        )
        for tabela, nome, definicao in cursor.fetchall():
            if tabela in estrutura.tabelas:
                estrutura.tabelas[tabela].indices[nome] = definicao

        cursor.execute("SELECT sequencename FROM pg_sequences WHERE schemaname = %s", (schema,))
        estrutura.sequencias = {linha[0] for linha in cursor.fetchall()}
    return estrutura


def role_existe(conexao: Any, role: str) -> bool:
    with conexao.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        return cursor.fetchone() is not None


def revisao_alembic(conexao: Any) -> str | None:
    """Revisao do core registrada no banco, ou `None` se o core ainda nao foi migrado."""

    with conexao.cursor() as cursor:
        cursor.execute("SELECT to_regclass('core.alembic_version')")
        if cursor.fetchone()[0] is None:
            return None
        cursor.execute("SELECT version_num FROM core.alembic_version")
        linha = cursor.fetchone()
    return str(linha[0]) if linha else None


# --- Comparacao e script --------------------------------------------------------------------


def _definicao_coluna(coluna: Coluna) -> str:
    partes = [citar(coluna.nome), coluna.tipo]
    if coluna.gerada == "s" and coluna.padrao:
        partes.append(f"GENERATED ALWAYS AS ({coluna.padrao}) STORED")
    elif coluna.identidade:
        modo = "ALWAYS" if coluna.identidade == "a" else "BY DEFAULT"
        partes.append(f"GENERATED {modo} AS IDENTITY")
    elif coluna.padrao is not None:
        partes.append(f"DEFAULT {coluna.padrao}")
    if coluna.nao_nulo and not coluna.identidade:
        partes.append("NOT NULL")
    return " ".join(partes)


def _qual(schema: str, nome: str) -> str:
    return f"{citar(schema)}.{citar(nome)}"


def _restricao_protegida(schema: str, tabela: str, nome: str, definicao: str) -> str:
    """`ADD CONSTRAINT` so se ainda nao existir: o script pode ser executado mais de uma vez."""

    return (
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_constraint k "
        "JOIN pg_namespace n ON n.oid = k.connamespace "
        f"WHERE n.nspname = {_literal(schema)} AND k.conname = {_literal(nome)}) THEN "
        f"ALTER TABLE {_qual(schema, tabela)} ADD CONSTRAINT {citar(nome)} {definicao}; "
        "END IF; END $$;"
    )


def _sequencias_usadas(tabela: Tabela) -> set[str]:
    nomes: set[str] = set()
    for coluna in tabela.colunas.values():
        achado = _SEQUENCIA.search(coluna.padrao or "")
        if achado:
            nomes.add(achado.group(1).split(".")[-1].strip('"'))
    return nomes


def comparar(
    origem: Estrutura,
    destino: Estrutura,
    *,
    role_destino: str | None = None,
    role_destino_existe: bool = False,
    nome_origem: str = "origem",
    nome_destino: str = "destino",
    agora: Callable[[], datetime] = datetime.now,
) -> Resultado:
    """Diferencas e o script que cria no `destino` o que so existe na `origem`."""

    resultado = Resultado(origem.schema)
    schema = origem.schema
    diferencas = resultado.diferencas
    ddl: list[str] = []
    fks: list[str] = []
    indices: list[str] = []
    tabelas_com_grant = False

    if not origem.existe:
        diferencas.append(
            Diferenca("schema", f"O schema {schema!r} nao existe em {nome_origem}.", False)
        )
        return resultado
    if not destino.existe:
        diferencas.append(
            Diferenca(
                "schema",
                f"O schema {schema!r} nao existe em {nome_destino}. Cadastre o sistema no Workspace "
                "(ele cria schema e role); o script cria o schema se faltar, mas sem a role.",
                True,
            )
        )
        ddl.append(f"CREATE SCHEMA IF NOT EXISTS {citar(schema)};")

    for nome_sequencia in sorted(
        {s for t in origem.tabelas.values() for s in _sequencias_usadas(t)} - destino.sequencias
    ):
        diferencas.append(Diferenca("sequencia", f"Sequencia {nome_sequencia} ausente.", True))
        ddl.append(f"CREATE SEQUENCE IF NOT EXISTS {_qual(schema, nome_sequencia)};")

    for nome, tabela in origem.tabelas.items():
        existente = destino.tabelas.get(nome)
        if existente is None:
            diferencas.append(Diferenca("tabela", f"Tabela {nome} ausente.", True))
            tabelas_com_grant = True
            colunas = ",\n    ".join(_definicao_coluna(c) for c in tabela.colunas.values())
            ddl.append(f"CREATE TABLE IF NOT EXISTS {_qual(schema, nome)} (\n    {colunas}\n);")
            for sequencia in sorted(_sequencias_usadas(tabela)):
                dona = next(
                    (c.nome for c in tabela.colunas.values() if sequencia in (c.padrao or "")), None
                )
                if dona:
                    ddl.append(
                        f"ALTER SEQUENCE {_qual(schema, sequencia)} "
                        f"OWNED BY {_qual(schema, nome)}.{citar(dona)};"
                    )
            existente = Tabela(nome)
        else:
            for coluna in tabela.colunas.values():
                par = existente.colunas.get(coluna.nome)
                if par is None:
                    aviso = ""
                    if coluna.nao_nulo and coluna.padrao is None and not coluna.identidade:
                        aviso = " -- ATENCAO: NOT NULL sem padrao falha se a tabela tiver linhas"
                        diferencas.append(
                            Diferenca(
                                "coluna",
                                f"{nome}.{coluna.nome} e NOT NULL sem valor padrao: "
                                "confira se a tabela de destino esta vazia.",
                                False,
                            )
                        )
                    diferencas.append(
                        Diferenca("coluna", f"Coluna {nome}.{coluna.nome} ausente.", True)
                    )
                    ddl.append(
                        f"ALTER TABLE {_qual(schema, nome)} ADD COLUMN IF NOT EXISTS "
                        f"{_definicao_coluna(coluna)};{aviso}"
                    )
                elif (par.tipo, par.nao_nulo, par.padrao) != (
                    coluna.tipo,
                    coluna.nao_nulo,
                    coluna.padrao,
                ) and not (par.identidade or coluna.identidade):
                    diferencas.append(
                        Diferenca(
                            "coluna",
                            f"{nome}.{coluna.nome} difere: {nome_origem}="
                            f"{_resumo(coluna)} / {nome_destino}={_resumo(par)} (revisao manual).",
                            False,
                        )
                    )

        for nome_restricao, (tipo, definicao) in tabela.restricoes.items():
            par_restricao = existente.restricoes.get(nome_restricao)
            if par_restricao is None:
                diferencas.append(
                    Diferenca("restricao", f"Constraint {nome}.{nome_restricao} ausente.", True)
                )
                destino_lista = fks if tipo == "f" else ddl
                destino_lista.append(_restricao_protegida(schema, nome, nome_restricao, definicao))
            elif par_restricao[1] != definicao:
                diferencas.append(
                    Diferenca(
                        "restricao",
                        f"Constraint {nome}.{nome_restricao} difere (revisao manual): "
                        f"{definicao} / {par_restricao[1]}.",
                        False,
                    )
                )
        for nome_indice, definicao in tabela.indices.items():
            par_indice = existente.indices.get(nome_indice)
            if par_indice is None:
                diferencas.append(
                    Diferenca("indice", f"Indice {nome}.{nome_indice} ausente.", True)
                )
                indices.append(
                    re.sub(r"^CREATE (UNIQUE )?INDEX ", r"CREATE \1INDEX IF NOT EXISTS ", definicao)
                    + ";"
                )
            elif par_indice != definicao:
                diferencas.append(
                    Diferenca(
                        "indice", f"Indice {nome}.{nome_indice} difere (revisao manual).", False
                    )
                )

    for nome in destino.tabelas:
        if nome not in origem.tabelas:
            diferencas.append(
                Diferenca(
                    "tabela",
                    f"Tabela {nome} existe so em {nome_destino} (nao e removida).",
                    False,
                )
            )

    grants: list[str] = []
    if (tabelas_com_grant or ddl) and role_destino:
        if role_destino_existe:
            papel = citar(role_destino)
            grants = [
                f"GRANT ALL ON SCHEMA {citar(schema)} TO {papel};",
                f"GRANT ALL ON ALL TABLES IN SCHEMA {citar(schema)} TO {papel};",
                f"GRANT ALL ON ALL SEQUENCES IN SCHEMA {citar(schema)} TO {papel};",
            ]
        else:
            diferencas.append(
                Diferenca(
                    "permissao",
                    f"A role {role_destino!r} nao existe em {nome_destino}: o script nao concede "
                    "acesso. Cadastre o sistema no Workspace e gere o script de novo.",
                    False,
                )
            )

    corpo = [*ddl, *indices, *fks, *grants]
    if corpo:
        cabecalho = [
            f"-- Estrutura do schema {schema}: {nome_origem} -> {nome_destino}",
            f"-- Gerado em {agora():%Y-%m-%d %H:%M} pelo LuftBase. REVISE antes de executar.",
            "-- So cria objetos que faltam; nao apaga nem altera tipo, nulidade ou padrao.",
            "BEGIN;",
        ]
        resultado.script = "\n".join([*cabecalho, "", *corpo, "", "COMMIT;", ""])
    return resultado


def _resumo(coluna: Coluna) -> str:
    nulo = "NOT NULL" if coluna.nao_nulo else "NULL"
    padrao = f" DEFAULT {coluna.padrao}" if coluna.padrao is not None else ""
    return f"{coluna.tipo} {nulo}{padrao}"


def comparar_schemas(
    conexao_origem: Any,
    conexao_destino: Any,
    schemas: Sequence[str],
    *,
    role_destino: Callable[[str], str | None] = lambda _schema: None,
    nome_origem: str = "origem",
    nome_destino: str = "destino",
) -> list[Resultado]:
    """Compara cada schema pedido; so le. A role do destino vem de `role_destino(schema)`."""

    resultados: list[Resultado] = []
    for schema in schemas:
        role = role_destino(schema)
        resultados.append(
            comparar(
                ler_estrutura(conexao_origem, schema),
                ler_estrutura(conexao_destino, schema),
                role_destino=role,
                role_destino_existe=bool(role) and role_existe(conexao_destino, str(role)),
                nome_origem=nome_origem,
                nome_destino=nome_destino,
            )
        )
    return resultados


__all__ = [
    "Coluna",
    "Diferenca",
    "Estrutura",
    "Resultado",
    "Tabela",
    "citar",
    "comparar",
    "comparar_schemas",
    "ler_estrutura",
    "listar_schemas",
    "revisao_alembic",
    "role_existe",
]
