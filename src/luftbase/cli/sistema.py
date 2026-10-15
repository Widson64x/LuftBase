"""Cadastro de sistemas que nao integram o LuftBase (C#, executaveis, ferramentas de terceiros)."""

from __future__ import annotations

import click

from luftbase.cli.operador import (
    AMBIENTES_DA_CLI,
    VAULT_URL_PADRAO,
    abrir_sessao_operador,
    normalizar_ambiente_da_cli,
)
from luftbase.infraestrutura.cadastro_sistema import (
    GRUPO_TI_PADRAO,
    ErroCadastroSistema,
    cadastrar_sistema,
    exigir_core_atualizado,
)
from luftbase.persistencia.core.categorias_sistema import CODIGOS_CATEGORIA
from luftbase.web.configuracoes import validar_payload_novo_sistema


@click.group("sistema")
def sistema() -> None:
    """Cadastro de sistemas no catalogo corporativo."""


@sistema.command("externo")
@click.argument("nome")
@click.option(
    "--tipo-acesso",
    type=click.Choice(["web", "download", "sem-acesso"]),
    default="web",
    show_default=True,
    help="web abre o --link; download leva ao --url-download; sem-acesso so aparece no catalogo.",
)
@click.option("--link", default=None, help="Rota ou URL que o card abre (tipo web).")
@click.option(
    "--url-download",
    default=None,
    help="Instalador ou pagina do atualizador (tipo download), ex.: /Luft-Workspace/atualizador.",
)
@click.option(
    "--categoria",
    type=click.Choice([c for c in CODIGOS_CATEGORIA if c != "HUB"]),
    default="APLICACAO",
    show_default=True,
)
@click.option("--descricao", default=None)
@click.option("--icone", default="ph-bold ph-app-window", show_default=True)
@click.option("--cor", default=None, help="Cor tematica #RRGGBB.")
@click.option("--responsavel", default=None, help="Equipe ou area responsavel.")
@click.option("--contato-suporte", default=None)
@click.option(
    "--grupo-acesso",
    default=GRUPO_TI_PADRAO,
    show_default=True,
    type=int,
    help="Grupo que recebe a permissao de ver o card.",
)
@click.option(
    "--ambiente",
    type=click.Choice(AMBIENTES_DA_CLI),
    default="desenvolvimento",
    show_default=True,
)
@click.option("--usuario-banco", default=None, help="Usuario administrativo do PostgreSQL.")
@click.option("--vault-url", default=VAULT_URL_PADRAO, show_default=True)
@click.option("--vault-mount", default="secret", show_default=True)
@click.option("--vault-namespace", default="luft", show_default=True)
@click.option("--banco-host", default=None)
@click.option("--banco-porta", default=None, type=int)
@click.option("--banco-nome", default=None)
@click.option("--sim", is_flag=True, help="Nao pede confirmacao.")
def externo(
    nome: str,
    tipo_acesso: str,
    link: str | None,
    url_download: str | None,
    categoria: str,
    descricao: str | None,
    icone: str,
    cor: str | None,
    responsavel: str | None,
    contato_suporte: str | None,
    grupo_acesso: int,
    ambiente: str,
    usuario_banco: str | None,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
    banco_host: str | None,
    banco_porta: int | None,
    banco_nome: str | None,
    sim: bool,
) -> None:
    """Cadastra uma ferramenta externa: card e link, sem schema, role nem segredo no Vault.

    O card aparece so para quem tem a permissao base do sistema; o LuftBase nao controla o
    login nem o banco da ferramenta.
    """

    ambiente = normalizar_ambiente_da_cli(ambiente)
    valores, erros = validar_payload_novo_sistema(
        {
            "Nome": nome,
            "Categoria": categoria,
            "Descricao": descricao,
            "Icone": icone,
            "Cor": cor,
            "Link": link,
            "UrlDownload": url_download,
            "Responsavel": responsavel,
            "ContatoSuporte": contato_suporte,
            "IntegraLuftbase": False,
            "TipoAcesso": tipo_acesso.replace("-", "_").upper(),
        }
    )
    if erros:
        detalhe = "; ".join(f"{campo}: {texto}" for campo, texto in erros.items())
        raise click.ClickException(f"Dados invalidos: {detalhe}")

    click.echo(f"sistema={nome} ambiente={ambiente} integra_luftbase=false")
    click.echo(f"tipo_acesso={valores['tipo_acesso']} link={link or '-'}")
    if not sim:
        click.confirm("Cadastrar este sistema externo?", abort=True)

    sessao = abrir_sessao_operador(
        ambiente=ambiente,
        vault_url=vault_url,
        vault_mount=vault_mount,
        namespace=vault_namespace,
        usuario_banco=usuario_banco,
        banco_host=banco_host,
        banco_porta=banco_porta,
        banco_nome=banco_nome,
        exigir_alias=False,
    )
    try:
        exigir_core_atualizado(sessao.provisionador.engine_administrativo())
        resultado = cadastrar_sistema(
            sessao.provisionador.engine_administrativo(),
            valores,
            grupo_acesso=grupo_acesso,
            ao_etapa=lambda texto: click.echo(f"  + {texto}"),
        )
    except ErroCadastroSistema as falha:
        raise click.ClickException(f"Nada foi gravado. {falha.mensagem}") from falha
    finally:
        sessao.provisionador.encerrar()

    click.echo(f"sistema_id={resultado.id_sistema}")
