"""Comandos de scaffolding e geracao deterministica de aplicacoes LuftBase."""

from __future__ import annotations

from pathlib import Path

import click

from luftbase.configuracao.identificadores import (
    validar_esquema_aplicacao,
    validar_identificador_tecnico,
)
from luftbase.nucleo.excecoes import ErroConfiguracao


def _gerar_arquivos_deploy(
    identificador: str,
    nome: str,
    pacote: str,
    diretorio_deploy: Path,
    *,
    forcar: bool = False,
) -> list[Path]:
    """Gera artefatos revisaveis de deploy Nginx e NSSM."""

    diretorio_deploy.mkdir(parents=True, exist_ok=True)
    arquivos: list[tuple[str, str]] = [
        (
            "nginx.conf",
            f"""# Configuracao de proxy reverso Nginx para {identificador}
# ATENCAO: Este arquivo e um artefato revisavel. Nao altere o servidor sem revisao previa.

upstream {pacote}_backend {{
    server 127.0.0.1:8000;
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
$AppParameters = "-m waitress --listen=127.0.0.1:8000 --call {pacote}.app:criar_app"

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
    identificador: str,
    *,
    sistema_id: int,
    nome: str | None = None,
    destino: Path | str | None = None,
    schema: str | None = None,
    forcar: bool = False,
) -> list[Path]:
    """Gera deterministica e atomicamente a arvore de uma aplicacao nova."""

    if isinstance(sistema_id, bool) or sistema_id < 0:
        raise ErroConfiguracao("sistema_id deve ser um inteiro nao negativo.")
    id_validado = validar_identificador_tecnico(identificador)
    nome_validado = (nome or id_validado.replace("-", " ").title()).strip()
    pacote = id_validado.replace("-", "_")
    schema_validado = validar_esquema_aplicacao(schema or pacote)

    diretorio_destino = Path(destino) if destino is not None else Path.cwd() / id_validado
    if diretorio_destino.exists() and any(diretorio_destino.iterdir()) and not forcar:
        raise click.UsageError(
            f"O diretorio {str(diretorio_destino)!r} ja existe e nao esta vazio. "
            "Use --forcar para sobrescrever."
        )

    diretorio_destino.mkdir(parents=True, exist_ok=True)

    arquivos: list[tuple[str, str]] = [
        (
            "pyproject.toml",
            f"""[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{id_validado}"
version = "0.1.0"
description = "{nome_validado}"
requires-python = ">=3.11"
dependencies = [
    "luft-base>=0.1.0a1",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
""",
        ),
        (
            ".env.example",
            f"""# Esquema PostgreSQL da aplicacao: {schema_validado}
LUFT_SISTEMA_ID={sistema_id}
LUFT_APLICACAO_VERSAO=0.1.0
LUFT_AMBIENTE=desenvolvimento

LUFT_VAULT_ENDERECO=http://servidor-vault:8200
LUFT_VAULT_NAMESPACE=luft
LUFT_VAULT_TOKEN=<TOKEN_VAULT_PROTEGIDO>
LUFT_TOKEN_ACESSO=<TOKEN_ACESSO_DA_APLICACAO>

LUFT_LDAP_SERVIDOR=ad.luft.interno
LUFT_LDAP_DOMINIO=LUFTFARMA
LUFT_LDAP_TRANSPORTE=ldaps
LUFT_LDAP_PORTA=636
LUFT_LDAP_TIMEOUT_SEGUNDOS=5

LUFT_SESSAO_COOKIE_NOME=luft_sessao
LUFT_SESSAO_COOKIE_CAMINHO=/
LUFT_SESSAO_COOKIE_SAMESITE=Lax
LUFT_SESSAO_COOKIE_SEGURO=false
LUFT_SESSAO_TTL_MINUTOS=10
""",
        ),
        (
            ".gitignore",
            """__pycache__/
*.py[cod]
.venv/
*.egg-info/
dist/
build/
.env
.pytest_cache/
.ruff_cache/
""",
        ),
        (
            "README.md",
            f"""# {nome_validado}

Aplicacao corporativa baseada na plataforma LuftBase.

## Desenvolvimento

1. Crie o ambiente virtual e instale as dependencias:
   ```powershell
   python -m venv .venv
   .venv\\Scripts\\activate
   pip install -e .
   ```

2. Configure o arquivo `.env` a partir de `.env.example`.

3. Execute os testes:
   ```powershell
   python -m pytest
   ```

4. Inicie o servidor:
   ```powershell
   flask --app {pacote}.app:criar_app run
   ```
""",
        ),
        (
            f"src/{pacote}/__init__.py",
            f"""\"\"\"Pacote da aplicacao {nome_validado}.\"\"\"

from {pacote}.app import criar_app

__all__ = ["criar_app"]
""",
        ),
        (
            f"src/{pacote}/app.py",
            f"""\"\"\"Fabrica de aplicacao Flask padronizada com LuftBase.\"\"\"

from __future__ import annotations

from flask import Flask
from luftbase import PlataformaLuft
from luftbase.configuracao import ConfiguracaoLuftBase

from {pacote}.rotas import bp_principal


def criar_app(
    configuracao: ConfiguracaoLuftBase | None = None,
    plataforma: PlataformaLuft | None = None,
) -> Flask:
    \"\"\"Cria e inicializa a aplicacao com a extensao LuftBase.\"\"\"

    app = Flask(__name__)
    base = plataforma or PlataformaLuft()
    base.inicializar(app, configuracao=configuracao)
    app.register_blueprint(bp_principal)
    return app
""",
        ),
        (
            f"src/{pacote}/rotas.py",
            f"""\"\"\"Rotas principais da aplicacao {nome_validado}.\"\"\"

from __future__ import annotations

from flask import Blueprint, render_template

bp_principal = Blueprint("principal", __name__)


@bp_principal.get("/")
def inicio() -> str:
    \"\"\"Pagina inicial da aplicacao estendendo o layout corporativo.\"\"\"

    return render_template("{pacote}/inicio.html")
""",
        ),
        (
            f"src/{pacote}/templates/{pacote}/inicio.html",
            """{% extends "luftbase/base.html" %}

{% block titulo %}{{ config.LUFT_APLICACAO_NOME }}{% endblock %}

{% block conteudo %}
<div class="luft-cartao">
    <h1 class="luft-titulo">{{ config.LUFT_APLICACAO_NOME }}</h1>
    <p class="luft-texto">Bem-vindo a aplicacao corporativa construida com LuftBase.</p>
</div>
{% endblock %}
""",
        ),
        ("tests/__init__.py", ""),
        (
            "tests/test_app.py",
            f"""\"\"\"Testes estruturais da aplicacao {nome_validado}.\"\"\"

from {pacote}.app import criar_app
from luftbase import PlataformaLuft
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.infraestrutura import FabricaInfraestruturaMemoria


def test_aplicacao_inicializa_e_responde_inicio() -> None:
    config = ConfiguracaoLuftBase.de_mapeamento(
        {{
            "LUFT_SISTEMA_ID": "{sistema_id}",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft.interno",
            "LUFT_LDAP_DOMINIO": "LUFTFARMA",
        }}
    )
    app = criar_app(
        configuracao=config,
        plataforma=PlataformaLuft(FabricaInfraestruturaMemoria()),
    )
    app.testing = True

    cliente = app.test_client()
    resposta = cliente.get("/")

    assert resposta.status_code == 200
    assert "Sistema {sistema_id}" in resposta.text
""",
        ),
    ]

    gerados: list[Path] = []
    for caminho_relativo, conteudo in arquivos:
        destino_arquivo = diretorio_destino / caminho_relativo
        destino_arquivo.parent.mkdir(parents=True, exist_ok=True)
        destino_arquivo.write_text(conteudo, encoding="utf-8")
        gerados.append(destino_arquivo)

    # Gera tambem os artefatos revisaveis de deploy
    deploy_arquivos = _gerar_arquivos_deploy(
        id_validado,
        nome_validado,
        pacote,
        diretorio_destino / "deploy",
        forcar=forcar,
    )
    gerados.extend(deploy_arquivos)
    return sorted(gerados)


@click.group("projeto")
def projeto() -> None:
    """Gerenciamento e scaffolding de projetos LuftBase."""


@projeto.command("criar")
@click.argument("identificador")
@click.option("--sistema-id", required=True, type=click.IntRange(min=0))
@click.option("--nome", default=None, help="Nome de exibicao da aplicacao.")
@click.option(
    "--destino",
    default=None,
    type=click.Path(path_type=Path),
    help="Diretorio de destino.",
)
@click.option("--schema", default=None, help="Esquema particular da aplicacao no PostgreSQL.")
@click.option(
    "--forcar",
    is_flag=True,
    help="Sobrescreve arquivos no destino se nao estiver vazio.",
)
def criar(
    identificador: str,
    sistema_id: int,
    nome: str | None,
    destino: Path | None,
    schema: str | None,
    forcar: bool,
) -> None:
    """Cria uma nova aplicacao conforme os padroes arquiteturais do LuftBase."""

    try:
        arquivos = gerar_projeto(
            identificador,
            sistema_id=sistema_id,
            nome=nome,
            destino=destino,
            schema=schema,
            forcar=forcar,
        )
    except Exception as erro:
        raise click.ClickException(str(erro)) from erro

    click.echo(f"projeto={identificador} status=criado arquivos={len(arquivos)}")
    for arq in arquivos:
        click.echo(f"  + {arq.name}")


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
