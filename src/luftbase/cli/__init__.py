"""Comandos operacionais registrados pelo LuftBase."""

from __future__ import annotations

import click
from flask import Flask

from luftbase._versao import __version__
from luftbase.cli.alertas import alertas
from luftbase.cli.banco import banco
from luftbase.cli.bootstrap import bootstrap, conceder_permissoes
from luftbase.cli.catalogo import catalogo
from luftbase.cli.diagnostico import diagnostico
from luftbase.cli.email import email
from luftbase.cli.estrutura import estrutura
from luftbase.cli.projeto import projeto
from luftbase.cli.servir import servir
from luftbase.cli.tema import tema
from luftbase.cli.vault import vault, vault_postgresql


@click.group("luftbase")
@click.version_option(version=__version__, prog_name="luftbase")
def cli() -> None:
    """CLI corporativa da plataforma LuftBase."""


banco.add_command(bootstrap)
banco.add_command(conceder_permissoes)
vault_postgresql.add_command(bootstrap)

cli.add_command(alertas)
cli.add_command(banco)
cli.add_command(bootstrap)
cli.add_command(conceder_permissoes)
cli.add_command(catalogo)
cli.add_command(diagnostico)
cli.add_command(email)
cli.add_command(estrutura)
cli.add_command(projeto)
cli.add_command(servir)
cli.add_command(tema)
cli.add_command(vault)


def registrar_comandos(app: Flask) -> None:
    """Registra grupos de CLI no aplicativo Flask sem executar qualquer operacao."""

    app.cli.add_command(alertas)
    app.cli.add_command(banco)
    app.cli.add_command(bootstrap)
    app.cli.add_command(conceder_permissoes)
    app.cli.add_command(catalogo)
    app.cli.add_command(diagnostico)
    app.cli.add_command(email)
    app.cli.add_command(estrutura)
    app.cli.add_command(projeto)
    app.cli.add_command(tema)
    app.cli.add_command(vault)


__all__ = [
    "alertas",
    "banco",
    "bootstrap",
    "catalogo",
    "cli",
    "conceder_permissoes",
    "diagnostico",
    "email",
    "estrutura",
    "projeto",
    "registrar_comandos",
    "tema",
    "vault",
]
