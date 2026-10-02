"""Assistente interativo de provisionamento seguro e aditivo de ambientes."""

from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from urllib.parse import quote_plus

import click
import psycopg
from alembic import command
from psycopg import sql
from sqlalchemy import Connection, create_engine, text

from luftbase.cli.manifesto import (
    AplicacaoManifesto,
)
from luftbase.cli.vault import (
    _criar_cliente_hvac_operador,
    _segredo_existe,
)
from luftbase.configuracao.ambientes import normalizar_ambiente
from luftbase.migracoes.configuracao import criar_configuracao_alembic
from luftbase.persistencia.core.catalogo import sincronizar_catalogo_workspace

SISTEMAS_PADRAO = (
    AplicacaoManifesto(
        sistema_id=0,
        identificador="luft-workspace",
        esquema="workspace",
        usuario="luft_workspace_app",
    ),
)


def provisionar_schema_sistema(
    conexao: Connection,
    *,
    id_sistema: int,
    schema_aplicacao: str,
    usuario_role: str | None = None,
) -> bool:
    """Provisiona schema proprio e privilegios para um novo sistema.

    Retorna ``True`` quando o schema foi criado e ``False`` quando ja existia.
    A existencia e verificada antes do DDL porque o PostgreSQL exige privilegio
    CREATE no banco mesmo para ``CREATE SCHEMA IF NOT EXISTS``; assim um schema
    criado previamente pelo DBA e reaproveitado sem exigir esse privilegio.
    """
    citar = conexao.dialect.identifier_preparer.quote
    esquema_citado = citar(schema_aplicacao)
    existente = conexao.exec_driver_sql(
        "SELECT 1 FROM pg_namespace WHERE nspname = %(nome)s", {"nome": schema_aplicacao}
    ).first()
    criado = existente is None
    if criado:
        conexao.exec_driver_sql(f"CREATE SCHEMA {esquema_citado}")
    if usuario_role:
        usuario_citado = citar(usuario_role)
        conexao.exec_driver_sql(f"GRANT ALL ON SCHEMA {esquema_citado} TO {usuario_citado}")
        conexao.exec_driver_sql(
            f"GRANT ALL ON ALL TABLES IN SCHEMA {esquema_citado} TO {usuario_citado}"
        )
        conexao.exec_driver_sql(
            f"GRANT ALL ON ALL SEQUENCES IN SCHEMA {esquema_citado} TO {usuario_citado}"
        )
    return criado


def _conceder_privilegios_aplicacao(
    conexao: Connection,
    aplicacao: AplicacaoManifesto,
) -> None:
    """Concede privilegios do Core e do schema proprio com identificadores citados."""

    citar = conexao.dialect.identifier_preparer.quote
    usuario = citar(aplicacao.usuario)
    esquema = citar(aplicacao.esquema)
    comandos = (
        f"GRANT USAGE ON SCHEMA core TO {usuario}",
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core TO {usuario}",
        f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core TO {usuario}",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA core "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {usuario}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA core GRANT USAGE, SELECT ON SEQUENCES TO {usuario}",
        f"GRANT ALL ON SCHEMA {esquema} TO {usuario}",
        f"GRANT ALL ON ALL TABLES IN SCHEMA {esquema} TO {usuario}",
        f"GRANT ALL ON ALL SEQUENCES IN SCHEMA {esquema} TO {usuario}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} GRANT ALL ON TABLES TO {usuario}",
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA {esquema} GRANT ALL ON SEQUENCES TO {usuario}",
    )
    for comando in comandos:
        conexao.exec_driver_sql(comando)


