"""Comandos de inspecao e validacao de temas do design system LuftBase."""

from __future__ import annotations

import json
from pathlib import Path

import click

from luftbase.interface.modelos import ManifestoTema
from luftbase.interface.servico import criar_registro_padrao
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema
from luftbase.plataforma import obter_luftbase

TOKENS_OBRIGATORIOS_CSS = frozenset(
    {
        "--luft-cor-fundo",
        "--luft-cor-superficie",
        "--luft-cor-texto",
        "--luft-cor-borda",
        "--luft-cor-destaque",
        "--luft-cor-foco",
        "--luft-cor-sucesso",
        "--luft-cor-alerta",
        "--luft-cor-perigo",
    }
)


def _modos_da_opcao(valor: str) -> frozenset[ModoTema]:
    """Converte 'claro,escuro' em modos de tema, rejeitando valores desconhecidos."""

    modos: set[ModoTema] = set()
    for item in valor.split(","):
        nome = item.strip().upper()
        if not nome:
            continue
        try:
            modos.add(ModoTema(nome))
        except ValueError as erro:
            raise click.BadParameter(f"modo desconhecido: {item.strip()!r}") from erro
    if not modos:
        raise click.BadParameter("informe ao menos um modo (claro e/ou escuro)")
    return frozenset(modos)


def validar_css_tema(
    conteudo: str,
    modos: frozenset[ModoTema] = frozenset({ModoTema.CLARO, ModoTema.ESCURO}),
) -> list[str]:
    """Verifica os tokens essenciais e os modos que o tema declara oferecer.

    Um tema de modo unico so precisa definir o modo que oferece; exigir o outro
    obrigaria a escrever uma paleta que o tema nunca vai usar.
    """

    faltantes: list[str] = []
    for token in sorted(TOKENS_OBRIGATORIOS_CSS):
        if token not in conteudo:
            faltantes.append(f"token ausente: {token}")

    if (
        ModoTema.ESCURO in modos
        and 'data-luft-mode="escuro"' not in conteudo
        and "color-scheme: dark" not in conteudo
    ):
        faltantes.append("modo escuro ausente (necessario seletor ou regra dark)")

    if (
        ModoTema.CLARO in modos
        and 'data-luft-mode="claro"' not in conteudo
        and "color-scheme: light" not in conteudo
    ):
        faltantes.append("modo claro ausente (necessario seletor ou regra light)")

    return faltantes


@click.group("tema")
def tema() -> None:
    """Listagem e validacao de manifestos e tokens de temas."""


@tema.command("listar")
def tema_listar() -> None:
    """Lista as familias visuais registradas na plataforma."""

    try:
        registro = obter_luftbase().temas.registro
    except Exception:
        registro = criar_registro_padrao()

    temas = registro.listar()
    click.echo(f"temas_registrados={len(temas)}")
    for t in temas:
        modos_str = ", ".join(sorted(m.value for m in t.modos))
        fixo = " modo_fixo" if t.modo_unico is not None else ""
        click.echo(
            f"  {t.identificador}: nome={t.nome!r} versao={t.versao} url={t.url_css} "
            f"modos=[{modos_str}]{fixo}"
        )


@tema.command("validar")
@click.argument("arquivo", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--modos",
    default="claro,escuro",
    show_default=True,
    help="Modos que o tema CSS deve oferecer (ex.: 'claro' para um tema de modo unico).",
)
def tema_validar(arquivo: Path, modos: str) -> None:
    """Valida um arquivo de tokens CSS ou um manifesto JSON de tema."""

    conteudo = arquivo.read_text(encoding="utf-8")
    extensao = arquivo.suffix.lower()

    if extensao == ".css":
        problemas = validar_css_tema(conteudo, _modos_da_opcao(modos))
        if problemas:
            click.echo(f"tema={arquivo.name} status=invalido")
            for prob in problemas:
                click.echo(f"  - {prob}")
            raise click.exceptions.Exit(1)
        click.echo(f"tema={arquivo.name} status=valido tokens=completos")
        return

    if extensao in {".json", ".manifest"}:
        try:
            dados = json.loads(conteudo)
            if not isinstance(dados, dict):
                raise click.ClickException("O manifesto deve ser um objeto JSON.")
            modos_json = dados.get("modos")
            argumentos_modos: dict[str, object] = {}
            if modos_json is not None:
                if not isinstance(modos_json, list):
                    raise click.ClickException("'modos' deve ser uma lista, ex.: [\"claro\"].")
                argumentos_modos["modos"] = _modos_da_opcao(",".join(map(str, modos_json)))
            manifesto = ManifestoTema(
                identificador=str(dados.get("identificador") or ""),
                nome=str(dados.get("nome") or ""),
                versao=str(dados.get("versao") or ""),
                url_css=str(dados.get("url_css") or ""),
                descricao=str(dados.get("descricao") or ""),
                cores_previa=tuple(str(c) for c in dados.get("cores_previa") or ()),
                **argumentos_modos,  # type: ignore[arg-type]
            )
            click.echo(
                f"manifesto={manifesto.identificador} status=valido versao={manifesto.versao}"
            )
        except ErroConfiguracao as erro:
            click.echo(f"manifesto={arquivo.name} status=invalido erro={erro}")
            raise click.exceptions.Exit(1) from erro
        except Exception as erro:
            raise click.ClickException(f"Erro ao processar manifesto: {erro}") from erro
        return

    raise click.ClickException("Formato nao suportado. Informe um arquivo .css ou .json.")
