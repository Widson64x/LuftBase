"""Comandos de scaffolding e geracao deterministica de aplicacoes LuftBase."""

from __future__ import annotations

from pathlib import Path

import click

from luftbase.cli.operador import (
    AMBIENTES_DA_CLI,
    VAULT_URL_PADRAO,
    abrir_sessao_operador,
    normalizar_ambiente_da_cli,
)
from luftbase.configuracao.identificadores import validar_identificador_tecnico
from luftbase.geracao.aplicacao import (
    PlanoProjeto,
    escrever_env,
    gerar_aplicacao,
    ler_env_referencia,
)
from luftbase.infraestrutura.cadastro_sistema import (
    GRUPO_TI_PADRAO,
    ErroCadastroSistema,
    cadastrar_sistema,
    exigir_core_atualizado,
)
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.persistencia.core.categorias_sistema import CODIGOS_CATEGORIA
from luftbase.web.configuracoes import validar_payload_novo_sistema


def _gerar_arquivos_deploy(
    identificador: str,
    nome: str,
    pacote: str,
    diretorio_deploy: Path,
    *,
    forcar: bool = False,
    porta: int = 8000,
) -> list[Path]:
    """Gera artefatos revisaveis de deploy Nginx e NSSM."""

    diretorio_deploy.mkdir(parents=True, exist_ok=True)
    arquivos: list[tuple[str, str]] = [
        (
            "nginx.conf",
            f"""# Configuracao de proxy reverso Nginx para {identificador}
# ATENCAO: Este arquivo e um artefato revisavel. Nao altere o servidor sem revisao previa.

upstream {pacote}_backend {{
    server 127.0.0.1:{porta};
    keepalive 32;
}}

server {{
    listen 80;
    server_name {identificador}.luft.interno;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Correlation-ID $request_id;

    location / {{
        proxy_pass http://{pacote}_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }}

    location ~ ^/_luftbase/.+/eventos$ {{
        proxy_pass http://{pacote}_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
        proxy_read_timeout 86400s;
    }}

    location /static/ {{
        proxy_pass http://{pacote}_backend;
        expires 7d;
        add_header Cache-Control "public, no-transform";
    }}
}}
""",
        ),
        (
            "nssm.ps1",
            f"""# Script de geracao de servico Windows via NSSM para {identificador}
# ATENCAO: Este script e um artefato revisavel.
# Execute manualmente com privilegios de Administrador.

$ServiceName = "{identificador}"
$NssmPath = "C:\\tools\\nssm\\nssm.exe"
$AppDirectory = "C:\\Projetos\\LUFT\\Python\\{identificador}"
$PythonExe = "$AppDirectory\\.venv\\Scripts\\python.exe"
# O Wsgi.py usa o servidor padrao do LuftBase (Waitress); host, porta e prefixo vem do .env.
$AppParameters = "Wsgi.py"

if (-not (Test-Path $NssmPath)) {{
    Write-Error "NSSM nao encontrado no caminho configurado: $NssmPath"
    exit 1
}}

Write-Host "Instalando servico $ServiceName..."
& $NssmPath install $ServiceName $PythonExe $AppParameters
& $NssmPath set $ServiceName AppDirectory $AppDirectory
& $NssmPath set $ServiceName AppStdout "$AppDirectory\\logs\\stdout.log"
& $NssmPath set $ServiceName AppStderr "$AppDirectory\\logs\\stderr.log"
& $NssmPath set $ServiceName AppRotateFiles 1
& $NssmPath set $ServiceName AppRotateOnline 1
& $NssmPath set $ServiceName AppRotateSeconds 86400
& $NssmPath set $ServiceName AppRotateBytes 10485760
& $NssmPath set $ServiceName Start SERVICE_AUTO_START

Write-Host "Servico $ServiceName instalado. Revise e inicie com: nssm start $ServiceName"
""",
        ),
        (
            "README.md",
            f"""# Artefatos de Implantacao — {nome}

Os arquivos neste diretorio sao artefatos revisaveis para implantacao:
- `nginx.conf`: configuracao de proxy reverso com suporte a Server-Sent Events (SSE) sem buffering;
- `nssm.ps1`: script PowerShell para criacao de servico Windows via NSSM.

## Revisao e execucao

1. Revise portas, dominios e caminhos absolutos antes de qualquer execucao.
2. Nunca execute scripts de deploy em producao sem validacao previa em homologacao.
3. Certifique-se de que as variaveis de ambiente e segredos do Vault estao configurados.
""",
        ),
    ]

    gerados: list[Path] = []
    for nome_arquivo, conteudo in arquivos:
        destino = diretorio_deploy / nome_arquivo
        if destino.exists() and not forcar:
            continue
        destino.write_text(conteudo, encoding="utf-8")
        gerados.append(destino)
    return gerados


