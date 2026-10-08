"""Comandos dos alertas para o desenvolvedor."""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from luftbase.observabilidade import alertas as modulo
from luftbase.plataforma import obter_luftbase


@click.group("alertas")
def alertas() -> None:
    """Avaliacao e consulta dos alertas (erros 5xx, rajadas de 4xx, eventos criticos, lentidao)."""


@alertas.command("avaliar")
@with_appcontext
def alertas_avaliar() -> None:
    """Roda UM ciclo do avaliador (ideal para agendar a cada minuto) e imprime o resultado."""

    estado = obter_luftbase()
    resultado = modulo.avaliar(estado.bancos, estado.email)
    click.echo(f"executou={str(resultado.executou).lower()}")
    click.echo(f"ocorrencias={resultado.ocorrencias}")
    click.echo(f"abertos={resultado.alertas_abertos} atualizados={resultado.alertas_atualizados}")
    click.echo(f"resolvidos={resultado.alertas_resolvidos}")
    click.echo(f"avisados={resultado.avisados} email_enviado={str(resultado.email_enviado).lower()}")
    for erro in resultado.erros:
        click.echo(f"erro={erro}", err=True)
    if resultado.erros:
        raise click.exceptions.Exit(1)


@alertas.command("listar")
@click.option("--todos", is_flag=True, help="Inclui os alertas ja resolvidos.")
@click.option("--limite", default=30, show_default=True, type=int)
@with_appcontext
def alertas_listar(todos: bool, limite: int) -> None:
    """Lista os alertas abertos (ou todos) do mais recente para o mais antigo."""

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        itens = modulo.listar_alertas(sessao, somente_abertos=not todos, limite=limite)
    if not itens:
        click.echo("Nenhum alerta.")
        return
    for a in itens:
        quem = a["login"] or (f"ip:{a['ip']}" if a["ip"] else "-")
        click.echo(
            f"#{a['id_alerta']} [{a['status']}] {a['rotulo']} | {a['sistema']} | {quem} | "
            f"{a['rota'] or '-'} | {a['ocorrencias']}x | ultima {a['ultima_ocorrencia']}"
        )


__all__ = ["alertas"]
