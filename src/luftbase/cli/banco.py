"""Comandos seguros de inspecao, adocao e evolucao do schema core."""

from __future__ import annotations

import contextlib
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

if TYPE_CHECKING:
    from luftbase.infraestrutura.espelho_banco import Servidor

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


@banco.command("tamanho-logs")
@with_appcontext
def tamanho_logs() -> None:
    """Mostra linhas e tamanho (MB, no PostgreSQL) das tabelas de log e o registro mais antigo.

    Use antes de definir os prazos de retencao: decida com o volume real, nao no chute.
    """

    from luftbase.observabilidade.retencao import mais_antigo, tamanho_tabelas

    try:
        with obter_luftbase().bancos.core.leitura() as sessao:
            tamanhos = tamanho_tabelas(sessao)
            antigos = mais_antigo(sessao)
    except Exception as erro:
        raise click.ClickException("Nao foi possivel medir as tabelas de log.") from erro
    for item in tamanhos:
        mb = "n/d" if item["mb"] is None else f"{item['mb']} MB"
        linhas = "n/d" if item["linhas"] is None else item["linhas"]
        click.echo(f"{item['tabela']}: linhas={linhas} tamanho={mb}")
    for tabela, quando in antigos.items():
        click.echo(
            f"mais_antigo.{tabela}={quando.isoformat(timespec='seconds') if quando else '-'}"
        )


@banco.command("retencao")
@click.option(
    "--simular", "modo", flag_value="simular", default=True, help="Mostra o que sairia (padrao)."
)
@click.option(
    "--executar", "modo", flag_value="executar", help="Apaga de verdade o que passou do prazo."
)
@click.option(
    "--arquivar-em",
    "pasta",
    type=click.Path(file_okay=False, path_type=str),
    default=None,
    help="Pasta onde cada lote e gravado em CSV compactado ANTES de apagar.",
)
@click.option("--sem-arquivo", is_flag=True, help="Permite apagar sem arquivar (nao recomendado).")
@click.option("--lote", default=1000, show_default=True, type=int, help="Linhas por COMMIT.")
@with_appcontext
def retencao(modo: str, pasta: str | None, sem_arquivo: bool, lote: int) -> None:
    """Aplica a politica de retencao dos logs, sessoes e alertas resolvidos.

    Prazos por variavel (LUFT_RETENCAO_ACESSO_DIAS=180, _SESSOES_DIAS=365, _EVENTOS_DIAS=730,
    _ALERTAS_DIAS=180). O padrao e simular; com --executar e preciso --arquivar-em ou --sem-arquivo.
    """

    from luftbase.observabilidade.retencao import Politica, executar, simular

    politica = Politica.de_ambiente()
    estado = obter_luftbase()
    click.echo(
        f"prazos: acesso={politica.acesso_dias}d sessoes={politica.sessoes_dias}d "
        f"eventos={politica.eventos_dias}d alertas={politica.alertas_dias}d"
    )
    if modo != "executar":
        with estado.bancos.core.leitura() as sessao:
            itens = simular(sessao, politica)
        for item in itens:
            click.echo(
                f"{item.tabela}: vencidas={item.vencidas} (anteriores a {item.corte:%Y-%m-%d %H:%M})"
            )
        click.echo("modo=simular (nada foi apagado; use --executar --arquivar-em PASTA)")
        return

    if pasta is None and not sem_arquivo:
        raise click.UsageError("Para --executar informe --arquivar-em PASTA (ou --sem-arquivo).")
    if lote < 1:
        raise click.UsageError("--lote deve ser maior que zero.")
    resultado = executar(
        estado.bancos,
        politica,
        pasta_arquivo=Path(pasta) if pasta else None,
        tamanho_lote=lote,
        ao_progresso=lambda mensagem: click.echo(f"  {mensagem}"),
    )
    for item in resultado.tabelas:
        extra = f" arquivadas={item.arquivadas} em {item.arquivo}" if item.arquivo else ""
        desligadas = f" trilha_preservada={item.desligadas}" if item.desligadas else ""
        click.echo(f"{item.tabela}: apagadas={item.apagadas}{extra}{desligadas}")
    with contextlib.suppress(Exception):
        from luftbase.observabilidade import EventoDominio, SeveridadeAuditoria

        estado.auditoria.registrar_evento(
            EventoDominio(
                acao="RETENCAO_EXECUTADA",
                recurso="LOGS",
                descricao=f"Retencao apagou {resultado.total_apagadas} registro(s) de log.",
                severidade=SeveridadeAuditoria.MEDIA,
            )
        )
    for erro in resultado.erros:
        click.echo(f"erro={erro}", err=True)
    if resultado.erros:
        raise click.exceptions.Exit(1)


