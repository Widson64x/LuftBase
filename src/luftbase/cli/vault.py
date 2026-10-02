"""Comandos de inspecao, auditoria e provisionamento do Vault."""

from __future__ import annotations

import getpass
import secrets
from typing import Any

import click

from luftbase.cli.manifesto import ManifestoProvisionamento
from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.credenciais import Segredo, TipoBanco
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais
from luftbase.nucleo.excecoes import ErroConfiguracao, ErroCredencial, SegredoNaoEncontrado


@click.group("vault")
def vault() -> None:
    """Inspecao sanitizada de caminhos e segredos do Vault."""


@vault.command("caminhos")
def vault_caminhos() -> None:
    """Mostra os caminhos canonicos derivados para o ambiente atual."""

    try:
        configuracao = ConfiguracaoLuftBase.de_ambiente()
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
        namespace=configuracao.cofre.namespace,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )

    click.echo(f"ambiente={configuracao.aplicacao.ambiente.value}")
    click.echo(f"sistema_id={configuracao.aplicacao.sistema_id}")
    click.echo(f"sqlserver={caminhos.sqlserver_diretorio}")
    click.echo(f"sqlserver_legado={caminhos.sqlserver_legado}")
    click.echo(f"postgresql={caminhos.postgresql}")
    click.echo(f"sessoes_redis={caminhos.sessoes_redis}")
    click.echo(f"email={caminhos.email}")


@vault.command("verificar")
@click.option("--conectar", is_flag=True, help="Testa conectividade e estrutura dos segredos.")
def vault_verificar(conectar: bool) -> None:
    """Verifica configuracao dos segredos sem exibir senhas ou tokens."""

    try:
        configuracao = ConfiguracaoLuftBase.de_ambiente()
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
        namespace=configuracao.cofre.namespace,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )

    click.echo(f"vault_endereco={configuracao.cofre.endereco}")
    click.echo(f"vault_namespace={configuracao.cofre.namespace}")
    click.echo(f"caminho_sqlserver={caminhos.sqlserver_diretorio}")
    click.echo(f"caminho_sqlserver_legado={caminhos.sqlserver_legado}")
    click.echo(f"caminho_postgresql={caminhos.postgresql}")
    click.echo(f"caminho_sessoes_redis={caminhos.sessoes_redis}")
    click.echo(f"caminho_email={caminhos.email}")

    if not conectar:
        click.echo("validacao_estrutural=concluida (use --conectar para testar acesso)")
        return

    token_protegido = configuracao.cofre.token_protegido
    token_acesso = configuracao.cofre.token_acesso
    if not token_protegido or not token_acesso:
        raise click.ClickException("Tokens do Vault nao estao configurados no ambiente.")

    try:
        token_vault = DesprotetorFernet(token_acesso).revelar(token_protegido)
        provedor = ClienteVaultHvac(configuracao.cofre.endereco, Segredo(token_vault))
        provedor.validar_acesso()
        carregador = CarregadorCredenciais(provedor)
        try:
            carregador.carregar_banco(caminhos.sqlserver_diretorio, TipoBanco.SQLSERVER)
            diretorio_status = "ok"
        except SegredoNaoEncontrado:
            carregador.carregar_banco(caminhos.sqlserver_legado, TipoBanco.SQLSERVER)
            diretorio_status = "caminho antigo em uso (migre para o caminho novo)"
        if caminhos.postgresql_conexoes:
            carregador.carregar_banco_composto(
                caminhos.postgresql,
                caminhos.postgresql_conexoes,
                TipoBanco.POSTGRESQL,
            )
        else:
            carregador.carregar_banco(
                caminhos.postgresql,
                TipoBanco.POSTGRESQL,
                exigir_esquema=True,
            )
        try:
            carregador.carregar_redis(caminhos.sessoes_redis)
            redis_status = "ok"
        except SegredoNaoEncontrado:
            redis_status = "ausente (fallback para sessoes corporativas PostgreSQL)"
        try:
            carregador.carregar_email(caminhos.email)
            email_status = "ok"
        except SegredoNaoEncontrado:
            email_status = "ausente (envio de e-mail indisponivel)"
    except (ErroConfiguracao, ErroCredencial, SegredoNaoEncontrado) as erro:
        raise click.ClickException(f"Falha ao validar segredos do Vault: {erro}") from erro
    except Exception as erro:
        raise click.ClickException(f"Falha ao comunicar com o Vault: {erro}") from erro

    click.echo("conexao=ok")
    click.echo("segredos=validos")
    click.echo(f"sqlserver_status={diretorio_status}")
    click.echo(f"sessoes_redis_status={redis_status}")
    click.echo(f"email_status={email_status}")