def gerar_projeto(
    nome: str,
    *,
    destino: Path | str | None = None,
    schema: str | None = None,
    porta: int = 9000,
    sistema_id: int | None = None,
    ambiente: str = "desenvolvimento",
    forcar: bool = False,
) -> list[Path]:
    """Gera a arvore da aplicacao (ADR-017) e os artefatos revisaveis de deploy."""

    plano = PlanoProjeto.criar(nome, esquema=schema, porta=porta)
    raiz = Path(destino) if destino is not None else Path.cwd() / plano.pacote_dir
    gerados = gerar_aplicacao(plano, raiz, ambiente=ambiente, sistema_id=sistema_id, forcar=forcar)
    gerados.extend(
        _gerar_arquivos_deploy(
            plano.identificador,
            plano.nome,
            plano.pacote_dir,
            raiz / "deploy",
            forcar=True,
            porta=plano.porta,
        )
    )
    return sorted(gerados)


@click.group("projeto")
def projeto() -> None:
    """Gerenciamento e scaffolding de projetos LuftBase."""


@projeto.command("criar")
@click.argument("nome")
@click.option("--sistema-id", default=None, type=click.IntRange(min=0), help="ID ja cadastrado.")
@click.option(
    "--destino",
    default=None,
    type=click.Path(path_type=Path),
    help="Diretorio de destino (padrao: ./NOME).",
)
@click.option("--schema", default=None, help="Esquema particular da aplicacao no PostgreSQL.")
@click.option("--porta", default=9000, show_default=True, type=int, help="Porta HTTP local.")
@click.option(
    "--forcar",
    is_flag=True,
    help="Sobrescreve arquivos no destino se nao estiver vazio.",
)
def criar(
    nome: str,
    sistema_id: int | None,
    destino: Path | None,
    schema: str | None,
    porta: int,
    forcar: bool,
) -> None:
    """Gera so a estrutura de pastas e arquivos; nao toca em banco nem Vault.

    Para criar o projeto junto com sistema, schema, role e Vault, use `luftbase projeto novo`.
    """

    try:
        arquivos = gerar_projeto(
            nome,
            destino=destino,
            schema=schema,
            porta=porta,
            sistema_id=sistema_id,
            forcar=forcar,
        )
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    click.echo(f"projeto={nome} status=criado arquivos={len(arquivos)}")
    for arq in arquivos:
        click.echo(f"  + {arq.name}")