def _conectar_postgresql(servidor: Servidor, banco: str) -> Any:
    """Conexao autocommit (necessaria para CREATE/DROP DATABASE) com timeout curto."""

    import psycopg

    from luftbase.infraestrutura.espelho_banco import ErroEspelho

    try:
        return psycopg.connect(
            host=servidor.host,
            port=servidor.porta,
            dbname=banco,
            user=servidor.usuario,
            password=servidor.senha,
            connect_timeout=10,
            autocommit=True,
        )
    except psycopg.OperationalError as erro:
        motivo = (
            "usuario ou senha recusados"
            if "authentication failed" in str(erro)
            else (str(erro).splitlines()[0][:200])
        )
        raise ErroEspelho(
            f"Nao foi possivel conectar em {servidor.host}:{servidor.porta} como "
            f"{servidor.usuario!r}: {motivo}."
        ) from erro


@banco.command("espelhar")
@click.option(
    "--origem",
    type=click.Choice(["homologacao", "desenvolvimento"]),
    default="homologacao",
    show_default=True,
    help="Ambiente de onde copiar. Producao nunca e aceita.",
)
@click.option(
    "--usuario-banco", default=None, help="Usuario administrativo do PostgreSQL de origem."
)
@click.option("--vault-url", default="http://172.16.200.80:8200", show_default=True)
@click.option("--vault-mount", default="secret", show_default=True)
@click.option("--vault-namespace", default="luft", show_default=True)
@click.option(
    "--destino-host",
    default="localhost",
    show_default=True,
    help="Somente a propria maquina: localhost, 127.0.0.1 ou ::1.",
)
@click.option("--destino-porta", default=5432, show_default=True, type=int)
@click.option(
    "--destino-banco",
    default=None,
    help="Nome do banco local (padrao: o da origem trocando o sufixo _hml por _dev).",
)
@click.option("--usuario-destino", default="postgres", show_default=True)
@click.option("--recriar", is_flag=True, help="Apaga o banco local se existir e copia de novo.")
@click.option(
    "--pg-bin",
    default=None,
    type=click.Path(path_type=Path, file_okay=False),
    help="Pasta bin do PostgreSQL com pg_dump e pg_restore.",
)
@click.option(
    "--sem-vault",
    is_flag=True,
    help="Nao cria no Vault de desenvolvimento os segredos dos sistemas do banco copiado.",
)
@click.option(
    "--substituir-segredos",
    is_flag=True,
    help="Troca segredos de desenvolvimento que apontam para outro schema ou role.",
)
@click.option(
    "--sobrescrever-senhas",
    is_flag=True,
    help="Troca a senha das roles que ja existem localmente pela da origem (padrao: mantem).",
)
@click.option(
    "--somente-estrutura",
    is_flag=True,
    help="Copia so a estrutura (sem nenhum dado): banco limpo para desenvolver.",
)
@click.option(
    "--via-wsl",
    is_flag=True,
    help="Roda pg_dump/pg_restore dentro do WSL (use quando o PostgreSQL local vive no WSL).",
)
@click.option(
    "--configurar-env",
    default=None,
    type=click.Path(path_type=Path, dir_okay=False),
    help="`.env` de um projeto a apontar para o espelho (LUFT_BANCO_LOCAL_HOST/PORTA/NOME).",
)
@click.option("--sim", is_flag=True, help="Nao pede confirmacao.")
def espelhar_comando(
    origem: str,
    usuario_banco: str | None,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
    destino_host: str,
    destino_porta: int,
    destino_banco: str | None,
    usuario_destino: str,
    recriar: bool,
    pg_bin: Path | None,
    sem_vault: bool,
    substituir_segredos: bool,
    sobrescrever_senhas: bool,
    somente_estrutura: bool,
    via_wsl: bool,
    configurar_env: Path | None,
    sim: bool,
) -> None:
    """Copia o banco de homologacao para um PostgreSQL local, para o dev trabalhar sem risco.

    A origem so e lida. A copia e integral e leva usuarios, sessoes e logs do ambiente: trate o
    banco local como dado de homologacao. As roles de aplicacao vao com o mesmo verificador de
    senha, entao as credenciais do Vault valem no espelho; a aplicacao so precisa de
    LUFT_BANCO_LOCAL_HOST e LUFT_BANCO_LOCAL_NOME (use --configurar-env).
    """

    import getpass

    from luftbase.cli.operador import abrir_sessao_operador, normalizar_ambiente_da_cli
    from luftbase.infraestrutura.espelho_banco import (
        ErroEspelho,
        Servidor,
        espelhar,
        exigir_destino_local,
        ferramentas_no_wsl,
        linhas_env_banco_local,
        localizar_ferramentas,
        nome_local_padrao,
        validar_nome_banco,
    )
    from luftbase.infraestrutura.espelho_banco import (
        configurar_env as configurar_env_projeto,
    )

    ambiente = normalizar_ambiente_da_cli(origem)
    try:
        exigir_destino_local(destino_host)
        ferramentas = ferramentas_no_wsl() if via_wsl else localizar_ferramentas(pg_bin)
        sessao = abrir_sessao_operador(
            ambiente=ambiente,
            vault_url=vault_url,
            vault_mount=vault_mount,
            namespace=vault_namespace,
            usuario_banco=usuario_banco,
            exigir_alias=False,
        )
    except ErroEspelho as erro:
        raise click.ClickException(str(erro)) from erro

    try:
        fonte = sessao.destino
        senha_origem = sessao.senha_banco.revelar() if sessao.senha_banco else ""
        servidor_origem = Servidor(
            fonte.host, fonte.porta, fonte.banco, sessao.usuario_banco, senha_origem
        )
        nome_local = validar_nome_banco(destino_banco or nome_local_padrao(fonte.banco))
        click.echo(f"origem={fonte.host}:{fonte.porta}/{fonte.banco} ({ambiente}, somente leitura)")
        click.echo(f"destino={destino_host}:{destino_porta}/{nome_local}")
        if somente_estrutura:
            click.echo("modo=somente-estrutura: nenhum dado de usuarios, sessoes ou logs e copiado")
        else:
            click.echo(
                "aviso=a copia e integral: leva usuarios, sessoes e logs de "
                f"{ambiente} para esta maquina"
            )
        if recriar:
            digitado = click.prompt(
                f"Digite o nome do banco local ({nome_local}) para confirmar que ele sera APAGADO",
                type=str,
            ).strip()
            if digitado != nome_local:
                raise click.ClickException("Confirmacao recusada; nada foi alterado.")
        elif not sim:
            click.confirm("Copiar o banco para esta maquina?", abort=True)

        senha_destino = getpass.getpass(
            f"Senha de {usuario_destino} no PostgreSQL LOCAL ({destino_host}:{destino_porta}): "
        )
        servidor_destino = Servidor(
            destino_host, destino_porta, nome_local, usuario_destino, senha_destino
        )
        resultado = espelhar(
            servidor_origem,
            servidor_destino,
            ferramentas=ferramentas,
            recriar=recriar,
            via_wsl=via_wsl,
            somente_estrutura=somente_estrutura,
            sobrescrever_senhas=sobrescrever_senhas,
            conectar=_conectar_postgresql,
            ao_etapa=lambda texto: click.echo(f"  + {texto}"),
        )
    except ErroEspelho as erro:
        raise click.ClickException(str(erro)) from erro
    finally:
        sessao.provisionador.encerrar()

    click.echo(f"espelho=concluido banco={resultado.banco_destino} roles={len(resultado.roles)}")
    if resultado.roles_ignoradas:
        click.echo(
            f"roles_ignoradas={','.join(resultado.roles_ignoradas)} (nao existem localmente)"
        )
    if not sem_vault and not somente_estrutura:
        _espelhar_vault_dev(
            sessao,
            servidor_destino,
            usuario_destino=usuario_destino,
            vault_url=vault_url,
            vault_mount=vault_mount,
            vault_namespace=vault_namespace,
            substituir=substituir_segredos,
        )
    if configurar_env is not None:
        mudou = configurar_env_projeto(configurar_env, servidor_destino)
        click.echo(f"env={configurar_env} {'atualizado' if mudou else 'ja estava configurado'}")
    else:
        click.echo("para usar o espelho, ponha no .env do projeto:")
        for linha in linhas_env_banco_local(servidor_destino):
            click.echo(f"  {linha}")


