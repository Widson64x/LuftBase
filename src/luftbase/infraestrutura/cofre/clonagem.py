"""Clonagem de um ambiente PostgreSQL/Vault para outro (ex.: producao -> homologacao).

O que o `CREATE DATABASE ... TEMPLATE` copia e o que ele NAO copia:
- copia schemas, tabelas, dados e os GRANTs de objetos (que citam roles pelo nome);
- nao copia roles (usuarios e senhas), que pertencem ao cluster inteiro.

Este modulo cria o que falta, sem tocar nas roles do ambiente de origem:
- roles de login dedicadas ao destino (`luft_workspace_app` -> `luft_workspace_hml_app`),
  com senha aleatoria propria, que existe somente no Vault do destino;
- as mesmas pertencas a roles funcionais (`luft_workspace_rw`), pois os GRANTs copiados
  referenciam essas roles;
- os segredos `conexoes/{alias}` (apontando para o banco destino) e `sistemas/{id}`.

Nenhuma funcao devolve ou imprime senhas.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from luftbase.configuracao.ambientes import normalizar_ambiente
from luftbase.infraestrutura.cofre.privilegios import (
    Privilegio,
    comando_grant,
    consultar_privilegios,
    faltantes,
    separar_padroes,
    usuario_atual,
)
from luftbase.nucleo.excecoes import ErroConfiguracao

_SUFIXOS_AMBIENTE = {"desenvolvimento": "dev", "homologacao": "hml", "producao": "prd"}
_NOME_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_NOME_BANCO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def raiz_bancos(ambiente: str, namespace: str = "luft") -> str:
    """Raiz do Vault para os bancos PostgreSQL de um ambiente."""

    return f"{namespace}/{normalizar_ambiente(ambiente).value}/bancos/postgresql"


def sufixo_do_ambiente(ambiente: str) -> str:
    """Sufixo curto usado nos nomes de role do ambiente (`hml`, `dev`, `prd`)."""

    return _SUFIXOS_AMBIENTE[normalizar_ambiente(ambiente).value]


def derivar_usuario_destino(usuario_origem: str, sufixo: str) -> str:
    """`luft_workspace_app` + `hml` -> `luft_workspace_hml_app` (ou `x_hml` sem `_app`)."""

    base = usuario_origem[:-4] if usuario_origem.endswith("_app") else usuario_origem
    final = "_app" if usuario_origem.endswith("_app") else ""
    novo = f"{base}_{sufixo}{final}"
    if novo == usuario_origem or not _NOME_ROLE.fullmatch(novo):
        raise ErroConfiguracao(
            f"Nao foi possivel derivar uma role de destino valida a partir de {usuario_origem!r}."
        )
    return novo


@dataclass(frozen=True, slots=True)
class SistemaClonado:
    """Um segredo `sistemas/{id}` do destino, sem a senha (gerada na execucao)."""

    sistema_id: str
    caminho_origem: str
    caminho_destino: str
    usuario_origem: str
    usuario_destino: str
    campos: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class PlanoClonagem:
    """Tudo o que sera criado; seguro para imprimir (nao contem senhas)."""

    ambiente_origem: str
    ambiente_destino: str
    banco_origem: str
    banco_destino: str
    host: str
    alias_conexao: str
    caminho_conexao_destino: str
    campos_conexao: Mapping[str, str]
    sistemas: tuple[SistemaClonado, ...]
    grupos: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def roles_destino(self) -> tuple[str, ...]:
        return tuple(sorted({s.usuario_destino for s in self.sistemas}))

    @property
    def caminhos_destino(self) -> tuple[str, ...]:
        return (self.caminho_conexao_destino, *(s.caminho_destino for s in self.sistemas))

    def com_grupos(self, grupos_por_origem: Mapping[str, Iterable[str]]) -> PlanoClonagem:
        """Associa a cada role de destino as roles funcionais da role de origem."""

        grupos = {
            s.usuario_destino: tuple(sorted(grupos_por_origem.get(s.usuario_origem, ())))
            for s in self.sistemas
        }
        return PlanoClonagem(
            self.ambiente_origem,
            self.ambiente_destino,
            self.banco_origem,
            self.banco_destino,
            self.host,
            self.alias_conexao,
            self.caminho_conexao_destino,
            self.campos_conexao,
            self.sistemas,
            grupos,
        )


def ler_segredos_postgresql(
    cliente: Any, mount: str, ambiente: str, namespace: str = "luft"
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    """Le `conexoes/*` e `sistemas/*` do ambiente. Devolve (conexoes, sistemas)."""

    from hvac import exceptions as excecoes_vault

    raiz = raiz_bancos(ambiente, namespace)

    def ler_pasta(pasta: str) -> dict[str, dict[str, str]]:
        try:
            chaves = cliente.secrets.kv.v2.list_secrets(path=f"{raiz}/{pasta}", mount_point=mount)[
                "data"
            ]["keys"]
        except excecoes_vault.InvalidPath:
            return {}
        segredos: dict[str, dict[str, str]] = {}
        for chave in sorted(str(c) for c in chaves if not str(c).endswith("/")):
            resposta = cliente.secrets.kv.v2.read_secret_version(
                path=f"{raiz}/{pasta}/{chave}",
                mount_point=mount,
                raise_on_deleted_version=True,
            )
            segredos[chave] = {k: str(v) for k, v in resposta["data"]["data"].items()}
        return segredos

    return ler_pasta("conexoes"), ler_pasta("sistemas")


def montar_plano(
    conexoes: Mapping[str, Mapping[str, str]],
    sistemas: Mapping[str, Mapping[str, str]],
    *,
    ambiente_origem: str,
    ambiente_destino: str,
    banco_destino: str,
    namespace: str = "luft",
    host_destino: str | None = None,
    alias: str | None = None,
    sufixo_role: str | None = None,
) -> PlanoClonagem:
    """Calcula o que sera criado no destino. Nao acessa Vault nem banco."""

    origem = normalizar_ambiente(ambiente_origem).value
    destino = normalizar_ambiente(ambiente_destino).value
    if origem == destino:
        raise ErroConfiguracao("Origem e destino devem ser ambientes diferentes.")
    if not _NOME_BANCO.fullmatch(banco_destino):
        raise ErroConfiguracao(f"Nome de banco de destino invalido: {banco_destino!r}.")
    if not conexoes:
        raise ErroConfiguracao(f"Nenhuma conexao encontrada em {raiz_bancos(origem, namespace)}.")
    if not sistemas:
        raise ErroConfiguracao(f"Nenhum sistema encontrado em {raiz_bancos(origem, namespace)}.")

    if alias is None:
        if len(conexoes) > 1:
            raise ErroConfiguracao(
                "Ha mais de uma conexao na origem (" + ", ".join(sorted(conexoes)) + "); "
                "informe qual clonar com --conexao."
            )
        alias = next(iter(conexoes))
    if alias not in conexoes:
        raise ErroConfiguracao(f"Conexao {alias!r} nao existe na origem.")

    sufixo = sufixo_role or sufixo_do_ambiente(destino)
    base_origem = raiz_bancos(origem, namespace)
    base_destino = raiz_bancos(destino, namespace)

    campos = dict(conexoes[alias])
    banco_origem = campos.get("nome_banco", "")
    if not banco_origem:
        raise ErroConfiguracao(f"A conexao {alias!r} nao informa nome_banco.")
    if host_destino:
        campos["host"] = host_destino
    campos["nome_banco"] = banco_destino
    host = campos.get("host", "")
    if not host:
        raise ErroConfiguracao(f"A conexao {alias!r} nao informa host.")
    if banco_origem == banco_destino and host == conexoes[alias].get("host"):
        raise ErroConfiguracao(
            "O banco de destino e o mesmo da origem no mesmo servidor; informe outro banco."
        )

    clonados: list[SistemaClonado] = []
    for sistema_id, dados in sorted(sistemas.items(), key=lambda par: par[0]):
        if dados.get("conexao") != alias:
            raise ErroConfiguracao(
                f"O sistema {sistema_id} usa a conexao {dados.get('conexao')!r}, "
                f"diferente de {alias!r}; clone cada conexao separadamente (--conexao)."
            )
        usuario = dados.get("usuario", "")
        if not usuario:
            raise ErroConfiguracao(f"O segredo do sistema {sistema_id} nao informa usuario.")
        campos_sistema = {k: v for k, v in dados.items() if k not in {"senha", "usuario"}}
        usuario_destino = derivar_usuario_destino(usuario, sufixo)
        clonados.append(
            SistemaClonado(
                sistema_id=str(sistema_id),
                caminho_origem=f"{base_origem}/sistemas/{sistema_id}",
                caminho_destino=f"{base_destino}/sistemas/{sistema_id}",
                usuario_origem=usuario,
                usuario_destino=usuario_destino,
                campos=campos_sistema,
            )
        )

    return PlanoClonagem(
        ambiente_origem=origem,
        ambiente_destino=destino,
        banco_origem=banco_origem,
        banco_destino=banco_destino,
        host=host,
        alias_conexao=alias,
        caminho_conexao_destino=f"{base_destino}/conexoes/{alias}",
        campos_conexao=campos,
        sistemas=tuple(clonados),
    )


def gerar_senhas(plano: PlanoClonagem) -> dict[str, str]:
    """Uma senha aleatoria independente por role de destino."""

    return {role: secrets.token_urlsafe(32) for role in plano.roles_destino}


def caminhos_existentes(
    cliente: Any, mount: str, caminhos: Iterable[str], existe: Callable[[Any, str, str], bool]
) -> list[str]:
    """Caminhos do destino que ja possuem segredo."""

    return [c for c in caminhos if existe(cliente, mount, c)]


def gravar_segredos_destino(
    cliente: Any,
    mount: str,
    plano: PlanoClonagem,
    senhas: Mapping[str, str],
    *,
    substituir: bool = False,
) -> None:
    """Grava conexao e sistemas no Vault de destino.

    Por padrao usa CAS 0 e recusa sobrescrever; com `substituir` cria uma nova versao do
    segredo (o KV v2 preserva as anteriores).
    """

    opcoes: dict[str, Any] = {} if substituir else {"cas": 0}
    cliente.secrets.kv.v2.create_or_update_secret(
        path=plano.caminho_conexao_destino,
        mount_point=mount,
        secret=dict(plano.campos_conexao),
        **opcoes,
    )
    for sistema in plano.sistemas:
        cliente.secrets.kv.v2.create_or_update_secret(
            path=sistema.caminho_destino,
            mount_point=mount,
            secret={
                **sistema.campos,
                "usuario": sistema.usuario_destino,
                "senha": senhas[sistema.usuario_destino],
            },
            **opcoes,
        )


def consultar_grupos(cursor: Any, usuarios: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Roles funcionais (pertencas) de cada role de origem."""

    cursor.execute(
        """
        SELECT membro.rolname, grupo.rolname
        FROM pg_catalog.pg_auth_members pertence
        JOIN pg_catalog.pg_roles membro ON membro.oid = pertence.member
        JOIN pg_catalog.pg_roles grupo ON grupo.oid = pertence.roleid
        WHERE membro.rolname = ANY (%s)
        """,
        (list(usuarios),),
    )
    grupos: dict[str, list[str]] = {}
    for membro, grupo in cursor.fetchall():
        grupos.setdefault(membro, []).append(grupo)
    return {membro: tuple(sorted(lista)) for membro, lista in grupos.items()}