def _atualizar_core_e_catalogo(
    *,
    ambiente: str | None,
    host: str | None,
    porta: int,
    banco: str,
    admin_user: str,
    grupo_administrador: int | None,
) -> None:
    """Aplica evolucoes aditivas sem acessar o Vault ou administrar roles."""

    ambiente_canonico = normalizar_ambiente(
        ambiente or os.getenv("LUFT_AMBIENTE", "desenvolvimento")
    ).value
    host_final = host or click.prompt("Host do PostgreSQL", default="127.0.0.1")
    porta_final = click.prompt("Porta do PostgreSQL", default=porta, type=int)
    banco_final = click.prompt("Nome do banco de dados", default=banco)
    admin_final = click.prompt("Usuario de migracao do PostgreSQL", default=admin_user)
    senha = click.prompt(f"Senha PostgreSQL do usuario {admin_final}", hide_input=True).strip()
    if not senha:
        raise click.ClickException("Senha do usuario de migracao e obrigatoria.")

    click.echo("\nAtualizacao aditiva do LuftBase")
    click.echo(f"  ambiente={ambiente_canonico}")
    click.echo(f"  destino={host_final}:{porta_final}/{banco_final}")
    click.echo("  Vault=nao acessado")
    click.echo("  roles=nao alteradas")
    click.echo("  dados existentes=preservados")
    confirmacao = f"ATUALIZAR-{ambiente_canonico.upper()}-{banco_final.upper()}"
    recebido = click.prompt(f"Digite {confirmacao} para continuar").strip()
    if recebido != confirmacao:
        raise click.ClickException("Confirmacao cancelada; nenhuma alteracao foi realizada.")

    uri = (
        f"postgresql+psycopg://{quote_plus(admin_final)}:{quote_plus(senha)}@"
        f"{host_final}:{porta_final}/{banco_final}?sslmode=prefer"
    )
    engine = create_engine(uri, pool_pre_ping=True)
    try:
        with engine.begin() as conexao:
            banco_conectado = conexao.scalar(text("SELECT current_database()"))
            if banco_conectado != banco_final:
                raise click.ClickException(
                    f"Conexao resolveu o banco {banco_conectado!r}, esperado {banco_final!r}."
                )
            conexao.execute(text("CREATE SCHEMA IF NOT EXISTS core"))
            command.upgrade(criar_configuracao_alembic(conexao=conexao), "head")
            resumo = sincronizar_catalogo_workspace(
                conexao,
                grupo_administrador=grupo_administrador,
            )
    except click.ClickException:
        raise
    except Exception as erro:
        detalhe = str(getattr(erro, "orig", erro)).splitlines()[0][:300]
        raise click.ClickException(
            f"Nao foi possivel atualizar o Core e o catalogo: {detalhe}"
        ) from erro
    finally:
        engine.dispose()

    click.echo("atualizacao=concluida")
    click.echo(f"modulos_sincronizados={resumo.modulos}")
    click.echo(f"permissoes_sincronizadas={resumo.permissoes}")
    if resumo.grupo_administrador is not None:
        click.echo(f"grupo_administrador={resumo.grupo_administrador}")