# ==============================================================================
# SUBCOMANDOS DE PROVISIONAMENTO POSTGRESQL + VAULT
# ==============================================================================


@vault.group("postgresql")
def vault_postgresql() -> None:
    """Auditoria e provisionamento oficial de PostgreSQL e Vault."""


def _solicitar_segredo(rotulo: str) -> str:
    valor = getpass.getpass(f"{rotulo}: ")
    if not valor:
        raise click.ClickException(f"{rotulo} nao pode ficar vazio.")
    return valor


def _criar_cliente_hvac_operador(url: str, token: str, mount: str) -> Any:
    import hvac
    from hvac import exceptions as vault_exceptions

    cliente = hvac.Client(url=url, token=token)
    if not cliente.is_authenticated():
        raise click.ClickException("O token informado nao foi autenticado pelo Vault.")
    try:
        montagens = cliente.sys.list_mounted_secrets_engines()["data"]  # type: ignore[no-untyped-call]
    except vault_exceptions.Forbidden:
        # Policies operacionais enxutas normalmente nao permitem listar todos os
        # mounts. A validacao efetiva do KV v2 ocorrera na primeira operacao.
        return cliente
    except Exception as erro:
        raise click.ClickException(f"Falha ao verificar engines no Vault: {erro}") from erro

    configuracao = montagens.get(f"{mount}/")
    if configuracao is None:
        raise click.ClickException(f"O mount {mount!r} nao existe no Vault.")
    if configuracao.get("type") != "kv":
        raise click.ClickException(f"O mount {mount!r} nao e do tipo KV.")
    if configuracao.get("options", {}).get("version") != "2":
        raise click.ClickException(f"O mount {mount!r} nao usa KV v2.")
    return cliente


def _segredo_existe(cliente: Any, mount: str, caminho: str) -> bool:
    from hvac import exceptions as vault_exceptions

    try:
        cliente.secrets.kv.v2.read_secret_metadata(path=caminho, mount_point=mount)
    except vault_exceptions.InvalidPath:
        return False
    except Exception:
        # Se leitura de metadata for proibida por policy, tenta ler versao
        try:
            cliente.secrets.kv.v2.read_secret_version(path=caminho, mount_point=mount)
        except vault_exceptions.InvalidPath:
            return False
    return True