@projeto.command("novo")
@click.argument("nome", required=False)
@click.option(
    "--ambiente",
    type=click.Choice(AMBIENTES_DA_CLI),
    default="desenvolvimento",
    show_default=True,
    help="Ambiente do Vault e do core onde o sistema sera cadastrado.",
)
@click.option(
    "--destino",
    default=None,
    type=click.Path(path_type=Path),
    help="Onde criar a pasta do projeto (padrao: ./NOME).",
)
@click.option("--schema", default=None, help="Schema do sistema (padrao: derivado do nome).")
@click.option("--porta", default=9000, show_default=True, type=int, help="Porta HTTP local.")
@click.option(
    "--categoria",
    type=click.Choice([c for c in CODIGOS_CATEGORIA if c != "HUB"]),
    default="APLICACAO",
    show_default=True,
)
@click.option("--descricao", default=None, help="Descricao corporativa do sistema.")
@click.option("--icone", default="ph-bold ph-app-window", show_default=True)
@click.option("--cor", default="#2563eb", show_default=True)
@click.option(
    "--grupo-acesso",
    default=GRUPO_TI_PADRAO,
    show_default=True,
    type=int,
    help="Grupo que recebe a permissao base de acesso.",
)
@click.option(
    "--sistema-id", default=None, type=click.IntRange(min=1), help="ID manual (opcional)."
)
@click.option(
    "--env-referencia",
    default=None,
    type=click.Path(path_type=Path, dir_okay=False),
    help="`.env` de outro sistema do mesmo ambiente; copia Vault, LDAP e sessao (nunca o ID).",
)
@click.option("--usuario-banco", default=None, help="Usuario administrativo do PostgreSQL.")
@click.option("--vault-url", default=VAULT_URL_PADRAO, show_default=True)
@click.option("--vault-mount", default="secret", show_default=True)
@click.option("--vault-namespace", default="luft", show_default=True)
@click.option("--banco-host", default=None, help="Sobrepoe o host do core descoberto no Vault.")
@click.option("--banco-porta", default=None, type=int, help="Sobrepoe a porta do core.")
@click.option("--banco-nome", default=None, help="Sobrepoe o nome do banco do core.")
@click.option(
    "--somente-estrutura",
    is_flag=True,
    help="Cria so a pasta do projeto; nao cadastra sistema, schema nem Vault.",
)
@click.option("--forcar", is_flag=True, help="Sobrescreve a pasta do projeto se nao estiver vazia.")
@click.option("--sim", is_flag=True, help="Nao pede confirmacao.")
def novo(
    nome: str | None,
    ambiente: str,
    destino: Path | None,
    schema: str | None,
    porta: int,
    categoria: str,
    descricao: str | None,
    icone: str,
    cor: str,
    grupo_acesso: int,
    sistema_id: int | None,
    env_referencia: Path | None,
    usuario_banco: str | None,
    vault_url: str,
    vault_mount: str,
    vault_namespace: str,
    banco_host: str | None,
    banco_porta: int | None,
    banco_nome: str | None,
    somente_estrutura: bool,
    forcar: bool,
    sim: bool,
) -> None:
    """Cria um projeto completo: pasta no padrao Luft, sistema, schema, role, Vault e `.env`.

    Ordem: 1) estrutura de pastas; 2) conexao com Vault e PostgreSQL (credenciais pedidas no
    terminal); 3) sistema no core, schema, role com senha aleatoria e segredo no Vault; 4) `.env`
    com o ID gerado. Se o passo 2 ou 3 falhar, nada fica gravado no banco nem no Vault e a pasta
    pode ser refeita com `--forcar`.
    """

    ambiente = normalizar_ambiente_da_cli(ambiente)
    if nome is None:
        nome = click.prompt("Nome do projeto (ex: Luft-Control)", type=str)
    try:
        plano = PlanoProjeto.criar(nome, esquema=schema, porta=porta, descricao=descricao)
        raiz = destino if destino is not None else Path.cwd() / plano.pacote_dir
        referencia = ler_env_referencia(env_referencia) if env_referencia else None
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro

    valores, erros = validar_payload_novo_sistema(
        {
            "IdSistema": sistema_id,
            "Nome": plano.nome,
            "Categoria": categoria,
            "Descricao": plano.descricao,
            "Icone": icone,
            "Cor": cor,
            "Link": f"{plano.prefixo_rota}/",
            "SchemaAplicacao": plano.esquema,
        }
    )
    if erros:
        detalhe = "; ".join(f"{campo}: {texto}" for campo, texto in erros.items())
        raise click.ClickException(f"Dados invalidos: {detalhe}")

    click.echo(f"projeto={plano.nome} ambiente={ambiente}")
    click.echo(f"pasta={raiz}")
    click.echo(f"schema={plano.esquema} porta={plano.porta}")
    if somente_estrutura:
        click.echo("modo=somente-estrutura (sem banco nem Vault)")
    if not sim:
        click.confirm("Criar o projeto?", abort=True)

    try:
        gerados = gerar_aplicacao(plano, raiz, ambiente=ambiente, forcar=forcar)
        _gerar_arquivos_deploy(
            plano.identificador,
            plano.nome,
            plano.pacote_dir,
            raiz / "deploy",
            forcar=True,
            porta=plano.porta,
        )
    except ErroConfiguracao as erro:
        raise click.ClickException(str(erro)) from erro
    click.echo(f"estrutura=criada arquivos={len(gerados)}")
    if somente_estrutura:
        click.echo("proximo_passo=cadastrar o sistema no Workspace e preencher o .env")
        return

    sessao = abrir_sessao_operador(
        ambiente=ambiente,
        vault_url=vault_url,
        vault_mount=vault_mount,
        namespace=vault_namespace,
        usuario_banco=usuario_banco,
        banco_host=banco_host,
        banco_porta=banco_porta,
        banco_nome=banco_nome,
    )
    destino_core = sessao.destino
    click.echo(f"core={destino_core.host}:{destino_core.porta}/{destino_core.banco}")
    try:
        exigir_core_atualizado(sessao.provisionador.engine_administrativo())
        resultado = cadastrar_sistema(
            sessao.provisionador.engine_administrativo(),
            valores,
            provisionador=sessao.provisionador,
            alias_conexao=sessao.alias_conexao,
            grupo_acesso=grupo_acesso,
            ao_etapa=lambda texto: click.echo(f"  + {texto}"),
        )
    except ErroCadastroSistema as falha:
        raise click.ClickException(
            f"Nada foi gravado no banco nem no Vault. {falha.mensagem}"
        ) from falha
    finally:
        sessao.provisionador.encerrar()

    arquivo_env = escrever_env(
        raiz,
        plano,
        sistema_id=resultado.id_sistema,
        ambiente=ambiente,
        referencia=referencia,
    )
    click.echo(f"sistema_id={resultado.id_sistema}")
    click.echo(f"env={arquivo_env}")
    if referencia is None or not referencia.get("LUFT_VAULT_TOKEN"):
        click.echo(
            "atencao=preencha LUFT_VAULT_TOKEN e LUFT_TOKEN_ACESSO no .env "
            "(use --env-referencia para copia-los de outro sistema)"
        )
    click.echo(f"proximo_passo=cd {raiz} ; pip install -r requirements.txt ; python App.py")


@projeto.command("deploy")
@click.argument("identificador")
@click.option("--nome", default=None, help="Nome de exibicao da aplicacao.")
@click.option(
    "--destino",
    default="deploy",
    type=click.Path(path_type=Path),
    help="Diretorio de destino dos artefatos.",
)
@click.option("--forcar", is_flag=True, help="Sobrescreve arquivos existentes.")
def deploy(identificador: str, nome: str | None, destino: Path, forcar: bool) -> None:
    """Gera artefatos revisaveis de deploy Nginx e NSSM para uma aplicacao."""

    id_validado = validar_identificador_tecnico(identificador)
    nome_validado = (nome or id_validado.replace("-", " ").title()).strip()
    pacote = id_validado.replace("-", "_")

    arquivos = _gerar_arquivos_deploy(
        id_validado,
        nome_validado,
        pacote,
        destino,
        forcar=forcar,
    )
    click.echo(f"deploy={identificador} gerados={len(arquivos)}")
    for arq in arquivos:
        click.echo(f"  + {arq.name}")
