"""Comandos seguros de inspecao, adocao e evolucao do schema core."""

from __future__ import annotations

from collections import Counter

import click
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from flask.cli import with_appcontext
from sqlalchemy import Connection, MetaData

from luftbase.migracoes.configuracao import criar_configuracao_alembic
from luftbase.persistencia import core as _modelos_core  # noqa: F401
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.catalogo import sincronizar_catalogo_workspace
from luftbase.plataforma import obter_luftbase

REVISAO_BASELINE = "20260915_0001"
CONFIRMACAO_ADOCAO = "ADOTAR_CORE_EXISTENTE"
CONFIRMACAO_ATUALIZACAO = "ATUALIZAR_CORE"
TABELAS_BASELINE = frozenset(
    {
        "tb_sistema",
        "tb_permissao",
        "tb_permissaogrupo",
        "tb_permissaousuario",
        "tb_logs",
        "tb_logevento",
        "tb_logdetalhe",
        "tb_notificacao",
        "tb_notificacao_leitura",
        "tb_publicacao",
        "tb_publicacaogrupo",
        "tb_publicacaoleitura",
        "tb_publicacaonotificacao",
        "tb_notaatualizacaoitem",
    }
)


def obter_metadados_baseline() -> MetaData:
    """Copia somente o contrato das tabelas migradas do core."""

    metadados = MetaData(schema="core", naming_convention=BaseLuft.metadata.naming_convention)
    for tabela in BaseLuft.metadata.tables.values():
        if tabela.name in TABELAS_BASELINE:
            tabela.to_metadata(metadados)
    return metadados


def _incluir_objeto(
    objeto: object,
    nome: str | None,
    tipo: str,
    refletido: bool,
    comparado: object | None,
) -> bool:
    del nome, refletido, comparado
    if tipo == "table" and getattr(objeto, "name", None) == "alembic_version":
        return False
    tabela = objeto if tipo == "table" else getattr(objeto, "table", None)
    return getattr(tabela, "schema", None) == "core"


def comparar_estrutura(conexao: Connection, *, somente_baseline: bool = False) -> list[object]:
    """Compara metadados e catalogo usando apenas consultas de introspeccao."""

    alvo = obter_metadados_baseline() if somente_baseline else BaseLuft.metadata
    contexto = MigrationContext.configure(
        conexao,
        opts={
            "target_metadata": alvo,
            "include_schemas": True,
            "include_object": _incluir_objeto,
            "compare_type": True,
            "compare_server_default": True,
            "version_table_schema": "core",
        },
    )
    return list(compare_metadata(contexto, alvo))


def resumir_diferencas(diferencas: list[object]) -> Counter[str]:
    """Agrupa divergencias sem imprimir valores ou SQL possivelmente sensiveis."""

    resumo: Counter[str] = Counter()

    def visitar(item: object) -> None:
        if isinstance(item, list):
            for filho in item:
                visitar(filho)
            return
        if isinstance(item, tuple) and item and isinstance(item[0], str):
            resumo[item[0]] += 1
            return
        resumo["divergencia_desconhecida"] += 1

    for diferenca in diferencas:
        visitar(diferenca)
    return resumo


def _revisoes(conexao: Connection) -> tuple[str | None, str]:
    contexto = MigrationContext.configure(
        conexao,
        opts={"version_table": "alembic_version", "version_table_schema": "core"},
    )
    atual = contexto.get_current_revision()
    scripts = ScriptDirectory.from_config(criar_configuracao_alembic())
    cabeca = scripts.get_current_head()
    if cabeca is None:
        raise click.ClickException("O pacote nao possui uma revisao Alembic de destino.")
    return atual, cabeca


@click.group("banco")
def banco() -> None:
    """Inspeciona e evolui o schema core de forma explicita."""


@banco.command("versao")
@with_appcontext
def versao() -> None:
    """Mostra a revisao instalada e a revisao entregue pelo pacote."""

    try:
        with obter_luftbase().bancos.core.engine.connect() as conexao:
            atual, cabeca = _revisoes(conexao)
    except Exception as erro:
        raise click.ClickException("Nao foi possivel consultar a versao do schema core.") from erro
    click.echo(f"instalada={atual or 'nao_versionada'}")
    click.echo(f"disponivel={cabeca}")


