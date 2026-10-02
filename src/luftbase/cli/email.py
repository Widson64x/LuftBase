"""Comandos de verificacao da integracao de e-mail."""

from __future__ import annotations

import click

from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais
from luftbase.integracoes.email import ServicoEmail
from luftbase.nucleo.excecoes import ErroConfiguracao, ErroCredencial, ErroEmail, ErroLuftBase


@click.group("email")
def email() -> None:
    """Verificacao da conta SMTP guardada no Vault."""


@email.command("testar")
@click.option("--para", "destinatarios", required=True, multiple=True, help="Destinatario.")
def email_testar(destinatarios: tuple[str, ...]) -> None:
    """Envia o template de teste usando o segredo `integracoes/email` do ambiente."""

    try:
        configuracao = ConfiguracaoLuftBase.de_ambiente()
        configuracao.validar_para_inicializacao()
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
        namespace=configuracao.cofre.namespace,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )
    assert configuracao.cofre.token_protegido is not None  # Validado acima.
    assert configuracao.cofre.token_acesso is not None

    try:
        token_vault = DesprotetorFernet(configuracao.cofre.token_acesso).revelar(
            configuracao.cofre.token_protegido
        )
        provedor = ClienteVaultHvac(configuracao.cofre.endereco, Segredo(token_vault))
        credencial = CarregadorCredenciais(provedor).carregar_email(caminhos.email)
    except ErroCredencial as erro:
        raise click.ClickException(f"Segredo de e-mail invalido: {erro}") from erro
    except ErroLuftBase as erro:
        raise click.ClickException(f"Falha ao ler {caminhos.email!r}: {erro}") from erro

    servico = ServicoEmail(
        credencial,
        ambiente=configuracao.aplicacao.ambiente,
        nome_sistema="LuftBase",
    )
    try:
        resultado = servico.enviar(
            destinatarios,
            "Teste de envio de e-mail",
            template="luftbase/email/teste.html",
            contexto={"servidor": f"{credencial.host}:{credencial.porta}"},
        )
    except ErroEmail as erro:
        raise click.ClickException(str(erro)) from erro

    click.echo(f"caminho={caminhos.email}")
    click.echo(f"servidor={credencial.host}:{credencial.porta} ({credencial.seguranca.value})")
    click.echo(f"remetente={credencial.remetente}")
    click.echo(f"modo_teste={'sim' if resultado.redirecionado else 'nao'}")
    click.echo(f"destinatarios={', '.join(resultado.destinatarios)}")
    if not resultado.sucesso:
        raise click.ClickException(resultado.erro or "Falha no envio.")
    if resultado.recusados:
        click.echo(f"recusados={', '.join(resultado.recusados)}")
    click.echo("envio=ok")
