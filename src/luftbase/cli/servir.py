"""Comando `luftbase servir`: executa a aplicacao com o servidor padrao da plataforma."""

from __future__ import annotations

import click


@click.command("servir")
@click.argument("alvo", default="App:app")
@click.option("--host", default=None, help="Padrao: LUFT_SERVIDOR_HOST | HOST | 127.0.0.1.")
@click.option("--porta", type=int, default=None, help="Padrao: LUFT_SERVIDOR_PORTA | PORT | 8000.")
@click.option("--prefixo", default=None, help="Padrao: LUFT_SERVIDOR_PREFIXO | ROUTE_PREFIX.")
@click.option("--threads", type=int, default=None, help="Padrao: LUFT_SERVIDOR_THREADS | 8.")
def servir(alvo: str, host: str | None, porta: int | None, prefixo: str | None,
           threads: int | None) -> None:
    """Serve ALVO ('modulo:atributo', Flask ou fabrica) com o Waitress."""

    from luftbase.servidor import executar

    executar(alvo, host=host, porta=porta, prefixo=prefixo, threads=threads)
