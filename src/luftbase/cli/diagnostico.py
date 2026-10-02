"""Comandos de diagnostico sanitizado da plataforma LuftBase."""

from __future__ import annotations

import click
from flask.cli import with_appcontext

from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.plataforma import obter_luftbase


@click.group("diagnostico")
def diagnostico() -> None:
    """Diagnostico sanitizado de configuracao e dependencias."""


@diagnostico.command("configuracao")
def diagnostico_configuracao() -> None:
    """Valida e exibe a configuracao sem revelar segredos."""

    try:
        configuracao = ConfiguracaoLuftBase.de_ambiente()
    except ErroConfiguracao as erro:
        click.echo(f"status=invalida erro={erro}")
        raise click.exceptions.Exit(1) from erro

    click.echo("status=valida")
    click.echo(f"ambiente={configuracao.aplicacao.ambiente.value}")
    click.echo(f"sistema_id={configuracao.aplicacao.sistema_id}")
    click.echo(f"aplicacao_nome={configuracao.aplicacao.nome}")
    click.echo("sistema_id=resolvido_no_core_apos_conexao")
    click.echo(f"versao={configuracao.aplicacao.versao or 'nao_informada'}")
    click.echo(f"cofre_endereco={configuracao.cofre.endereco}")
    click.echo(f"cofre_namespace={configuracao.cofre.namespace}")
    token_prot = "configurado" if configuracao.cofre.token_protegido else "ausente"
    click.echo(f"cofre_token_protegido={token_prot}")
    token_aces = "configurado" if configuracao.cofre.token_acesso else "ausente"
    click.echo(f"cofre_token_acesso={token_aces}")
    click.echo(f"ldap_servidor={configuracao.diretorio.servidor}")
    click.echo(f"ldap_dominio={configuracao.diretorio.dominio}")
    click.echo(f"ldap_transporte={configuracao.diretorio.transporte}")
    click.echo(f"ldap_porta={configuracao.diretorio.porta or 'padrao'}")
    click.echo(f"ldap_timeout_segundos={configuracao.diretorio.timeout_segundos}")
    click.echo(f"sessao_cookie_nome={configuracao.sessao.nome_cookie}")
    click.echo(f"sessao_cookie_caminho={configuracao.sessao.caminho_cookie}")
    click.echo(f"sessao_cookie_samesite={configuracao.sessao.same_site}")
    click.echo(f"sessao_cookie_seguro={configuracao.sessao.cookie_seguro}")
    click.echo(f"sessao_ttl_minutos={configuracao.sessao.ttl_minutos}")
    click.echo(f"autorizacao_ttl_segundos={configuracao.autorizacao.ttl_resultado_segundos}")
    click.echo(f"autorizacao_revisao_ttl_segundos={configuracao.autorizacao.ttl_revisao_segundos}")
    click.echo(f"autorizacao_max_chaves={configuracao.autorizacao.maximo_chaves_consulta}")

    try:
        configuracao.validar_para_inicializacao()
        click.echo("pronta_para_inicializacao=sim")
    except ErroConfiguracao as erro:
        click.echo(f"pronta_para_inicializacao=nao motivo={erro}")


@diagnostico.command("saude")
@with_appcontext
def diagnostico_saude() -> None:
    """Executa checagem de saude das dependencias sem expor dados sensiveis."""

    try:
        estado = obter_luftbase()
    except Exception as erro:
        raise click.ClickException(
            "O LuftBase nao esta inicializado no contexto Flask atual."
        ) from erro

    resultados_bancos = estado.bancos.verificar_saude()
    redis_disponivel = estado.infraestrutura.armazenamento_sessoes.verificar_saude()

    click.echo("dependencias:")
    tudo_ok = True
    for res in resultados_bancos:
        tudo_ok = tudo_ok and res.disponivel
        click.echo(
            f"  {res.dependencia}: status={res.codigo} disponivel={res.disponivel} "
            f"latencia_ms={res.latencia_ms}"
        )

    tudo_ok = tudo_ok and redis_disponivel
    click.echo(
        f"  sessoes_redis: status={'ok' if redis_disponivel else 'indisponivel'} "
        f"disponivel={redis_disponivel}"
    )
    click.echo(f"status_geral={'ok' if tudo_ok else 'indisponivel'}")
    if not tudo_ok:
        raise click.exceptions.Exit(1)
