"""Espelho local do banco de homologacao na maquina do desenvolvedor.

Faz uma copia integral do banco de origem para um PostgreSQL local, para o dev trabalhar sem tocar
nos dados do ambiente. A origem e somente lida (`pg_dump` e consultas); o SQL Server nunca entra.

Duas regras de seguranca nao dependem de flag:

- o destino e sempre a propria maquina (loopback) e a origem nunca e producao;
- senhas vao por variavel de ambiente do subprocesso, jamais por argumento de linha de comando.

As roles `luft_*` de aplicacao viajam com o verificador SCRAM da senha, lido de `pg_authid` e
aplicado com `CREATE ROLE ... PASSWORD '<verificador>'`. Assim as credenciais que o Vault ja entrega
continuam valendo no banco local, e a aplicacao so precisa trocar host e porta
(`LUFT_BANCO_LOCAL_HOST`). Roles administrativas (superusuarios) nunca sao copiadas: aplicar a
role `postgres` de homologacao trocaria a senha do administrador local.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luftbase.configuracao.modelos import HOSTS_LOCAIS
from luftbase.nucleo.excecoes import ErroConfiguracao

FERRAMENTAS = ("pg_dump", "pg_restore")
_PADRAO_ROLE_APLICACAO = re.compile(r"^luft_[a-z0-9_]+$")
_PADRAO_NOME_BANCO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_PASTAS_WINDOWS = (r"C:\Program Files\PostgreSQL", r"C:\Program Files (x86)\PostgreSQL")


class ErroEspelho(Exception):
    """Falha controlada do espelho, com mensagem pronta para o terminal."""


@dataclass(frozen=True, slots=True)
class Servidor:
    """Endereco e credencial de um PostgreSQL; a senha nunca aparece em `repr`."""

    host: str
    porta: int
    banco: str
    usuario: str
    senha: str

    def __repr__(self) -> str:
        return f"Servidor({self.host}:{self.porta}/{self.banco} usuario={self.usuario})"


@dataclass(frozen=True, slots=True)
class RoleAplicacao:
    """Role de aplicacao e o verificador SCRAM da senha dela."""

    nome: str
    verificador: str


@dataclass(frozen=True, slots=True)
class ResultadoEspelho:
    """O que o espelho fez, sem nenhum segredo."""

    banco_destino: str
    roles: tuple[str, ...]
    recriado: bool
    roles_ignoradas: tuple[str, ...] = ()
    roles_mantidas: tuple[str, ...] = ()
    roles_dev_atendidas: tuple[str, ...] = ()


def exigir_destino_local(host: str) -> str:
    """Recusa qualquer destino que nao seja a propria maquina."""

    if host.strip().casefold() not in HOSTS_LOCAIS:
        raise ErroEspelho(
            "O espelho so grava no PostgreSQL da propria maquina "
            f"(localhost, 127.0.0.1 ou ::1); recebido {host!r}."
        )
    return host.strip()


def validar_nome_banco(nome: str) -> str:
    """Nome de banco valido e seguro para entrar em `CREATE DATABASE`."""

    if not _PADRAO_NOME_BANCO.fullmatch(nome):
        raise ErroEspelho(
            f"Nome de banco invalido: {nome!r}. Use letras, numeros e sublinhado, "
            "comecando por letra."
        )
    return nome


def localizar_ferramentas(
    pasta_bin: Path | None = None,
    *,
    procurar: Callable[[str], str | None] = shutil.which,
    pastas_instalacao: Sequence[str] = _PASTAS_WINDOWS,
) -> dict[str, str]:
    """Acha `pg_dump` e `pg_restore`: pasta informada, PATH e instalacoes padrao do Windows.

    A versao do `pg_dump` precisa ser igual ou maior que a do servidor de origem; por isso, entre
    as instalacoes do Windows, vale a de numero mais alto.
    """

    instaladas: list[Path] = []
    for raiz in pastas_instalacao:
        base = Path(raiz)
        if base.is_dir():
            versoes = sorted(
                (p for p in base.iterdir() if (p / "bin").is_dir()),
                key=lambda p: _numero_versao(p.name),
                reverse=True,
            )
            instaladas.extend(p / "bin" for p in versoes)

    achadas: dict[str, str] = {}
    for nome in FERRAMENTAS:
        # Pasta informada vence; depois o PATH; por fim as instalacoes padrao.
        caminho = _executavel(pasta_bin, nome) if pasta_bin is not None else None
        caminho = caminho or procurar(nome)
        for pasta in instaladas:
            if caminho:
                break
            caminho = _executavel(pasta, nome)
        if caminho is None:
            raise ErroEspelho(
                f"Ferramenta {nome!r} nao encontrada. Instale o cliente do PostgreSQL ou "
                "informe a pasta com --pg-bin (ex.: C:/Program Files/PostgreSQL/17/bin)."
            )
        achadas[nome] = caminho
    return achadas


def _numero_versao(nome: str) -> float:
    try:
        return float(nome)
    except ValueError:
        return 0.0


def _executavel(pasta: Path, nome: str) -> str | None:
    for sufixo in ("", ".exe"):
        arquivo = pasta / f"{nome}{sufixo}"
        if arquivo.is_file():
            return str(arquivo)
    return None


def ler_roles_aplicacao(conexao_origem: Any) -> list[RoleAplicacao]:
    """Le de `pg_authid` as roles `luft_*` com login que nao sao superusuario."""

    with conexao_origem.cursor() as cursor:
        cursor.execute(
            "SELECT rolname, rolpassword FROM pg_authid "
            "WHERE rolcanlogin AND NOT rolsuper AND rolpassword IS NOT NULL "
            "AND rolname ~ '^luft_' ORDER BY rolname"
        )
        linhas = cursor.fetchall()
    roles: list[RoleAplicacao] = []
    for nome, verificador in linhas:
        if not _PADRAO_ROLE_APLICACAO.fullmatch(str(nome)):
            continue
        if not str(verificador).startswith("SCRAM-SHA-256$"):
            # Senha em MD5 ou texto: nao ha como levar sem expor ou rebaixar a seguranca.
            raise ErroEspelho(
                f"A role {nome!r} nao usa verificador SCRAM-SHA-256; o espelho nao a copia."
            )
        roles.append(RoleAplicacao(str(nome), str(verificador)))
    return roles


def aplicar_roles(
    conexao_destino: Any,
    roles: Sequence[RoleAplicacao],
    *,
    sobrescrever_senhas: bool = False,
) -> list[str]:
    """Cria as roles que faltam no PostgreSQL local, sem privilegios extras.

    Role que ja existe localmente **mantem a senha local**: trocar pela de homologacao quebraria o
    acesso do dev a roles dele (ex.: o dono do banco). So `sobrescrever_senhas` faz o `ALTER ROLE`.
    Devolve os nomes das roles que ja existiam e ficaram como estavam.
    """

    from psycopg import sql

    mantidas: list[str] = []
    with conexao_destino.cursor() as cursor:
        for role in roles:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role.nome,))
            existe = cursor.fetchone() is not None
            if existe and not sobrescrever_senhas:
                mantidas.append(role.nome)
                continue
            cursor.execute(
                sql.SQL("{verbo} ROLE {nome} WITH LOGIN PASSWORD {senha}").format(
                    verbo=sql.SQL("ALTER" if existe else "CREATE"),
                    nome=sql.Identifier(role.nome),
                    senha=sql.Literal(role.verificador),
                )
            )
    return mantidas


_PADRAO_ROLE_DEV = r"^luft_.+_dev_app$"


def conceder_acesso_roles_dev(conexao_banco: Any) -> tuple[list[str], list[str]]:
    """Da as roles `luft_<schema>_dev_app` locais o acesso que `provisionar` daria a elas.

    O dump traz permissoes so para as roles de homologacao (`..._hml_app`); sem isto, uma
    aplicacao que roda como desenvolvimento nao enxergaria nada do banco copiado. So atende role que
    ja existe localmente e cujo schema veio no dump; devolve (atendidas, sem_schema).
    """

    from psycopg import sql

    atendidas: list[str] = []
    sem_schema: list[str] = []
    with conexao_banco.cursor() as cursor:
        cursor.execute(
            "SELECT rolname FROM pg_roles WHERE rolname ~ %s ORDER BY 1", (_PADRAO_ROLE_DEV,)
        )
        nomes = [linha[0] for linha in cursor.fetchall()]
        for nome in nomes:
            schema = nome[len("luft_") : -len("_dev_app")]
            cursor.execute("SELECT 1 FROM pg_namespace WHERE nspname = %s", (schema,))
            if cursor.fetchone() is None:
                sem_schema.append(nome)
                continue
            for modelo in _GRANTS_ROLE_DEV:
                cursor.execute(
                    sql.SQL(modelo).format(
                        papel=sql.Identifier(nome), esquema=sql.Identifier(schema)
                    )
                )
            atendidas.append(nome)
    return atendidas, sem_schema


# Mesmos privilegios de `luftbase bootstrap`: core com DML e schema proprio completo.
_GRANTS_ROLE_DEV = (
    "GRANT USAGE ON SCHEMA core TO {papel}",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO {papel}",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO {papel}",
    "GRANT ALL ON SCHEMA {esquema} TO {papel}",
    "GRANT ALL ON ALL TABLES IN SCHEMA {esquema} TO {papel}",
    "GRANT ALL ON ALL SEQUENCES IN SCHEMA {esquema} TO {papel}",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} GRANT ALL ON TABLES TO {papel}",
    "ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} GRANT ALL ON SEQUENCES TO {papel}",
)


def comando_dump(
    ferramenta: str, origem: Servidor, *, somente_estrutura: bool = False
) -> list[str]:
    """`pg_dump` do banco inteiro em formato custom, com ACL e sem donos (donos = admin local)."""

    return [
        ferramenta,
        "--format=custom",
        *(["--schema-only"] if somente_estrutura else []),
        "--no-owner",
        "--no-password",
        f"--host={origem.host}",
        f"--port={origem.porta}",
        f"--username={origem.usuario}",
        f"--dbname={origem.banco}",
    ]


def comando_restore(ferramenta: str, destino: Servidor) -> list[str]:
    """`pg_restore` lendo o dump da entrada padrao."""

    return [
        ferramenta,
        "--no-owner",
        "--no-password",
        f"--host={destino.host}",
        f"--port={destino.porta}",
        f"--username={destino.usuario}",
        f"--dbname={destino.banco}",
    ]


PREFIXO_WSL = ("wsl.exe", "-e")


def _ambiente_com_senha(senha: str, *, via_wsl: bool = False) -> Mapping[str, str]:
    ambiente = {**os.environ, "PGPASSWORD": senha}
    if via_wsl:
        # O WSL so repassa ao Linux as variaveis listadas em WSLENV; assim a senha nao vai na
        # linha de comando (visivel em `ps`), so no ambiente do processo.
        atual = ambiente.get("WSLENV", "")
        ambiente["WSLENV"] = f"{atual}:PGPASSWORD" if atual else "PGPASSWORD"
    return ambiente


def ferramentas_no_wsl(
    executar: Callable[..., Any] = subprocess.run,
) -> dict[str, str]:
    """Confere se `pg_dump` e `pg_restore` existem na distribuicao padrao do WSL.

    Dentro do WSL a rede do PostgreSQL local e a do proprio Linux; por isso o destino
    `localhost` aponta para o mesmo servidor que o Windows enxerga por redirecionamento.
    """

    try:
        resultado = executar(
            [*PREFIXO_WSL, "sh", "-c", "command -v pg_dump && command -v pg_restore"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as erro:
        raise ErroEspelho(f"Nao foi possivel executar o WSL: {erro}") from erro
    if resultado.returncode != 0:
        raise ErroEspelho(
            "pg_dump/pg_restore nao encontrados no WSL. Instale no Linux: "
            "sudo apt install postgresql-client"
        )
    return {nome: nome for nome in FERRAMENTAS}


def copiar_dados(
    ferramentas: Mapping[str, str],
    origem: Servidor,
    destino: Servidor,
    *,
    iniciar: Callable[..., Any] = subprocess.Popen,
    via_wsl: bool = False,
    avisos: list[str] | None = None,
    somente_estrutura: bool = False,
) -> tuple[str, ...]:
    """Liga `pg_dump` a `pg_restore` por um pipe: o dado nao fica em disco.

    Falha se qualquer um dos dois terminar com erro; a mensagem traz o fim do `stderr`, que nunca
    contem a senha (ela so existe no ambiente do processo). Uma unica classe de erro e tolerada:
    `GRANT` para role que nao existe na maquina local (ex.: role de DBA da origem, que nao e
    copiada de proposito). Os nomes dessas roles voltam para o operador ver.
    """

    prefixo = list(PREFIXO_WSL) if via_wsl else []
    dump = iniciar(
        [
            *prefixo,
            *comando_dump(ferramentas["pg_dump"], origem, somente_estrutura=somente_estrutura),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_ambiente_com_senha(origem.senha, via_wsl=via_wsl),
    )
    restore = iniciar(
        [*prefixo, *comando_restore(ferramentas["pg_restore"], destino)],
        stdin=dump.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_ambiente_com_senha(destino.senha, via_wsl=via_wsl),
    )
    # O pg_restore agora e dono da ponta de leitura; fechar aqui permite o SIGPIPE ao dump.
    if dump.stdout is not None:
        dump.stdout.close()
    _, erro_restore = restore.communicate()
    erro_dump = dump.stderr.read() if dump.stderr is not None else b""
    dump.wait()
    if dump.returncode != 0:
        raise ErroEspelho(f"pg_dump falhou (codigo {dump.returncode}): {_fim(erro_dump)}")
    if restore.returncode == 0:
        return ()
    erros = _linhas_de_erro(erro_restore)
    ignoradas = tuple(sorted({m.group(1) for e in erros if (m := _ROLE_INEXISTENTE.search(e))}))
    parametros = sorted({m.group(1) for e in erros if (m := _PARAMETRO_DESCONHECIDO.search(e))})
    if parametros and avisos is not None:
        avisos.append(
            "O servidor local nao conhece o parametro "
            f"{', '.join(parametros)} (cliente pg_dump mais novo que o servidor); sem efeito nos dados."
        )
    graves = [
        e
        for e in erros
        if not _ROLE_INEXISTENTE.search(e) and not _PARAMETRO_DESCONHECIDO.search(e)
    ]
    if graves or not erros:
        raise ErroEspelho(f"pg_restore falhou (codigo {restore.returncode}): {_fim(erro_restore)}")
    return ignoradas


_ROLE_INEXISTENTE = re.compile(r'role "([^"]+)" does not exist')
# `pg_dump` mais novo que o servidor local emite `SET <parametro novo>`; o servidor antigo recusa so
# essa linha, sem efeito nos dados (ex.: `transaction_timeout`, do PostgreSQL 17).
_PARAMETRO_DESCONHECIDO = re.compile(r'unrecognized configuration parameter "([^"]+)"')


def _linhas_de_erro(texto: bytes | str) -> list[str]:
    """Linhas `pg_restore: error: ...`; as linhas `Command was:` acompanham o erro anterior."""

    bruto = texto.decode("utf-8", "replace") if isinstance(texto, bytes) else texto
    return [
        linha.strip()
        for linha in bruto.splitlines()
        if "error:" in linha and not linha.startswith("pg_restore: warning")
    ]


def _fim(texto: bytes | str, linhas: int = 6) -> str:
    bruto = texto.decode("utf-8", "replace") if isinstance(texto, bytes) else texto
    return " | ".join(bruto.strip().splitlines()[-linhas:]) or "sem detalhes"


def banco_existe(conexao_destino: Any, nome: str) -> bool:
    with conexao_destino.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (nome,))
        return cursor.fetchone() is not None


def recriar_banco(conexao_destino: Any, nome: str, *, apagar_existente: bool) -> bool:
    """Cria o banco local; com `apagar_existente` derruba conexoes e o recria. Devolve se recriou."""

    from psycopg import sql

    existia = banco_existe(conexao_destino, nome)
    if existia and not apagar_existente:
        raise ErroEspelho(
            f"O banco local {nome!r} ja existe. Use --recriar para apaga-lo e copiar de novo."
        )
    with conexao_destino.cursor() as cursor:
        if existia:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (nome,),
            )
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(nome)))
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    return existia


def espelhar(
    origem: Servidor,
    destino: Servidor,
    *,
    ferramentas: Mapping[str, str],
    recriar: bool,
    conectar: Callable[[Servidor, str], Any],
    iniciar: Callable[..., Any] = subprocess.Popen,
    via_wsl: bool = False,
    somente_estrutura: bool = False,
    sobrescrever_senhas: bool = False,
    ao_etapa: Callable[[str], None] | None = None,
) -> ResultadoEspelho:
    """Roles, banco vazio e copia dos dados, nesta ordem.

    `conectar(servidor, banco)` devolve uma conexao autocommit; os testes injetam a deles.
    """

    def avisar(texto: str) -> None:
        if ao_etapa is not None:
            ao_etapa(texto)

    exigir_destino_local(destino.host)
    validar_nome_banco(destino.banco)

    # Falha cedo no login local: evita ler a origem so para descobrir senha errada do destino.
    with conectar(destino, "postgres"):
        pass
    with conectar(origem, origem.banco) as conexao_origem:
        roles = ler_roles_aplicacao(conexao_origem)
    avisar(f"{len(roles)} role(s) de aplicacao lida(s) da origem.")

    with conectar(destino, "postgres") as conexao_destino:
        mantidas = aplicar_roles(conexao_destino, roles, sobrescrever_senhas=sobrescrever_senhas)
        avisar(f"Roles criadas no banco local: {len(roles) - len(mantidas)}.")
        if mantidas:
            avisar(
                "Roles que ja existiam localmente mantiveram a senha local: "
                f"{', '.join(mantidas)} (use --sobrescrever-senhas para trocar pela da origem)."
            )
        recriado = recriar_banco(conexao_destino, destino.banco, apagar_existente=recriar)
        avisar(f"Banco local {destino.banco!r} {'recriado' if recriado else 'criado'}.")

    avisar("Copiando dados (pg_dump | pg_restore)...")
    avisos: list[str] = []
    ignoradas = copiar_dados(
        ferramentas,
        origem,
        destino,
        iniciar=iniciar,
        via_wsl=via_wsl,
        avisos=avisos,
        somente_estrutura=somente_estrutura,
    )
    for aviso in avisos:
        avisar(aviso)
    if ignoradas:
        avisar(
            f"Permissoes para roles que nao existem localmente foram ignoradas: {', '.join(ignoradas)}."
        )
    avisar("Copia concluida.")

    with conectar(destino, destino.banco) as conexao_banco:
        atendidas, sem_schema = conceder_acesso_roles_dev(conexao_banco)
    if atendidas:
        avisar(f"Acesso concedido as roles de desenvolvimento: {', '.join(atendidas)}.")
    if sem_schema:
        avisar(
            "Roles de desenvolvimento sem schema no banco copiado (sem acesso concedido): "
            f"{', '.join(sem_schema)}."
        )
    return ResultadoEspelho(
        destino.banco,
        tuple(r.nome for r in roles),
        recriado,
        ignoradas,
        tuple(mantidas),
        tuple(atendidas),
    )


def nome_local_padrao(banco_origem: str) -> str:
    """`luft_web_hml` -> `luft_web_dev`: o espelho nunca reaproveita o nome do ambiente de origem."""

    base = re.sub(r"_(hml|homologacao|prd|producao|dev)$", "", banco_origem, flags=re.IGNORECASE)
    return f"{base}_dev"


def linhas_env_banco_local(destino: Servidor) -> list[str]:
    """As duas linhas que apontam a aplicacao para o espelho."""

    return [
        f"LUFT_BANCO_LOCAL_HOST={destino.host}",
        f"LUFT_BANCO_LOCAL_PORTA={destino.porta}",
        f"LUFT_BANCO_LOCAL_NOME={destino.banco}",
    ]


def configurar_env(arquivo: Path, destino: Servidor) -> bool:
    """Acrescenta ou atualiza as linhas do banco local num `.env`; devolve se houve mudanca."""

    if not arquivo.is_file():
        raise ErroConfiguracao(f"O arquivo {str(arquivo)!r} nao existe.")
    novas = dict(linha.split("=", 1) for linha in linhas_env_banco_local(destino))
    original = arquivo.read_text(encoding="utf-8")
    saida: list[str] = []
    vistas: set[str] = set()
    for linha in original.splitlines():
        chave = linha.partition("=")[0].strip()
        if chave in novas:
            saida.append(f"{chave}={novas[chave]}")
            vistas.add(chave)
        else:
            saida.append(linha)
    faltantes = [c for c in novas if c not in vistas]
    if faltantes:
        saida.append("")
        saida.append(
            "# Banco espelho local (luftbase banco espelhar). Apague estas linhas para voltar ao ambiente."
        )
        saida.extend(f"{c}={novas[c]}" for c in faltantes)
    texto = "\n".join(saida) + "\n"
    if texto == original:
        return False
    arquivo.write_text(texto, encoding="utf-8")
    return True


__all__ = [
    "ErroEspelho",
    "ResultadoEspelho",
    "RoleAplicacao",
    "Servidor",
    "aplicar_roles",
    "conceder_acesso_roles_dev",
    "configurar_env",
    "copiar_dados",
    "espelhar",
    "ferramentas_no_wsl",
    "exigir_destino_local",
    "ler_roles_aplicacao",
    "linhas_env_banco_local",
    "nome_local_padrao",
    "localizar_ferramentas",
    "recriar_banco",
    "validar_nome_banco",
]