def _espelhar_vault_dev(
    sessao: Any,
    servidor_destino: Servidor,
    *,
    usuario_destino: str,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
    substituir: bool,
) -> None:
    """Cria no Vault de desenvolvimento um segredo por sistema do core copiado."""

    from luftbase.infraestrutura.cadastro_sistema import (
        ErroCadastroSistema,
        descobrir_destino_core,
    )
    from luftbase.infraestrutura.cofre.credenciais import Segredo
    from luftbase.infraestrutura.espelho_vault import (
        AMBIENTE_DO_VAULT,
        espelhar_vault,
        ler_sistemas_locais,
    )
    from luftbase.infraestrutura.provisionamento_sistema import (
        CredenciaisOperador,
        DestinoProvisionamento,
        ProvisionadorSistema,
    )

    cliente = sessao.provisionador.cliente_vault
    try:
        conexao_dev = descobrir_destino_core(
            cliente,
            ambiente=AMBIENTE_DO_VAULT,
            namespace=vault_namespace,
            vault_url=vault_url,
            mount=vault_mount,
        )
    except ErroCadastroSistema as falha:
        raise click.ClickException(f"Vault de desenvolvimento: {falha.mensagem}") from falha
    click.echo(f"vault={vault_namespace}/{AMBIENTE_DO_VAULT} conexao={conexao_dev.alias_conexao}")
    if conexao_dev.banco != servidor_destino.banco:
        click.echo(
            f"aviso=a conexao '{conexao_dev.alias_conexao}' do Vault aponta para o banco "
            f"{conexao_dev.banco!r}, nao para {servidor_destino.banco!r}: as aplicacoes em "
            "desenvolvimento nao enxergarao o espelho ate voce ajustar nome_banco no Vault "
            "ou usar LUFT_BANCO_LOCAL_NOME."
        )
    destino = DestinoProvisionamento(
        ambiente=AMBIENTE_DO_VAULT,
        namespace=vault_namespace,
        vault_url=vault_url,
        host=servidor_destino.host,
        porta=servidor_destino.porta,
        banco=servidor_destino.banco,
        sistema_referencia=0,
        mount=vault_mount,
        alias_conexao=conexao_dev.alias_conexao,
    )
    provisionador = ProvisionadorSistema(
        destino,
        CredenciaisOperador(usuario_destino, sessao.token_vault, Segredo(servidor_destino.senha)),
        criar_cliente_vault=lambda _url, _token: cliente,
    )
    try:
        with _conectar_postgresql(servidor_destino, servidor_destino.banco) as conexao:
            sistemas = ler_sistemas_locais(conexao)
        click.echo(f"sistemas_no_core_copiado={len(sistemas)}")
        resultado = espelhar_vault(
            provisionador,
            sistemas,
            conexao_dev.alias_conexao or "",
            substituir=substituir,
            ao_etapa=lambda texto: click.echo(f"  + {texto}"),
        )
    finally:
        provisionador.encerrar()
    for item in (*resultado.conflitos, *resultado.falhas):
        click.echo(f"  ! {item}")
    click.echo(
        f"vault_espelhado=criados:{len(resultado.criados)} mantidos:{len(resultado.mantidos)} "
        f"conflitos:{len(resultado.conflitos)} falhas:{len(resultado.falhas)}"
    )
    if resultado.falhas:
        raise click.exceptions.Exit(1)


