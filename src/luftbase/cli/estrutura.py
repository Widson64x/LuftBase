"""Comandos explicitos para inspecionar modelos particulares da aplicacao."""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from luftbase.nucleo.excecoes import ErroInicializacao
from luftbase.plataforma import obter_luftbase

CONFIRMACAO_CRIACAO = "CRIAR_ESTRUTURA"


@click.group("estrutura")
def estrutura() -> None:
    """Verifica tabelas particulares sem alterar fontes externas."""


@estrutura.command("verificar")
@with_appcontext
def verificar() -> None:
    """Lista a existencia e a politica de cada model registrado."""

    estados = obter_luftbase().estruturas.verificar()
    if not estados:
        click.echo("modelos=nenhum_registrado")
        return
    faltantes = 0
    for estado in estados:
        status = "OK" if estado.existe else "AUSENTE"
        faltantes += int(not estado.existe)
        click.echo(
            f"{status:<7} modelo={estado.nome} tabela={estado.tabela} "
            f"origem={estado.origem.value} politica={estado.politica.value}"
        )
    click.echo(f"faltantes={faltantes}")
    if faltantes:
        raise click.exceptions.Exit(1)


@estrutura.command("criar")
@click.argument("modelo")
@click.option("--confirmar", default="", help=f"Informe {CONFIRMACAO_CRIACAO}.")
@with_appcontext
def criar(modelo: str, confirmar: str) -> None:
    """Cria um model GERENCIAR usando uma credencial autorizada para DDL."""

    if confirmar != CONFIRMACAO_CRIACAO:
        raise click.UsageError(f"Use --confirmar {CONFIRMACAO_CRIACAO}.")
    try:
        obter_luftbase().estruturas.criar(modelo)
    except ErroInicializacao as erro:
        raise click.ClickException(str(erro)) from erro
    except Exception as erro:
        raise click.ClickException(
            "Nao foi possivel criar a tabela. Execute com a credencial de implantacao."
        ) from erro
    click.echo(f"modelo={modelo} criacao=concluida")