@banco.command("validar")
@click.option(
    "--baseline-migrada",
    is_flag=True,
    help="Compara somente as 13 tabelas da migracao manual.",
)
@with_appcontext
def validar(baseline_migrada: bool) -> None:
    """Detecta divergencias sem alterar o banco."""

    try:
        with obter_luftbase().bancos.core.engine.connect() as conexao:
            diferencas = comparar_estrutura(conexao, somente_baseline=baseline_migrada)
    except Exception as erro:
        raise click.ClickException("Nao foi possivel validar a estrutura do schema core.") from erro
    if not diferencas:
        click.echo("estrutura=compativel")
        return
    click.echo("estrutura=divergente")
    for categoria, quantidade in sorted(resumir_diferencas(diferencas).items()):
        click.echo(f"{categoria}={quantidade}")
    raise click.exceptions.Exit(1)


@banco.command("registrar-base")
@click.option("--confirmar", default="", help=f"Informe {CONFIRMACAO_ADOCAO}.")
@with_appcontext
def registrar_base(confirmar: str) -> None:
    """Adota a baseline somente apos validar as 13 tabelas existentes."""

    if confirmar != CONFIRMACAO_ADOCAO:
        raise click.UsageError(f"Use --confirmar {CONFIRMACAO_ADOCAO}.")
    engine = obter_luftbase().bancos.core.engine
    try:
        with engine.begin() as conexao:
            atual, _cabeca = _revisoes(conexao)
            if atual is not None:
                raise click.ClickException("O schema core ja possui uma revisao registrada.")
            diferencas = comparar_estrutura(conexao, somente_baseline=True)
            if diferencas:
                raise click.ClickException(
                    "A estrutura existente diverge da baseline; nenhuma revisao foi registrada."
                )
            configuracao = criar_configuracao_alembic(conexao=conexao)
            command.stamp(configuracao, REVISAO_BASELINE)
    except click.ClickException:
        raise
    except Exception as erro:
        raise click.ClickException("Nao foi possivel registrar a baseline.") from erro
    click.echo(f"baseline_registrada={REVISAO_BASELINE}")


@banco.command("atualizar")
@click.option("--confirmar", default="", help=f"Informe {CONFIRMACAO_ATUALIZACAO}.")
@with_appcontext
def atualizar(confirmar: str) -> None:
    """Aplica migrations pendentes; nunca e chamado na inicializacao web."""

    if confirmar != CONFIRMACAO_ATUALIZACAO:
        raise click.UsageError(f"Use --confirmar {CONFIRMACAO_ATUALIZACAO}.")
    engine = obter_luftbase().bancos.core.engine
    try:
        with engine.begin() as conexao:
            configuracao = criar_configuracao_alembic(conexao=conexao)
            command.upgrade(configuracao, "head")
            sincronizar_catalogo_workspace(conexao)
    except Exception as erro:
        raise click.ClickException("Nao foi possivel atualizar o schema core.") from erro
    click.echo("atualizacao=concluida")


@banco.command("historico")
@with_appcontext
def historico() -> None:
    """Lista as revisoes disponiveis no pacote e indica a versao instalada."""

    atual: str | None = None
    try:
        with obter_luftbase().bancos.core.engine.connect() as conexao:
            atual, _ = _revisoes(conexao)
    except Exception:
        atual = None

    scripts = ScriptDirectory.from_config(criar_configuracao_alembic())
    revisoes = list(scripts.walk_revisions(base="base", head="head"))
    revisoes.reverse()

    for sc in revisoes:
        marcador = "->" if sc.revision == atual else "  "
        click.echo(f"{marcador} {sc.revision}: {sc.doc or ''}")


@banco.command("pendencias")
@with_appcontext
def pendencias() -> None:
    """Lista revisoes pendentes sem aplicar alteracoes."""

    try:
        with obter_luftbase().bancos.core.engine.connect() as conexao:
            atual, cabeca = _revisoes(conexao)
    except Exception as erro:
        raise click.ClickException("Nao foi possivel consultar revisoes do banco.") from erro

    if atual == cabeca:
        click.echo("pendencias=nenhuma")
        return

    scripts = ScriptDirectory.from_config(criar_configuracao_alembic())
    if atual is None:
        revisoes_pendentes = list(scripts.walk_revisions(base="base", head="head"))
    else:
        revisoes_pendentes = [
            sc for sc in scripts.walk_revisions(base=atual, head="head") if sc.revision != atual
        ]

    revisoes_pendentes.reverse()
    click.echo(f"pendencias={len(revisoes_pendentes)}")
    for sc in revisoes_pendentes:
        click.echo(f"  {sc.revision}: {sc.doc or ''}")