def consultar_roles_existentes(cursor: Any, roles: Iterable[str]) -> set[str]:
    """Roles do conjunto que ja existem no cluster."""

    cursor.execute(
        "SELECT rolname FROM pg_catalog.pg_roles WHERE rolname = ANY (%s)", (list(roles),)
    )
    return {linha[0] for linha in cursor.fetchall()}


def criar_roles(
    conexao: Any,
    plano: PlanoClonagem,
    senhas: Mapping[str, str],
    privilegios: Mapping[str, Iterable[Privilegio]] | None = None,
) -> dict[str, list[Privilegio]]:
    """Cria as roles de destino, replica pertencas e privilegios e libera o banco.

    Tudo em uma transacao: se qualquer comando falhar, nenhuma role e criada. Nunca altera
    uma role existente: quem chama ja garantiu que elas nao existem. `privilegios` mapeia a
    role de DESTINO para os privilegios diretos copiados da role de origem.

    Devolve, por role, os privilegios que a role nova nao recebeu (normalmente porque o
    usuario administrativo nao e dono do objeto e nao tem GRANT OPTION).
    """

    from psycopg import sql

    privilegios = privilegios or {}
    nao_concedidos: dict[str, list[Privilegio]] = {}
    with conexao.transaction(), conexao.cursor() as cursor:
        dono_atual = usuario_atual(cursor)
        for role in plano.roles_destino:
            verificador = conexao.pgconn.encrypt_password(
                senhas[role].encode(), role.encode(), b"scram-sha-256"
            ).decode()
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(verificador)
                )
            )
            for grupo in plano.grupos.get(role, ()):
                cursor.execute(
                    sql.SQL("GRANT {} TO {}").format(sql.Identifier(grupo), sql.Identifier(role))
                )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(plano.banco_destino), sql.Identifier(role)
                )
            )
            aplicaveis, _ignorados = separar_padroes(privilegios.get(role, ()), dono_atual)
            for item in aplicaveis:
                cursor.execute(comando_grant(item, role))
            ausentes = faltantes(aplicaveis, consultar_privilegios(cursor, role))
            if ausentes:
                nao_concedidos[role] = ausentes
    return nao_concedidos


def roles_que_alcancam_a_origem(cursor: Any, plano: PlanoClonagem) -> list[str]:
    """Roles de destino que ainda conseguem conectar no banco de origem (isolamento)."""

    alcancam: list[str] = []
    for role in plano.roles_destino:
        cursor.execute(
            "SELECT pg_catalog.has_database_privilege(%s, %s, 'CONNECT')",
            (role, plano.banco_origem),
        )
        linha = cursor.fetchone()
        if linha and linha[0]:
            alcancam.append(role)
    return alcancam


__all__ = [
    "PlanoClonagem",
    "SistemaClonado",
    "caminhos_existentes",
    "consultar_grupos",
    "consultar_roles_existentes",
    "criar_roles",
    "derivar_usuario_destino",
    "gerar_senhas",
    "gravar_segredos_destino",
    "ler_segredos_postgresql",
    "montar_plano",
    "raiz_bancos",
    "roles_que_alcancam_a_origem",
    "sufixo_do_ambiente",
]