def _conectar_somente_leitura(servidor: Servidor) -> Any:
    """Conexao de leitura: o servidor recusa qualquer escrita, mesmo por engano."""

    import psycopg

    from luftbase.infraestrutura.espelho_banco import ErroEspelho

    try:
        return psycopg.connect(
            host=servidor.host,
            port=servidor.porta,
            dbname=servidor.banco,
            user=servidor.usuario,
            password=servidor.senha,
            connect_timeout=10,
            options="-c default_transaction_read_only=on",
        )
    except psycopg.OperationalError as erro:
        motivo = (
            "usuario ou senha recusados"
            if "authentication failed" in str(erro)
            else str(erro).splitlines()[0][:200]
        )
        raise ErroEspelho(
            f"Nao foi possivel conectar em {servidor.host}:{servidor.porta}/{servidor.banco} "
            f"como {servidor.usuario!r}: {motivo}."
        ) from erro


@banco.command("comparar")
@click.option(
    "--origem",
    type=click.Choice(["desenvolvimento", "homologacao"]),
    default="desenvolvimento",
    show_default=True,
)
@click.option(
    "--destino",
    type=click.Choice(["homologacao", "producao"]),
    default="homologacao",
    show_default=True,
)
@click.option(
    "--schema",
    "schemas",
    multiple=True,
    help="Schema a comparar (repita para varios). Sem ele, todos os da origem, exceto o core.",
)
@click.option("--usuario-origem", default=None, help="Usuario do PostgreSQL de origem.")
@click.option("--usuario-destino", default=None, help="Usuario do PostgreSQL de destino.")
@click.option(
    "--saida",
    default=None,
    type=click.Path(path_type=Path, file_okay=False),
    help="Pasta onde gravar os .sql (padrao: a atual).",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", show_default=True)
@click.option("--vault-mount", default="secret", show_default=True)
@click.option("--vault-namespace", default="luft", show_default=True)
def comparar_comando(
    origem: str,
    destino: str,
    schemas: tuple[str, ...],
    usuario_origem: str | None,
    usuario_destino: str | None,
    saida: Path | None,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
) -> None:
    """Compara a estrutura dos schemas entre dois ambientes e gera o SQL para igualar o destino.

    Le so o catalogo dos dois bancos (nenhum dado) e escreve um arquivo .sql por schema com o que
    falta no destino. Nada e aplicado: o dev revisa o arquivo, roda em homologacao e, se der certo,
    o mesmo arquivo em producao. Divergencias que um script nao resolve com seguranca (tipo, nulidade,
    padrao, tabela sobrando) aparecem no relatorio como revisao manual. O core evolui por Alembic:
    aqui so se compara a revisao registrada em cada banco.
    """

    from luftbase.cli.operador import abrir_cliente_vault, pedir_banco_do_ambiente
    from luftbase.infraestrutura.comparacao_estrutura import (
        comparar_schemas,
        listar_schemas,
        revisao_alembic,
    )
    from luftbase.infraestrutura.provisionamento_sistema import nome_da_role

    if origem == destino:
        raise click.UsageError("Origem e destino precisam ser ambientes diferentes.")
    from luftbase.infraestrutura.espelho_banco import ErroEspelho, Servidor

    cliente = abrir_cliente_vault(vault_url=vault_url, vault_mount=vault_mount)
    pontas = []
    for ambiente, usuario in ((origem, usuario_origem), (destino, usuario_destino)):
        dados, login, senha = pedir_banco_do_ambiente(
            cliente,
            ambiente=ambiente,
            vault_url=vault_url,
            vault_mount=vault_mount,
            namespace=vault_namespace,
            usuario=usuario,
        )
        pontas.append(Servidor(dados.host, dados.porta, dados.banco, login, senha.revelar()))

    try:
        with (
            _conectar_somente_leitura(pontas[0]) as conexao_origem,
            _conectar_somente_leitura(pontas[1]) as conexao_destino,
        ):
            rev_origem, rev_destino = (
                revisao_alembic(conexao_origem),
                revisao_alembic(conexao_destino),
            )
            click.echo(f"core: {origem}={rev_origem} {destino}={rev_destino}")
            if rev_origem != rev_destino:
                click.echo(
                    "aviso=o core esta em revisoes diferentes; ele evolui por `banco atualizar`, "
                    "nao por este script"
                )
            lista = list(schemas) or listar_schemas(conexao_origem)
            resultados = comparar_schemas(
                conexao_origem,
                conexao_destino,
                lista,
                role_destino=lambda schema: nome_da_role(schema, destino),
                nome_origem=origem,
                nome_destino=destino,
            )
    except ErroEspelho as erro:
        raise click.ClickException(str(erro)) from erro

    pasta = saida or Path.cwd()
    pasta.mkdir(parents=True, exist_ok=True)
    manuais = 0
    for resultado in resultados:
        if resultado.iguais:
            click.echo(f"{resultado.schema}: igual")
            continue
        click.echo(f"{resultado.schema}: {len(resultado.diferencas)} diferenca(s)")
        for item in resultado.diferencas:
            marca = "  +" if item.automatica else "  !"
            click.echo(f"{marca} {item.descricao}")
        manuais += len(resultado.manuais)
        if resultado.script:
            arquivo = pasta / f"estrutura_{resultado.schema}_{origem}_para_{destino}.sql"
            arquivo.write_text(resultado.script, encoding="utf-8")
            click.echo(f"  sql={arquivo}")
    legenda = "legenda: + o script resolve, ! exige revisao manual"
    click.echo(legenda if any(not r.iguais for r in resultados) else "estruturas iguais")
    if manuais:
        click.echo(f"revisao_manual={manuais}")


@banco.command("atualizar-core")
@click.option(
    "--ambiente",
    type=click.Choice(["desenvolvimento"]),
    default="desenvolvimento",
    show_default=True,
    help="So o ambiente de desenvolvimento (local). Homologacao evolui pelo Workspace.",
)
@click.option("--usuario-banco", default=None, help="Usuario administrativo do PostgreSQL.")
@click.option("--vault-url", default="http://172.16.200.80:8200", show_default=True)
@click.option("--vault-mount", default="secret", show_default=True)
@click.option("--vault-namespace", default="luft", show_default=True)
@click.option("--sim", is_flag=True, help="Nao pede confirmacao.")
def atualizar_core(
    ambiente: str,
    usuario_banco: str | None,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
    sim: bool,
) -> None:
    """Leva o core do desenvolvimento a revisao deste LuftBase, sem precisar subir uma aplicacao.

    Serve para o banco local copiado de homologacao, que fica numa revisao antiga. Usa as migrations
    empacotadas e o usuario administrativo que voce informa (a role de runtime nao altera
    estrutura). Aplica as migrations pendentes e sincroniza o catalogo do Workspace, como o
    `banco atualizar`. Nunca roda sozinho na inicializacao de uma aplicacao.
    """

    from luftbase.cli.operador import (
        abrir_cliente_vault,
        engine_do_operador,
        pedir_banco_do_ambiente,
    )
    from luftbase.infraestrutura.cadastro_sistema import revisao_cabeca

    cliente = abrir_cliente_vault(vault_url=vault_url, vault_mount=vault_mount)
    destino, login, senha = pedir_banco_do_ambiente(
        cliente,
        ambiente=ambiente,
        vault_url=vault_url,
        vault_mount=vault_mount,
        namespace=vault_namespace,
        usuario=usuario_banco,
    )
    engine = engine_do_operador(destino, login, senha)
    try:
        try:
            with engine.connect() as conexao:
                atual = conexao.exec_driver_sql(
                    "SELECT version_num FROM core.alembic_version"
                ).scalar()
        except Exception as erro:
            detalhe = str(getattr(erro, "orig", erro)).splitlines()[0][:200]
            raise click.ClickException(
                f"Nao foi possivel ler core.alembic_version ({detalhe}). Confira usuario e senha."
            ) from erro
        alvo = revisao_cabeca()
        click.echo(f"core: revisao_atual={atual} revisao_alvo={alvo}")
        if atual == alvo:
            click.echo("atualizacao=nada_a_fazer")
            return
        if not sim:
            click.confirm(f"Aplicar as migrations pendentes em {destino.banco}?", abort=True)
        try:
            with engine.begin() as conexao:
                command.upgrade(criar_configuracao_alembic(conexao=conexao), "head")
                sincronizar_catalogo_workspace(conexao)
        except Exception as erro:
            detalhe = str(getattr(erro, "orig", erro)).splitlines()[0][:300]
            raise click.ClickException(f"Nao foi possivel atualizar o core: {detalhe}") from erro
    finally:
        engine.dispose()
    click.echo("atualizacao=concluida")