@vault_postgresql.command("auditar")
@click.option(
    "--manifesto",
    "caminho_manifesto",
    required=True,
    type=click.Path(exists=True),
    help="Caminho do manifesto nao sensivel.",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
@click.option("--postgres-admin", default="admin", help="Usuario administrativo do PostgreSQL.")
def postgresql_auditar(
    caminho_manifesto: str,
    vault_url: str,
    vault_mount: str,
    postgres_admin: str,
) -> None:
    """Audita PostgreSQL e Vault sem realizar alteracoes."""

    import psycopg

    manifesto = ManifestoProvisionamento.de_arquivo(caminho_manifesto)
    token_operador = _solicitar_segredo("Token de operador do Vault")
    senha_admin = _solicitar_segredo(f"Senha PostgreSQL do usuario {postgres_admin}")

    cliente_vault = _criar_cliente_hvac_operador(vault_url, token_operador, vault_mount)
    raiz = f"luft/{manifesto.ambiente}"

    click.echo("\nVault (checagem de caminhos):")
    caminho_conexao = f"{raiz}/bancos/postgresql/conexoes/{manifesto.conexao.alias}"
    existe_con = _segredo_existe(cliente_vault, vault_mount, caminho_conexao)
    status_con = "EXISTE" if existe_con else "AUSENTE"
    click.echo(f"  {status_con:<7}  {caminho_conexao}")

    for app in manifesto.aplicacoes:
        caminho_app = f"{raiz}/bancos/postgresql/sistemas/{app.sistema_id}"
        existe_app = _segredo_existe(cliente_vault, vault_mount, caminho_app)
        status_app = "EXISTE" if existe_app else "AUSENTE"
        click.echo(f"  {status_app:<7}  {caminho_app}")

    click.echo("\nPostgreSQL (checagem de roles):")
    try:
        with psycopg.connect(
            host=manifesto.conexao.host,
            port=manifesto.conexao.porta,
            dbname=manifesto.conexao.nome_banco,
            user=postgres_admin,
            password=senha_admin,
            sslmode=manifesto.conexao.sslmode,
            connect_timeout=10,
        ) as conexao:
            usuarios = [app.usuario for app in manifesto.aplicacoes]
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rolname, rolcanlogin, rolpassword IS NOT NULL AS senha_configurada
                    FROM pg_catalog.pg_authid
                    WHERE rolname = ANY (%s)
                    ORDER BY rolname
                    """,
                    (usuarios,),
                )
                encontrados = {linha[0]: linha for linha in cursor.fetchall()}

                cursor.execute(
                    """
                    SELECT usename, count(*)
                    FROM pg_catalog.pg_stat_activity
                    WHERE datname = %s AND usename = ANY (%s)
                    GROUP BY usename
                    """,
                    (manifesto.conexao.nome_banco, usuarios),
                )
                ativas: dict[str, int] = dict(cursor.fetchall())

            for app in manifesto.aplicacoes:
                linha = encontrados.get(app.usuario)
                if linha is None:
                    click.echo(f"  AUSENTE  {app.usuario}")
                else:
                    _, permite_login, possui_senha = linha
                    click.echo(
                        f"  OK       {app.usuario}: login={permite_login}, "
                        f"senha={possui_senha}, conexoes={ativas.get(app.usuario, 0)}"
                    )
    except Exception as erro:
        raise click.ClickException(f"Falha ao consultar PostgreSQL: {erro}") from erro

    click.echo("\nAuditoria concluida sem alteracoes.")


@vault_postgresql.command("provisionar")
@click.option(
    "--manifesto",
    "caminho_manifesto",
    required=True,
    type=click.Path(exists=True),
    help="Caminho do manifesto nao sensivel.",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
@click.option("--postgres-admin", default="admin", help="Usuario administrativo do PostgreSQL.")
def postgresql_provisionar(
    caminho_manifesto: str,
    vault_url: str,
    vault_mount: str,
    postgres_admin: str,
) -> None:
    """Cria novos segredos com CAS 0 e define senhas SCRAM-SHA-256 no PostgreSQL."""

    import psycopg
    from psycopg import sql

    manifesto = ManifestoProvisionamento.de_arquivo(caminho_manifesto)
    confirmacao_esperada = f"PROVISIONAR-{manifesto.conexao.alias.upper()}"
    click.echo(
        "Esta operacao criara segredos no Vault com CAS 0 e configurara senhas no PostgreSQL."
    )
    recebido = click.prompt(f"Digite {confirmacao_esperada} para confirmar", type=str).strip()
    if recebido != confirmacao_esperada:
        raise click.ClickException("Confirmacao recusada; nenhuma alteracao realizada.")

    token_operador = _solicitar_segredo("Token de operador do Vault")
    senha_admin = _solicitar_segredo(f"Senha PostgreSQL do usuario {postgres_admin}")

    cliente_vault = _criar_cliente_hvac_operador(vault_url, token_operador, vault_mount)
    raiz = f"luft/{manifesto.ambiente}"
    raiz_conexoes = f"{raiz}/bancos/postgresql/conexoes"

    # 1. Validar que nenhum segredo ja existe no Vault
    caminhos = [f"{raiz_conexoes}/{manifesto.conexao.alias}"]
    for app in manifesto.aplicacoes:
        caminhos.append(f"{raiz}/bancos/postgresql/sistemas/{app.sistema_id}")

    existentes = [c for c in caminhos if _segredo_existe(cliente_vault, vault_mount, c)]
    if existentes:
        raise click.ClickException(
            "O provisionamento nao sobrescreve segredos existentes: " + ", ".join(existentes)
        )

    # 2. Validar roles no PostgreSQL
    usuarios = [app.usuario for app in manifesto.aplicacoes]
    try:
        with psycopg.connect(
            host=manifesto.conexao.host,
            port=manifesto.conexao.porta,
            dbname=manifesto.conexao.nome_banco,
            user=postgres_admin,
            password=senha_admin,
            sslmode=manifesto.conexao.sslmode,
            connect_timeout=10,
        ) as conexao:
            with conexao.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT rolname, rolcanlogin, rolpassword IS NOT NULL
                    FROM pg_catalog.pg_authid
                    WHERE rolname = ANY (%s)
                    """,
                    (usuarios,),
                )
                roles = {nome: (login, senha) for nome, login, senha in cursor.fetchall()}
                cursor.execute(
                    """
                    SELECT DISTINCT usename
                    FROM pg_catalog.pg_stat_activity
                    WHERE datname = %s AND usename = ANY (%s) AND pid <> pg_backend_pid()
                    """,
                    (manifesto.conexao.nome_banco, usuarios),
                )
                ativas = {linha[0] for linha in cursor.fetchall()}

            ausentes = sorted(set(usuarios) - roles.keys())
            sem_login = sorted(nome for nome, st in roles.items() if not st[0])
            com_senha = sorted(nome for nome, st in roles.items() if st[1])
            if ausentes:
                raise click.ClickException(f"Roles ausentes no PostgreSQL: {', '.join(ausentes)}")
            if sem_login:
                raise click.ClickException(f"Roles sem LOGIN: {', '.join(sem_login)}")
            if com_senha:
                raise click.ClickException(
                    "Roles ja possuem senha e nao serao rotacionadas: " + ", ".join(com_senha)
                )
            if ativas:
                raise click.ClickException(
                    "Conexoes ativas das roles alvo: " + ", ".join(sorted(ativas))
                )

            # 3. Gerar senhas criptograficamente seguras
            senhas = {app.usuario: secrets.token_urlsafe(32) for app in manifesto.aplicacoes}

            # 4. Escrever segredos no Vault com CAS 0
            cliente_vault.secrets.kv.v2.create_or_update_secret(
                path=f"{raiz_conexoes}/{manifesto.conexao.alias}",
                mount_point=vault_mount,
                cas=0,
                secret={
                    "tipo_banco": manifesto.conexao.tipo_banco,
                    "host": manifesto.conexao.host,
                    "porta": str(manifesto.conexao.porta),
                    "nome_banco": manifesto.conexao.nome_banco,
                    "sslmode": manifesto.conexao.sslmode,
                },
            )
            for app in manifesto.aplicacoes:
                payload = {
                    "conexao": manifesto.conexao.alias,
                    "esquema": app.esquema,
                    "identificador": app.identificador,
                    "usuario": app.usuario,
                    "senha": senhas[app.usuario],
                    "sistema_id": app.sistema_id,
                }
                cliente_vault.secrets.kv.v2.create_or_update_secret(
                    path=f"{raiz}/bancos/postgresql/sistemas/{app.sistema_id}",
                    mount_point=vault_mount,
                    cas=0,
                    secret=payload,
                )

            click.echo("Segredos gravados no Vault com CAS 0.")

            # 5. Aplicar senhas no PostgreSQL com SCRAM-SHA-256
            try:
                with conexao.transaction(), conexao.cursor() as cursor:
                    for app in manifesto.aplicacoes:
                        senha = senhas[app.usuario]
                        verificador = conexao.pgconn.encrypt_password(
                            senha.encode(),
                            app.usuario.encode(),
                            b"scram-sha-256",
                        ).decode()
                        cursor.execute(
                            sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                                sql.Identifier(app.usuario),
                                sql.Literal(verificador),
                            )
                        )
            except Exception as erro:
                click.echo(
                    "FALHA ao aplicar senhas no PostgreSQL. Os segredos foram mantidos no Vault. "
                    "Use 'aplicar-senhas-do-vault' apos corrigir a causa.",
                    err=True,
                )
                raise click.ClickException(str(erro)) from erro

    except click.ClickException:
        raise
    except Exception as erro:
        raise click.ClickException(f"Falha durante o provisionamento: {erro}") from erro

    click.echo("Provisionamento concluido com sucesso sem expor valores secretos.")