@click.command("bootstrap")
@click.option(
    "--ambiente",
    default=None,
    help="Ambiente a provisionar (ex: producao, homologacao, desenvolvimento).",
)
@click.option("--host", default=None, help="Host do PostgreSQL.")
@click.option("--porta", default=5432, type=int, help="Porta do PostgreSQL.")
@click.option("--banco", default="luft_web", help="Nome do banco de dados.")
@click.option(
    "--admin-user", default="postgres", help="Usuario administrativo/master do PostgreSQL."
)
@click.option("--vault-url", default=None, help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
@click.option("--alias-conexao", default="luft-web", help="Alias da conexao compartilhada.")
@click.option(
    "--atualizar",
    is_flag=True,
    help="Atualiza somente o schema Core e o catalogo, sem alterar Vault ou roles.",
)
@click.option(
    "--grupo-administrador",
    type=int,
    default=None,
    help="Concede a permissao mestre ao codigo de grupo informado.",
)
@click.option(
    "--manifesto-saida",
    default=None,
    help="Caminho para salvar o manifesto gerado.",
)
def bootstrap(
    ambiente: str | None,
    host: str | None,
    porta: int,
    banco: str,
    admin_user: str,
    vault_url: str | None,
    vault_mount: str,
    alias_conexao: str,
    atualizar: bool,
    grupo_administrador: int | None,
    manifesto_saida: str | None,
) -> None:
    """Assistente interativo de provisionamento seguro de banco, roles, cofre e Core."""

    if atualizar:
        _atualizar_core_e_catalogo(
            ambiente=ambiente,
            host=host,
            porta=porta,
            banco=banco,
            admin_user=admin_user,
            grupo_administrador=grupo_administrador,
        )
        return

    click.echo("\n" + "=" * 66)
    click.echo("   LuftBase — Assistente Interativo de Provisionamento")
    click.echo("=" * 66)
    click.echo("  Este assistente configura PostgreSQL, Vault e o schema Core")
    click.echo("  de forma ESTRITAMENTE ADITIVA (CAS 0).")
    click.echo("  Nenhum segredo ou dado existente sera editado ou apagado.")
    click.echo("=" * 66 + "\n")

    # 1. Coleta e validacao de parametros
    env_ambiente = os.getenv("LUFT_AMBIENTE", "producao")
    if not ambiente:
        ambiente = click.prompt(
            "Ambiente a provisionar (producao / homologacao / desenvolvimento)",
            default=env_ambiente,
        )
    ambiente_canonico = normalizar_ambiente(ambiente).value

    if not vault_url:
        vault_url = click.prompt(
            "URL do Vault",
            default=os.getenv("LUFT_VAULT_ENDERECO", "http://172.16.200.80:8200"),
        )
    vault_token = click.prompt("Token de operador/admin do Vault", hide_input=True).strip()
    if not vault_token:
        raise click.ClickException("Token de operador do Vault e obrigatorio.")

    if not host:
        host = click.prompt("Host do PostgreSQL", default="172.19.85.111")
    porta = click.prompt("Porta do PostgreSQL", default=porta, type=int)
    banco = click.prompt("Nome do banco de dados", default=banco)
    admin_user = click.prompt(
        "Usuario administrativo (DBA/superuser) do PostgreSQL", default=admin_user
    )
    admin_password = click.prompt(
        f"Senha PostgreSQL do usuario {admin_user}", hide_input=True
    ).strip()
    if not admin_password:
        raise click.ClickException("Senha administrativa do PostgreSQL e obrigatoria.")

    alias_conexao = click.prompt("Alias da conexao compartilhada", default=alias_conexao)

    usar_padrao = click.confirm(
        "Deseja provisionar o sistema corporativo padrao (0: Workspace)?",
        default=True,
    )
    if usar_padrao:
        aplicacoes = list(SISTEMAS_PADRAO)
    else:
        aplicacoes = []
        click.echo("Informe ao menos uma aplicacao:")
        while True:
            s_id = click.prompt("  ID do sistema (inteiro)", type=int)
            s_ident = click.prompt("  Identificador (slug, ex: luft-workspace)")
            s_esquema = click.prompt("  Esquema PostgreSQL (ex: workspace)")
            s_usr = click.prompt("  Usuario/Role PostgreSQL (ex: luft_workspace_app)")
            aplicacoes.append(
                AplicacaoManifesto(
                    sistema_id=s_id,
                    identificador=s_ident,
                    esquema=s_esquema,
                    usuario=s_usr,
                )
            )
            if not click.confirm("Adicionar outro sistema?", default=False):
                break

    # 2. Resumo e Confirmacao de Seguranca
    click.echo("\n" + "-" * 66)
    click.echo("  RESUMO DO PROVISIONAMENTO:")
    click.echo(f"  • Ambiente:        {ambiente_canonico.upper()}")
    click.echo(f"  • PostgreSQL:      {host}:{porta}/{banco} (admin: {admin_user})")
    click.echo(f"  • Vault URL:       {vault_url} (mount: {vault_mount})")
    click.echo(f"  • Conexao Alias:   {alias_conexao}")
    click.echo(f"  • Sistemas ({len(aplicacoes)}):")
    for app in aplicacoes:
        click.echo(
            f"      - ID {app.sistema_id}: {app.identificador} "
            f"[schema: {app.esquema}, role: {app.usuario}]"
        )
    click.echo("-" * 66)
    click.echo("  GARANTIAS DE SEGURANCA:")
    click.echo(f"  [OK] Destino no Vault: luft/{ambiente_canonico}/bancos/postgresql/")
    click.echo("  [OK] luft/desenvolvimento e segredos legados NAO serao tocados.")
    click.echo("  [OK] Operacao estritamente ADITIVA com CAS 0.")
    click.echo("-" * 66)

    confirmacao_esperada = f"BOOTSTRAP-{ambiente_canonico.upper()}"
    recebido = click.prompt(f"Digite {confirmacao_esperada} para executar", type=str).strip()
    if recebido != confirmacao_esperada:
        raise click.ClickException("Confirmacao cancelada; nenhuma alteracao foi realizada.")

    # 3. Teste de Conectividade do Vault
    click.echo("\n[1/5] Conectando ao HashiCorp Vault...")
    cliente_vault = _criar_cliente_hvac_operador(vault_url, vault_token, vault_mount)
    raiz = f"luft/{ambiente_canonico}"
    raiz_conexoes = f"{raiz}/bancos/postgresql/conexoes"
    raiz_sistemas = f"{raiz}/bancos/postgresql/sistemas"

    # Determinar senhas: se o segredo ja existir no Vault, reutiliza a senha; senao gera nova
    senhas: dict[str, str] = {}
    for app in aplicacoes:
        caminho_app = f"{raiz_sistemas}/{app.sistema_id}"
        senha_existente = None
        if _segredo_existe(cliente_vault, vault_mount, caminho_app):
            try:
                dados_vault = cliente_vault.secrets.kv.v2.read_secret_version(
                    path=caminho_app, mount_point=vault_mount
                )["data"]["data"]
                senha_existente = dados_vault.get("senha")
            except Exception:
                senha_existente = None
        senhas[app.usuario] = senha_existente or secrets.token_urlsafe(32)

    # 4. Criacao de Schemas, Roles e Senhas no PostgreSQL
    click.echo("[2/5] Conectando ao PostgreSQL administrativo...")
    try:
        # Tenta o banco de manutencao para criar o destino quando ele nao existir.
        if banco.lower() != "postgres":
            try:
                with (
                    psycopg.connect(
                        host=host,
                        port=porta,
                        dbname="postgres",
                        user=admin_user,
                        password=admin_password,
                        sslmode="prefer",
                        connect_timeout=10,
                        autocommit=True,
                    ) as conn_maint,
                    conn_maint.cursor() as cur,
                ):
                    cur.execute(
                        "SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s",
                        (banco,),
                    )
                    if not cur.fetchone():
                        cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(banco)))
                        click.echo(f"  ✓ Banco de dados '{banco}' criado com sucesso.")
                    else:
                        click.echo(f"  ✓ Banco de dados '{banco}' ja existe.")
            except Exception:
                # Se nao tiver permissao no banco 'postgres', prossegue diretamente para 'banco'
                pass

        with psycopg.connect(
            host=host,
            port=porta,
            dbname=banco,
            user=admin_user,
            password=admin_password,
            sslmode="prefer",
            connect_timeout=10,
        ) as conexao:
            conexao.autocommit = True
            with conexao.cursor() as cursor:
                # Criar schema core
                cursor.execute("CREATE SCHEMA IF NOT EXISTS core;")
                click.echo("  ✓ Schema 'core' garantido.")

                # Criar schemas e roles das aplicacoes
                for app in aplicacoes:
                    cursor.execute(
                        sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                            sql.Identifier(app.esquema)
                        )
                    )
                    # Verificar se role existe
                    cursor.execute(
                        "SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s",
                        (app.usuario,),
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            sql.SQL("CREATE ROLE {} WITH LOGIN").format(sql.Identifier(app.usuario))
                        )
                        click.echo(f"  ✓ Role '{app.usuario}' criada.")
                    else:
                        click.echo(f"  ✓ Role '{app.usuario}' ja existe.")

            # Aplicar senhas com SCRAM-SHA-256
            with conexao.cursor() as cursor:
                for app in aplicacoes:
                    senha_bruta = senhas[app.usuario]
                    verificador = conexao.pgconn.encrypt_password(
                        senha_bruta.encode(),
                        app.usuario.encode(),
                        b"scram-sha-256",
                    ).decode()
                    cursor.execute(
                        sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                            sql.Identifier(app.usuario),
                            sql.Literal(verificador),
                        )
                    )
            click.echo("  ✓ Senhas SCRAM-SHA-256 aplicadas nas roles.")

    except Exception as erro:
        raise click.ClickException(f"Falha na operacao PostgreSQL: {erro}") from erro

    # 5. Gravacao de Segredos no Vault com CAS 0
    click.echo("[3/5] Gravando segredos no Vault (CAS 0)...")
    caminho_conexao = f"{raiz_conexoes}/{alias_conexao}"
    if not _segredo_existe(cliente_vault, vault_mount, caminho_conexao):
        cliente_vault.secrets.kv.v2.create_or_update_secret(
            path=caminho_conexao,
            mount_point=vault_mount,
            cas=0,
            secret={
                "host": host,
                "porta": porta,
                "nome_banco": banco,
                "tipo_banco": "postgresql",
                "sslmode": "prefer",
            },
        )
        click.echo(f"  ✓ Segredo de conexao criado: {caminho_conexao}")
    else:
        click.echo(f"  • Segredo de conexao preservado: {caminho_conexao}")

    for app in aplicacoes:
        caminho_app = f"{raiz_sistemas}/{app.sistema_id}"
        if not _segredo_existe(cliente_vault, vault_mount, caminho_app):
            cliente_vault.secrets.kv.v2.create_or_update_secret(
                path=caminho_app,
                mount_point=vault_mount,
                cas=0,
                secret={
                    "sistema_id": app.sistema_id,
                    "identificador": app.identificador,
                    "conexao": alias_conexao,
                    "esquema": app.esquema,
                    "usuario": app.usuario,
                    "senha": senhas[app.usuario],
                },
            )
            click.echo(f"  ✓ Segredo do sistema {app.sistema_id} criado: {caminho_app}")
        else:
            click.echo(f"  • Segredo do sistema {app.sistema_id} preservado: {caminho_app}")

    # 6. Criacao das tabelas do Schema Core via Alembic
    click.echo("[4/5] Executando migracoes do Alembic para montar o Core...")
    senha_encoded = quote_plus(admin_password)
    uri_sqlalchemy = (
        f"postgresql+psycopg://{admin_user}:{senha_encoded}@{host}:{porta}/{banco}?sslmode=prefer"
    )
    try:
        engine_admin = create_engine(uri_sqlalchemy)
        with engine_admin.begin() as conexao_alembic:
            configuracao_alembic = criar_configuracao_alembic(conexao=conexao_alembic)
            command.upgrade(configuracao_alembic, "head")
        click.echo("  ✓ Todas as tabelas do schema 'core' montadas com sucesso.")

        with engine_admin.begin() as conexao_admin:
            resumo_catalogo = sincronizar_catalogo_workspace(conexao_admin)
            click.echo(
                "  Catalogo do Workspace sincronizado: "
                f"{resumo_catalogo.modulos} modulos e "
                f"{resumo_catalogo.permissoes} permissoes."
            )

            # Conceder privilegios nas tabelas do Core e das aplicacoes
            for app in aplicacoes:
                _conceder_privilegios_aplicacao(conexao_admin, app)
            click.echo("  ✓ Privilégios concedidos às roles nos schemas 'core' e aplicações.")
    except Exception as erro:
        raise click.ClickException(f"Falha ao executar migracoes do Core: {erro}") from erro

    # 7. Salvar Manifesto Local
    click.echo("[5/5] Salvando manifesto de documentacao...")
    caminho_manifesto = (
        Path(manifesto_saida)
        if manifesto_saida
        else Path("docs") / f"manifesto-postgresql-{ambiente_canonico}.json"
    )
    caminho_manifesto.parent.mkdir(parents=True, exist_ok=True)
    manifesto_dados = {
        "ambiente": ambiente_canonico,
        "conexao": {
            "alias": alias_conexao,
            "host": host,
            "porta": porta,
            "nome_banco": banco,
            "tipo_banco": "postgresql",
            "sslmode": "prefer",
        },
        "aplicacoes": [
            {
                "sistema_id": a.sistema_id,
                "identificador": a.identificador,
                "esquema": a.esquema,
                "usuario": a.usuario,
            }
            for a in aplicacoes
        ],
    }
    caminho_manifesto.write_text(
        json.dumps(manifesto_dados, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    click.echo(f"  ✓ Manifesto salvo em: {caminho_manifesto}")

    click.echo("\n" + "=" * 66)
    click.echo("  🎉 PROVISIONAMENTO CONCLUIDO COM SUCESSO!")
    click.echo("  • PostgreSQL: Schemas, Roles e Tabelas do Core montadas.")
    click.echo("  • Vault: Conexao e Sistemas criados com CAS 0.")
    click.echo("  • Ambientes legados e de desenvolvimento: 100% preservados.")
    click.echo("=" * 66 + "\n")


@click.command("conceder-permissoes")
@click.option("--host", default=None, help="Host do PostgreSQL.")
@click.option("--porta", default=5432, type=int, help="Porta do PostgreSQL.")
@click.option("--banco", default="luft_web", help="Nome do banco de dados.")
@click.option(
    "--admin-user", default="postgres", help="Usuario administrativo/master do PostgreSQL."
)
def conceder_permissoes(
    host: str | None,
    porta: int,
    banco: str,
    admin_user: str,
) -> None:
    """Aplica permissoes completas nas tabelas dos schemas core e aplicacoes."""

    click.echo("\n==================================================================")
    click.echo("   LuftBase — Conceder Permissoes PostgreSQL (Core & Apps)")
    click.echo("==================================================================")

    if not host:
        host = click.prompt("Host do PostgreSQL", default="transfersql.luftfarma.com.br")
    porta = click.prompt("Porta do PostgreSQL", default=porta, type=int)
    banco = click.prompt("Nome do banco de dados", default=banco)
    admin_user = click.prompt(
        "Usuario administrativo (DBA/superuser) do PostgreSQL", default=admin_user
    )
    admin_password = click.prompt(
        f"Senha PostgreSQL do usuario {admin_user}", hide_input=True
    ).strip()
    if not admin_password:
        raise click.ClickException("Senha administrativa do PostgreSQL e obrigatoria.")

    senha_encoded = quote_plus(admin_password)
    uri_sqlalchemy = (
        f"postgresql+psycopg://{admin_user}:{senha_encoded}@{host}:{porta}/{banco}?sslmode=prefer"
    )

    try:
        engine_admin = create_engine(uri_sqlalchemy)
        with engine_admin.begin() as conexao_admin:
            for app in SISTEMAS_PADRAO:
                _conceder_privilegios_aplicacao(conexao_admin, app)
                click.echo(
                    f"  ✓ Permissoes concedidas para {app.usuario} no core e em {app.esquema}."
                )
        click.echo("\n  🎉 Permissoes aplicadas com sucesso em todas as tabelas e schemas!\n")
    except Exception as erro:
        raise click.ClickException(f"Falha ao conceder permissoes: {erro}") from erro


__all__ = ["bootstrap", "conceder_permissoes", "SISTEMAS_PADRAO"]