@vault_postgresql.command("migrar-layout-sistemas")
@click.option(
    "--manifesto",
    "caminho_manifesto",
    required=True,
    type=click.Path(exists=True),
    help="Caminho do manifesto nao sensivel.",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
def postgresql_migrar_layout_sistemas(
    caminho_manifesto: str,
    vault_url: str,
    vault_mount: str,
) -> None:
    """Copia credenciais legadas para sistemas/{id} sem apagar ou revelar segredos."""

    manifesto = ManifestoProvisionamento.de_arquivo(caminho_manifesto)
    token_operador = _solicitar_segredo("Token de operador do Vault")
    cliente_vault = _criar_cliente_hvac_operador(vault_url, token_operador, vault_mount)
    raiz = f"luft/{manifesto.ambiente}"
    raiz_legada = f"{raiz}/bancos/postgresql"
    destino_conexao = f"{raiz_legada}/conexoes/{manifesto.conexao.alias}"

    if _segredo_existe(cliente_vault, vault_mount, destino_conexao):
        click.echo(f"  PULADO  {destino_conexao} (ja existe)")
    else:
        try:
            resposta = cliente_vault.secrets.kv.v2.read_secret_version(
                path=f"{raiz_legada}/conexoes/{manifesto.conexao.alias}",
                mount_point=vault_mount,
                raise_on_deleted_version=True,
            )
            cliente_vault.secrets.kv.v2.create_or_update_secret(
                path=destino_conexao,
                mount_point=vault_mount,
                cas=0,
                secret=resposta["data"]["data"],
            )
            click.echo(f"  CRIADO  {destino_conexao} (CAS 0)")
        except Exception as erro:
            raise click.ClickException("Falha ao migrar a conexao compartilhada.") from erro

    for app in manifesto.aplicacoes:
        caminho_origem = f"{raiz_legada}/aplicacoes/{app.identificador}"
        caminho_destino = f"{raiz_legada}/sistemas/{app.sistema_id}"

        if _segredo_existe(cliente_vault, vault_mount, caminho_destino):
            click.echo(f"  PULADO  {caminho_destino} (ja existe)")
            continue

        try:
            resposta = cliente_vault.secrets.kv.v2.read_secret_version(
                path=caminho_origem,
                mount_point=vault_mount,
                raise_on_deleted_version=True,
            )
            dados_origem = dict(resposta["data"]["data"])
            dados_origem.update(
                {
                    "conexao": manifesto.conexao.alias,
                    "esquema": app.esquema,
                    "identificador": app.identificador,
                    "sistema_id": app.sistema_id,
                    "usuario": app.usuario,
                }
            )
            cliente_vault.secrets.kv.v2.create_or_update_secret(
                path=caminho_destino,
                mount_point=vault_mount,
                cas=0,
                secret=dados_origem,
            )
            click.echo(f"  CRIADO  {caminho_destino} (CAS 0 a partir de {app.identificador})")
        except Exception as erro:
            raise click.ClickException(f"Falha ao associar {app.identificador}: {erro}") from erro

    click.echo("Layout por sistema criado; nenhum segredo legado foi alterado ou removido.")


@vault_postgresql.command("aplicar-senhas-do-vault")
@click.option(
    "--manifesto",
    "caminho_manifesto",
    required=True,
    type=click.Path(exists=True),
    help="Caminho do manifesto nao sensivel.",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
@click.option("--postgres-admin", default="admin", help="Usuario administrativo do PostgreSQL.")
def postgresql_aplicar_senhas_do_vault(
    caminho_manifesto: str,
    vault_url: str,
    vault_mount: str,
    postgres_admin: str,
) -> None:
    """Recupera senhas gravadas no Vault e reaplica com SCRAM-SHA-256 no PostgreSQL."""

    import psycopg
    from psycopg import sql

    manifesto = ManifestoProvisionamento.de_arquivo(caminho_manifesto)
    token_operador = _solicitar_segredo("Token de operador do Vault")
    senha_admin = _solicitar_segredo(f"Senha PostgreSQL do usuario {postgres_admin}")

    cliente_vault = _criar_cliente_hvac_operador(vault_url, token_operador, vault_mount)
    raiz = f"luft/{manifesto.ambiente}"

    # Ler senhas do Vault
    senhas: dict[str, str] = {}
    for app in manifesto.aplicacoes:
        caminho_app = f"{raiz}/bancos/postgresql/sistemas/{app.sistema_id}"
        resposta = cliente_vault.secrets.kv.v2.read_secret_version(
            path=caminho_app,
            mount_point=vault_mount,
            raise_on_deleted_version=True,
        )
        dados = resposta["data"]["data"]
        senha = dados.get("senha")
        if not senha:
            raise click.ClickException(f"Senha ausente no segredo {caminho_app}")
        senhas[app.usuario] = senha

    # Aplicar no PostgreSQL
    with (
        psycopg.connect(
            host=manifesto.conexao.host,
            port=manifesto.conexao.porta,
            dbname=manifesto.conexao.nome_banco,
            user=postgres_admin,
            password=senha_admin,
            sslmode=manifesto.conexao.sslmode,
            connect_timeout=10,
        ) as conexao,
        conexao.transaction(),
        conexao.cursor() as cursor,
    ):
        for app in manifesto.aplicacoes:
            senha = senhas[app.usuario]
            verificador = conexao.pgconn.encrypt_password(
                senha.encode(),
                app.usuario.encode(),
                b"scram-sha-256",
            ).decode()
            cursor.execute(
                sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                    sql.Identifier(app.usuario),
                    sql.Literal(verificador),
                )
            )

    click.echo("Senhas reaplicadas no PostgreSQL com sucesso a partir do Vault.")


@vault_postgresql.command("remover-sistemas")
@click.option(
    "--ambiente", required=True, help="Ambiente (desenvolvimento, homologacao, producao)."
)
@click.option(
    "--sistema-id",
    "ids_sistema",
    multiple=True,
    type=int,
    help="Sistema a remover; repita a opcao para varios. Sem ela, remove todos da pasta.",
)
@click.option("--vault-url", default="http://172.16.200.80:8200", help="URL do Vault.")
@click.option("--vault-mount", default="secret", help="Mount point do Vault KV v2.")
@click.option("--namespace", default="luft", help="Namespace raiz dos segredos.")
def postgresql_remover_sistemas(
    ambiente: str,
    ids_sistema: tuple[int, ...],
    vault_url: str,
    vault_mount: str,
    namespace: str,
) -> None:
    """Apaga segredos `bancos/postgresql/sistemas/{id}` (todas as versoes), com confirmacao.

    Nao altera roles, schemas nem o core; conexoes compartilhadas sao preservadas.
    """

    from luftbase.configuracao.ambientes import normalizar_ambiente
    from luftbase.infraestrutura.cofre.provisionamento import (
        listar_segredos_sistemas,
        raiz_segredos_sistemas,
        remover_segredo_sistema,
    )

    try:
        ambiente_canonico = normalizar_ambiente(ambiente).value
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    token_operador = _solicitar_segredo("Token de operador do Vault")
    cliente = _criar_cliente_hvac_operador(vault_url, token_operador, vault_mount)
    raiz = raiz_segredos_sistemas(ambiente_canonico, namespace)
    existentes = listar_segredos_sistemas(cliente, vault_mount, ambiente_canonico, namespace)
    alvos = [str(i) for i in ids_sistema] if ids_sistema else existentes

    click.echo(f"pasta={raiz}")
    click.echo(f"existentes={', '.join(existentes) or '(nenhum)'}")
    ausentes = [alvo for alvo in alvos if alvo not in existentes]
    alvos = [alvo for alvo in alvos if alvo in existentes]
    if ausentes:
        click.echo(f"ignorados (nao existem)={', '.join(ausentes)}")
    if not alvos:
        click.echo("Nada a remover.")
        return

    for alvo in alvos:
        click.echo(f"  REMOVER {raiz}/{alvo}")
    confirmacao = f"REMOVER-{ambiente_canonico.upper()}"
    recebido = click.prompt(f"Digite {confirmacao} para apagar {len(alvos)} segredo(s)").strip()
    if recebido != confirmacao:
        raise click.ClickException("Confirmacao cancelada; nenhum segredo foi removido.")

    for alvo in alvos:
        try:
            remover_segredo_sistema(cliente, vault_mount, ambiente_canonico, alvo, namespace)
        except Exception as erro:
            raise click.ClickException(f"Falha ao remover {raiz}/{alvo}: {erro}") from erro
        click.echo(f"  REMOVIDO {raiz}/{alvo}")
    click.echo("Concluido. Roles, schemas e o core nao foram alterados.")
