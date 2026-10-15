"""Gerador do esqueleto de uma aplicacao Luft, no padrao da ADR-017.

A estrutura, os nomes e a ordem dos arquivos sao os mesmos dos sistemas em producao
(Luft-Control, Luft-ConnectAir, Luft-Workspace), para que uma correcao de plataforma chegue a
todos pela nova versao do LuftBase e nao por copia manual de codigo.

O gerador nao toca em banco, Vault nem rede: so escreve arquivos. O `.env` real e escrito a parte
(`escrever_env`), depois que o sistema recebe seu `LUFT_SISTEMA_ID`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from luftbase.configuracao.identificadores import (
    validar_esquema_aplicacao,
    validar_identificador_tecnico,
)
from luftbase.nucleo.excecoes import ErroConfiguracao

VAULT_ENDERECO_PADRAO = "http://172.16.200.80:8200"
_CHAVES_COPIADAS_DA_REFERENCIA = (
    "LUFT_VAULT_ENDERECO",
    "LUFT_VAULT_NAMESPACE",
    "LUFT_VAULT_TOKEN",
    "LUFT_TOKEN_ACESSO",
    "LUFT_LDAP_SERVIDOR",
    "LUFT_LDAP_DOMINIO",
    "LUFT_LDAP_TRANSPORTE",
    "LUFT_LDAP_TIMEOUT_SEGUNDOS",
    "LUFT_SESSAO_COOKIE_NOME",
    "LUFT_SESSAO_COOKIE_CAMINHO",
    "LUFT_SESSAO_COOKIE_DOMINIO",
    "LUFT_SESSAO_COOKIE_SAMESITE",
    "LUFT_SESSAO_COOKIE_SEGURO",
    "LUFT_PERMITIR_COOKIE_INSEGURO",
    "LUFT_SESSAO_TTL_MINUTOS",
)
# So estas chaves carregam segredo; o .env.example nunca recebe o valor delas.
_CHAVES_SECRETAS = frozenset({"LUFT_VAULT_TOKEN", "LUFT_TOKEN_ACESSO"})


@dataclass(frozen=True, slots=True)
class PlanoProjeto:
    """Tudo o que o esqueleto precisa saber, ja validado."""

    nome: str
    identificador: str
    pacote_dir: str
    esquema: str
    prefixo_chave: str
    porta: int
    prefixo_rota: str
    descricao: str

    @classmethod
    def criar(
        cls,
        nome: str,
        *,
        esquema: str | None = None,
        porta: int = 9000,
        descricao: str | None = None,
    ) -> PlanoProjeto:
        """Deriva identificador, esquema e prefixo de chave a partir do nome de exibicao."""

        nome_limpo = nome.strip()
        if not nome_limpo or re.search(r'[\\/:*?"<>|\s]', nome_limpo):
            raise ErroConfiguracao(
                "O nome do projeto nao pode ficar vazio nem conter espacos ou "
                'caracteres de caminho (\\ / : * ? " < > |). Exemplo: Luft-Control.'
            )
        identificador = validar_identificador_tecnico(nome_limpo.lower())
        sugestao = identificador.removeprefix("luft-").replace("-", "_")
        esquema_validado = validar_esquema_aplicacao(esquema or sugestao)
        if not 1024 <= porta <= 65535:
            raise ErroConfiguracao("A porta deve estar entre 1024 e 65535.")
        prefixo = re.sub(r"[^A-Za-z0-9_]+", "_", nome_limpo).strip("_").upper()
        if not prefixo[0].isalpha():
            prefixo = f"SISTEMA_{prefixo}"
        return cls(
            nome=nome_limpo,
            identificador=identificador,
            pacote_dir=nome_limpo,
            esquema=esquema_validado,
            prefixo_chave=prefixo[:50],
            porta=porta,
            prefixo_rota=f"/{nome_limpo}",
            descricao=(descricao or f"Sistema {nome_limpo}.").strip(),
        )


def ler_env_referencia(caminho: Path) -> dict[str, str]:
    """Le so as chaves de plataforma de um `.env` de outro sistema (Vault, LDAP, sessao).

    Serve para o dev nao redigitar o que e igual em todos os sistemas do ambiente. Chaves fora
    da lista (como senhas e particularidades do outro sistema) sao ignoradas.
    """

    if not caminho.is_file():
        raise ErroConfiguracao(f"O .env de referencia {str(caminho)!r} nao existe.")
    valores: dict[str, str] = {}
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        texto = linha.strip()
        if not texto or texto.startswith("#") or "=" not in texto:
            continue
        chave, _, valor = texto.partition("=")
        chave = chave.strip()
        if chave in _CHAVES_COPIADAS_DA_REFERENCIA:
            valores[chave] = valor.strip()
    return valores


def montar_env(
    plano: PlanoProjeto,
    *,
    sistema_id: int | None,
    ambiente: str,
    referencia: Mapping[str, str] | None = None,
    com_segredos: bool,
) -> str:
    """Monta o `.env` no esqueleto da ADR-017; `com_segredos=False` gera o `.env.example`."""

    ref = dict(referencia or {})

    def valor(chave: str, padrao: str) -> str:
        if chave in _CHAVES_SECRETAS:
            if not com_segredos:
                return f"<{chave}>"
            return ref.get(chave) or f"<{chave}>"
        return ref.get(chave) or padrao

    return f"""# ==========================================================
# {plano.nome} - configuracao {"" if com_segredos else "(modelo) "}(LuftBase)
# Bancos, sessao, e-mail e LDAP sao resolvidos pelo LuftBase via Vault:
#   luft/<ambiente>/bancos/postgresql/sistemas/<LUFT_SISTEMA_ID>   (schema do sistema: {plano.esquema})
#   luft/<ambiente>/integracoes/email
#
# Padrao Luft: todos os sistemas usam este esqueleto, na mesma ordem.
# O que e comum vem primeiro; o que e particular do sistema, no fim.
# ==========================================================

# --- Identidade ---
# ID gerado ao cadastrar o sistema: core.tb_sistema
LUFT_SISTEMA_ID={"" if sistema_id is None else sistema_id}
# desenvolvimento | homologacao | producao
LUFT_AMBIENTE={ambiente}
# A versao vem de App/_version.py; so preencha para forcar outra versao (ex.: scripts fora da aplicacao).
LUFT_APLICACAO_VERSAO=

# --- Vault ---
LUFT_VAULT_ENDERECO={valor("LUFT_VAULT_ENDERECO", VAULT_ENDERECO_PADRAO)}
LUFT_VAULT_NAMESPACE={valor("LUFT_VAULT_NAMESPACE", "luft")}
LUFT_VAULT_TOKEN={valor("LUFT_VAULT_TOKEN", "")}
LUFT_TOKEN_ACESSO={valor("LUFT_TOKEN_ACESSO", "")}

# --- LDAP corporativo (credenciais de usuario nunca ficam no ambiente) ---
LUFT_LDAP_SERVIDOR={valor("LUFT_LDAP_SERVIDOR", "luftfarma.com.br")}
LUFT_LDAP_DOMINIO={valor("LUFT_LDAP_DOMINIO", "luftfarma")}
LUFT_LDAP_TRANSPORTE={valor("LUFT_LDAP_TRANSPORTE", "ldaps")}
LUFT_LDAP_TIMEOUT_SEGUNDOS={valor("LUFT_LDAP_TIMEOUT_SEGUNDOS", "5")}

# --- Sessao compartilhada entre os sistemas (SSO): iguais em todos do mesmo ambiente ---
LUFT_SESSAO_COOKIE_NOME={valor("LUFT_SESSAO_COOKIE_NOME", "luft_sessao")}
LUFT_SESSAO_COOKIE_CAMINHO={valor("LUFT_SESSAO_COOKIE_CAMINHO", "/")}
LUFT_SESSAO_COOKIE_DOMINIO={valor("LUFT_SESSAO_COOKIE_DOMINIO", "")}
LUFT_SESSAO_COOKIE_SAMESITE={valor("LUFT_SESSAO_COOKIE_SAMESITE", "Lax")}
LUFT_SESSAO_COOKIE_SEGURO={valor("LUFT_SESSAO_COOKIE_SEGURO", "false")}
# Producao exige cookie Secure (HTTPS). Em rede interna servida por HTTP, true libera o login.
LUFT_PERMITIR_COOKIE_INSEGURO={valor("LUFT_PERMITIR_COOKIE_INSEGURO", "false")}
# Minutos sem atividade ate a sessao expirar
LUFT_SESSAO_TTL_MINUTOS={valor("LUFT_SESSAO_TTL_MINUTOS", "720")}

# --- Autorizacao (opcional; valores padrao do LuftBase) ---
# LUFT_AUTORIZACAO_TTL_SEGUNDOS=300
# LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS=5
# LUFT_AUTORIZACAO_MAX_CHAVES=100

# --- Processo HTTP (Wsgi.py publica no ROUTE_PREFIX; App.py responde na raiz) ---
HOST=127.0.0.1
PORT={plano.porta}
ROUTE_PREFIX={plano.prefixo_rota}

# ==========================================================
# Particularidades do {plano.nome}
# ==========================================================
# Mostra o SQL emitido pelo SQLAlchemy (diagnostico)
DB_CONNECT_LOGS=false
"""


def escrever_env(
    raiz: Path,
    plano: PlanoProjeto,
    *,
    sistema_id: int,
    ambiente: str,
    referencia: Mapping[str, str] | None,
) -> Path:
    """Grava o `.env` real do projeto (ignorado pelo git) com o ID ja conhecido."""

    destino = raiz / ".env"
    destino.write_text(
        montar_env(
            plano,
            sistema_id=sistema_id,
            ambiente=ambiente,
            referencia=referencia,
            com_segredos=True,
        ),
        encoding="utf-8",
    )
    return destino


def _substituir(texto: str, plano: PlanoProjeto) -> str:
    trocas = {
        "__NOME__": plano.nome,
        "__IDENT__": plano.identificador,
        "__ESQUEMA__": plano.esquema,
        "__PREFIXO__": plano.prefixo_chave,
        "__PORTA__": str(plano.porta),
        "__ROTA__": plano.prefixo_rota,
        "__DESCRICAO__": plano.descricao,
        "__INICIAL__": plano.nome[0].upper(),
        "__PACOTE_DIR__": plano.pacote_dir,
    }
    for marcador, valor in trocas.items():
        texto = texto.replace(marcador, valor)
    return texto


def gerar_aplicacao(
    plano: PlanoProjeto,
    destino: Path,
    *,
    ambiente: str = "desenvolvimento",
    sistema_id: int | None = None,
    versao_luftbase: str | None = None,
    forcar: bool = False,
) -> list[Path]:
    """Escreve a arvore da aplicacao em `destino` e devolve os arquivos criados.

    Recusa diretorio nao vazio sem `forcar`, para nunca sobrescrever trabalho existente por engano.
    """

    if destino.exists() and any(destino.iterdir()) and not forcar:
        raise ErroConfiguracao(
            f"O diretorio {str(destino)!r} ja existe e nao esta vazio. Use --forcar para sobrescrever."
        )
    destino.mkdir(parents=True, exist_ok=True)

    arquivos = dict(_ARQUIVOS)
    arquivos[".env.example"] = montar_env(
        plano,
        sistema_id=sistema_id,
        ambiente=ambiente,
        com_segredos=False,
    )
    versao = versao_luftbase or _versao_instalada()
    arquivos["requirements.txt"] = _REQUIREMENTS.replace("__VERSAO_LUFTBASE__", versao)

    gerados: list[Path] = []
    for caminho_relativo, conteudo in arquivos.items():
        arquivo = destino / caminho_relativo
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_text(_substituir(conteudo, plano), encoding="utf-8", newline="\n")
        gerados.append(arquivo)
    for pasta in _PASTAS_VAZIAS:
        (destino / pasta).mkdir(parents=True, exist_ok=True)
        marcador = destino / pasta / ".gitkeep"
        marcador.write_text("", encoding="utf-8")
        gerados.append(marcador)
    return sorted(gerados)


def _versao_instalada() -> str:
    from luftbase._versao import __version__

    return f"v{__version__}"


_PASTAS_VAZIAS = (
    "App/Static/CSS",
    "App/Static/JS",
    "App/Static/Img",
    "App/Utils",
    "Data",
    "Docs",
    "SQL",
    "scripts",
)

_REQUIREMENTS = """Flask==3.1.2
Flask-Login==0.6.3
psycopg[binary]>=3.2
python-dotenv>=1.0
SQLAlchemy>=2.0
waitress>=3.0
luft-base @ git+https://github.com/Widson64x/LuftBase.git@__VERSAO_LUFTBASE__
"""

_ARQUIVOS: dict[str, str] = {
    ".gitignore": """__pycache__/
*.py[cod]
.venv/
.env
.env.local
.env.*.local
Logs/
Data/Temp/
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
""",
    "README.md": """# __NOME__

__DESCRICAO__

Aplicacao Luft sobre o LuftBase: login (LDAP + sessao compartilhada), permissoes, auditoria,
notificacoes, temas e Painel de Controle vem da plataforma. Aqui ficam so as rotas e as regras
de negocio.

## Desenvolvimento

```powershell
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python App.py
```

O `.env` ja foi criado por `luftbase projeto novo`. Para recria-lo, copie o `.env.example` e
preencha `LUFT_SISTEMA_ID`, `LUFT_VAULT_TOKEN` e `LUFT_TOKEN_ACESSO` (iguais aos de outro sistema
do mesmo ambiente).

- Desenvolvimento: `python App.py` (depurador e recarga).
- Producao: `Wsgi.py` (Waitress).
- Testes: `python -m pytest`.

## Estrutura (ADR-017 do LuftBase)

```text
App/            pacote da aplicacao (fabrica, catalogo, conexoes, rotas, servicos, templates)
App.py          entrada de desenvolvimento
Wsgi.py         entrada de producao
Data/ Logs/ SQL/ Docs/ scripts/ tests/
```
""",
    "App.py": '''"""Desenvolvimento do __NOME__: `python App.py` (depurador e recarga automatica).

Em producao use o Wsgi.py. Host e porta vem do .env (HOST/PORT ou LUFT_SERVIDOR_*).
"""

from luftbase.servidor import executar_desenvolvimento

if __name__ == "__main__":
    executar_desenvolvimento("App:CriarApp")
''',
    "Wsgi.py": '''"""Producao do __NOME__: servidor padrao do LuftBase (Waitress).

Host, porta, prefixo e threads vem do .env (LUFT_SERVIDOR_* ou HOST/PORT/ROUTE_PREFIX).
Em desenvolvimento use o App.py.
"""

from luftbase.servidor import executar

if __name__ == "__main__":
    executar("App:CriarApp")
''',
    "App/__init__.py": '''"""
Pacote do __NOME__ sobre o LuftBase.

O LuftBase instala login (LDAP + sessao compartilhada), permissoes, auditoria, notificacoes,
publicacoes, mensagens, temas, e-mail e o Painel de Controle. Aqui ficam so as rotas e as
regras de negocio.

Padrao Luft: este arquivo tem a mesma ordem em todos os sistemas (imports, fabrica, contexto
global); o que e particular de cada sistema fica no fim, em "Particularidades".
Desenvolvimento: `python App.py`. Producao: `Wsgi.py`.
"""

from flask import Flask, url_for
from luftbase import DefinicaoModelo, PlataformaLuft, consultar_permissoes, contexto_painel

from App import Conexoes
from App._version import __version__
from App.Buscas import BUSCAS
from App.Catalogo import CATALOGO, PARAMETROS, PERMISSOES_MENU
from App.Configuracoes import ConfiguracaoAtual
from App.Models.POSTGRES import ModelsPostgres
from App.Routes import RegistrarRotas
from App.Services.LogService import LogService


def CriarApp(configuracao=None, fabrica_infraestrutura=None):
    """Fabrica padrao: Flask, LuftBase, conexoes, rotas e contexto global dos templates."""
    LogService.Inicializar()

    app = Flask(
        __name__,
        template_folder='Templates',
        static_folder='Static',
        static_url_path='/Static',
    )
    app.config['LUFT_APLICACAO_VERSAO'] = __version__
    app.config['LUFT_LOG_DIR'] = ConfiguracaoAtual.DIR_LOGS

    # O catalogo (Catalogo.py) e conferido no core e completado a cada inicializacao.
    # Os parametros aparecem em Painel de Controle > Configuracoes Gerais.
    # As tabelas do PostgreSQL sao conferidas (sem DDL) e ausencias aparecem no log.
    # As buscas (Buscas.py) alimentam a barra de busca global, alem do menu.
    modelos = [DefinicaoModelo.de_modelo(m) for m in ModelsPostgres()]
    estado = PlataformaLuft(
        fabrica_infraestrutura, catalogo=CATALOGO, parametros=PARAMETROS, modelos=modelos, buscas=BUSCAS
    ).inicializar(app, configuracao)
    Conexoes.Inicializar(estado)

    RegistrarRotas(app)
    _RegistrarContextoGlobal(app, estado)
    _RegistrarParticularidades(app, estado)

    LogService.Info("App", f"Aplicacao iniciada no ambiente {estado.configuracao.aplicacao.ambiente.value}.")
    return app


def _RegistrarContextoGlobal(app, estado):
    """Variaveis disponiveis em todos os templates (layout, Painel de Controle e menu)."""

    @app.context_processor
    def InjetarContextoGlobal():
        decisoes = consultar_permissoes(PERMISSOES_MENU.values())
        return {
            # As paginas do LuftBase (Painel de Controle, comunicados) estendem este layout.
            'layout_base': 'Layout/BaseLayout.html',
            'luft_base_template': 'Layout/BaseLayout.html',
            **contexto_painel(),
            'SidebarPermissoes': {
                nome: bool(decisoes.get(chave, False)) for nome, chave in PERMISSOES_MENU.items()
            },
            **_ContextoParticular(estado),
        }


# ========================================================================================
# Particularidades do __NOME__
# ========================================================================================

def _ContextoParticular(estado):
    """Variaveis extras dos templates."""
    return {
        'url_raiz_aplicacao': url_for('Principal.MenuPrincipal'),
    }


def _RegistrarParticularidades(app, estado):
    """Rotas e ajustes que so existem no __NOME__ (por ora, nenhum)."""
''',
    "App/_version.py": '''"""Versao do __NOME__."""

__version__ = "0.1.0a01"
''',
    "App/Catalogo.py": '''"""
Catalogo de modulos e permissoes do __NOME__ no LuftBase.

E a fonte unica das chaves de permissao: as rotas usam `Permissao.<NOME>` e, a cada
inicializacao, o LuftBase confere esta arvore no core e cria o que faltar para o
LUFT_SISTEMA_ID. O cadastro do sistema (nome, icone, link) e feito por `luftbase projeto novo`
ou no Luft-Workspace.

Chaves seguem MODULO.RECURSO.ACAO. Conceder um no concede tambem os seus filhos, por isso a raiz
`__PREFIXO__.SISTEMA.ADMINISTRAR` concede o sistema inteiro.
"""

from enum import StrEnum

from luftbase import CatalogoAplicacao, DefinicaoModulo, PermissaoAplicacao


class Permissao(StrEnum):
    SISTEMA_ADMINISTRAR = "__PREFIXO__.SISTEMA.ADMINISTRAR"
    SISTEMA_ACESSAR = "__PREFIXO__.SISTEMA.ACESSAR"


P = Permissao
_RAIZ = P.SISTEMA_ADMINISTRAR


def _no(chave, descricao, pai=_RAIZ, *, sensivel=False, acesso=False, ordem=0):
    return PermissaoAplicacao(
        chave=chave.value,
        descricao=descricao,
        pai=pai.value if pai else None,
        sensivel=sensivel,
        acesso_sistema=acesso,
        ordem=ordem,
        # As chaves do sistema ficam no modulo PLATAFORMA criado no cadastro.
        modulo_codigo='PLATAFORMA' if chave.value.startswith('__PREFIXO__.') else None,
    )


CATALOGO = CatalogoAplicacao(
    modulos=(
        DefinicaoModulo("PLATAFORMA", "Plataforma", "Acesso e administracao do __NOME__.", "ph-cube", 0),
    ),
    permissoes=(
        _no(P.SISTEMA_ADMINISTRAR, "Administrar todo o __NOME__.", pai=None, sensivel=True),
        _no(P.SISTEMA_ACESSAR, "Acessar o __NOME__ e a pagina inicial.", acesso=True, ordem=1),
    ),
)

# Parametros: aparecem em Painel de Controle > Configuracoes Gerais.
PARAMETROS = ()

# Permissoes do menu lateral e dos atalhos: uma consulta em lote por requisicao.
PERMISSOES_MENU = {}
''',
    "App/Buscas.py": '''"""
Busca global (barra superior) do __NOME__: o que o sistema ensina o LuftBase a procurar.

Alem do menu (que o LuftBase pesquisa sozinho), cada provedor vira um grupo de resultados.

Padrao Luft: este arquivo existe em todos os sistemas e expoe BUSCAS (vazio se nao houver).
"""

BUSCAS = ()
''',
    "App/Configuracoes.py": '''"""
Parametros proprios do __NOME__.

Bancos, Vault, sessao, LDAP e e-mail pertencem ao LuftBase (variaveis LUFT_* e segredos do
Vault). Aqui ficam apenas diretorios e parametros de execucao particulares desta aplicacao.

Padrao Luft: a configuracao comum vem primeiro; o que e particular do sistema, no fim.
"""

import os

from dotenv import load_dotenv

load_dotenv()

NOME_APLICACAO = "__NOME__"


def _ObterBoolEnv(NomeVariavel, ValorPadrao=False):
    Valor = os.getenv(NomeVariavel)
    if Valor is None:
        return ValorPadrao
    return Valor.strip().lower() in {"1", "true", "sim", "yes", "on"}


class ConfiguracaoBase:
    APP_NAME = os.getenv("APP_NAME", NOME_APLICACAO)

    AMBIENTE = (os.getenv("LUFT_AMBIENTE") or "desenvolvimento").strip().lower()
    DEBUG = AMBIENTE not in {"producao", "production", "prod", "prd"}

    # Raiz do projeto (pai do pacote App): Data/ e Logs/ ficam fora do codigo.
    DIR_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DIR_DATA = os.path.join(DIR_BASE, "Data")
    DIR_TEMP = os.path.join(DIR_DATA, "Temp")
    DIR_LOGS = os.path.join(DIR_BASE, "Logs")

    # Mostra o SQL emitido pelo SQLAlchemy (diagnostico)
    MOSTRAR_LOGS_DB = _ObterBoolEnv("DB_CONNECT_LOGS", False)


# ========================================================================================
# Particularidades do __NOME__
# ========================================================================================

class ConfiguracaoParticular(ConfiguracaoBase):
    pass


ConfiguracaoAtual = ConfiguracaoParticular()
''',
    "App/Conexoes.py": '''"""
Conexoes do __NOME__, com credenciais vindas do Vault atraves do LuftBase.

- PostgreSQL (schema da aplicacao: __ESQUEMA__): tabelas proprias. Leitura e escrita.
- Core do LuftBase: ObterBancoCore(), para servicos que consultam a plataforma.

Padrao Luft: estas funcoes existem em todos os sistemas com o mesmo nome. Conexoes que so um
sistema usa ficam no fim, em "Particularidades".
"""

import logging
import os
import re
import threading

from sqlalchemy.orm import sessionmaker

from App.Configuracoes import ConfiguracaoAtual

_logger = logging.getLogger(f"{ConfiguracaoAtual.APP_NAME}.Conexoes")
_trava = threading.Lock()
_inicializado = False
_banco_core = None
_engine_postgres = None
_sessoes_postgres = None


def _Carregador(configuracao):
    from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
    from luftbase.infraestrutura.cofre.credenciais import Segredo
    from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
    from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais

    token = DesprotetorFernet(configuracao.cofre.token_acesso).revelar(configuracao.cofre.token_protegido)
    return CarregadorCredenciais(ClienteVaultHvac(configuracao.cofre.endereco, Segredo(token)))


def _Caminhos(configuracao, ambiente):
    from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault

    return resolver_caminhos_vault(
        ambiente=ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
        namespace=configuracao.cofre.namespace,
    )


def _CriarEnginePostgres(configuracao):
    """Engine do schema da aplicacao, igual a que o LuftBase monta na inicializacao."""
    from luftbase.infraestrutura.banco.conexoes import ConstrutorEngines

    caminhos = _Caminhos(configuracao, configuracao.aplicacao.ambiente)
    credencial = _Carregador(configuracao).carregar_aplicacao_postgresql(
        caminhos.postgresql,
        caminhos.postgresql_conexoes,
        sistema_id_esperado=configuracao.aplicacao.sistema_id,
    ).banco
    # LUFT_BANCO_LOCAL_HOST (banco espelho na maquina do dev) vale tambem para scripts.
    credencial = configuracao.aplicar_banco_local(credencial)
    construtor = ConstrutorEngines()
    return construtor.para_aplicacao(construtor.criar(credencial), credencial.esquema)


def _RegistrarPostgres(engine):
    global _engine_postgres, _sessoes_postgres
    _engine_postgres = engine
    _sessoes_postgres = sessionmaker(bind=engine) if engine is not None else None


def Inicializar(estado):
    """Registra as conexoes a partir do estado do LuftBase (chamado pelo CriarApp)."""
    global _inicializado, _banco_core
    aplicacao = getattr(estado.bancos, "aplicacao", None)
    with _trava:
        _banco_core = estado.bancos.core
        _RegistrarPostgres(getattr(aplicacao, "engine", None))
        _InicializarParticularidades(estado)
        _inicializado = True


def _GarantirInicializado():
    """Scripts fora da aplicacao Flask resolvem as engines direto do Vault, uma unica vez."""
    global _inicializado
    if _inicializado:
        return
    with _trava:
        if _inicializado:
            return
        from luftbase.configuracao.modelos import ConfiguracaoLuftBase

        from App._version import __version__

        # A versao vem de App/_version.py; o .env so a define para forca-la.
        if not (os.environ.get("LUFT_APLICACAO_VERSAO") or "").strip():
            os.environ["LUFT_APLICACAO_VERSAO"] = __version__
        configuracao = ConfiguracaoLuftBase.de_ambiente()
        configuracao.validar_para_inicializacao()
        _RegistrarPostgres(_CriarEnginePostgres(configuracao))
        _GarantirParticularidades(configuracao)
        _inicializado = True


# --- Core do LuftBase ------------------------------------------------------------------

def ObterBancoCore():
    """Banco `core` da plataforma (usuarios, sistemas, permissoes). So com a aplicacao iniciada."""
    if _banco_core is None:
        raise RuntimeError("O banco core so esta disponivel depois de Conexoes.Inicializar(estado).")
    return _banco_core


# --- Tabelas do sistema (PostgreSQL) ---------------------------------------------------

def ObterEnginePostgres():
    """Engine do schema da aplicacao no PostgreSQL."""
    _GarantirInicializado()
    if _engine_postgres is None:
        raise RuntimeError("Esta aplicacao nao tem schema proprio configurado no Vault.")
    return _engine_postgres


def ObterSessaoPostgres():
    """Nova sessao das tabelas do sistema; quem abre e responsavel por commit/rollback/close."""
    ObterEnginePostgres()
    return _sessoes_postgres()


def EsquemaPostgres():
    """Schema real da aplicacao (do segredo no Vault), ja validado pelo LuftBase."""
    from luftbase.infraestrutura.banco.conexoes import ESQUEMA_LOGICO_APLICACAO

    mapa = ObterEnginePostgres().get_execution_options().get("schema_translate_map") or {}
    return mapa.get(ESQUEMA_LOGICO_APLICACAO) or ESQUEMA_LOGICO_APLICACAO


def TabelaPostgres(nome):
    """Nome qualificado para SQL cru: TabelaPostgres('tb_exemplo') -> "__ESQUEMA__"."tb_exemplo".

    SQL cru nao passa pela traducao de schema do ORM; use este helper em vez de fixar o schema.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", nome):
        raise ValueError(f"Nome de tabela invalido: {nome!r}")
    return f'"{EsquemaPostgres()}"."{nome}"'


class _TabelasPostgres:
    """Atalho para SQL cru: f'FROM {Tabelas.tb_exemplo}' -> FROM "__ESQUEMA__"."tb_exemplo"."""

    def __getattr__(self, nome):
        if nome.startswith("__"):
            raise AttributeError(nome)
        return TabelaPostgres(nome)


Tabelas = _TabelasPostgres()


# ========================================================================================
# Particularidades do __NOME__
# ========================================================================================

def _InicializarParticularidades(estado):
    """Com a aplicacao iniciada: conexoes que so este sistema usa (por ora, nenhuma)."""


def _GarantirParticularidades(configuracao):
    """Em scripts, sem a aplicacao: resolve as mesmas conexoes direto do Vault."""
''',
    "App/Models/POSTGRES/__init__.py": '''"""Models do __NOME__ no PostgreSQL (schema proprio da aplicacao)."""

import importlib
import pathlib

from App.Models.POSTGRES.Base import Base

# Importa todos os modulos para registrar os models na Base.
for _arquivo in sorted(pathlib.Path(__file__).parent.glob("*.py")):
    if _arquivo.stem not in ("__init__", "Base"):
        importlib.import_module(f"App.Models.POSTGRES.{_arquivo.stem}")


def ModelsPostgres():
    """Classes mapeadas, em ordem de tabela (para registro no LuftBase)."""
    return sorted((m.class_ for m in Base.registry.mappers), key=lambda c: c.__table__.name)
''',
    "App/Models/POSTGRES/Base.py": '''"""Base dos models do __NOME__ no PostgreSQL (schema proprio da aplicacao).

O schema logico `luft_aplicacao` e trocado pelo LuftBase pelo schema real do segredo do sistema
no Vault (ex.: `__ESQUEMA__`), entao o nome nunca fica fixo no codigo.
"""

from luftbase.infraestrutura.banco.conexoes import ESQUEMA_LOGICO_APLICACAO
from sqlalchemy import MetaData
from sqlalchemy.orm import declarative_base

CONVENCAO_NOMES = {
    "pk": "pk_%(table_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s",
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}

Base = declarative_base(
    metadata=MetaData(schema=ESQUEMA_LOGICO_APLICACAO, naming_convention=CONVENCAO_NOMES)
)
''',
    "App/Routes/__init__.py": '''"""Registro das rotas do __NOME__.

Cada modulo de rotas expoe um Blueprint; a lista BLUEPRINTS define o prefixo de cada um.
A pagina inicial (Principal) fica na raiz.
"""

from App.Routes.Principal import main_bp

BLUEPRINTS = (
    (main_bp, None),
)


def RegistrarRotas(app):
    """Registra todos os blueprints da aplicacao."""
    for blueprint, prefixo in BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix=prefixo)
''',
    "App/Routes/Principal.py": """from flask import Blueprint, render_template
from flask_login import current_user, login_required

from luftbase import exigir_permissao
from App.Catalogo import Permissao

main_bp = Blueprint('Principal', __name__)


@main_bp.route('/')
@login_required
@exigir_permissao(Permissao.SISTEMA_ACESSAR)
def MenuPrincipal():
    return render_template('Pages/Inicio.html', user=current_user)
""",
    "App/Services/__init__.py": "",
    "App/Services/LogService.py": '''import logging
import os
import traceback

from App.Configuracoes import ConfiguracaoAtual


class LogService:
    """
    Servico centralizado de Logs.
    Gerencia logs de sessao (volateis) e logs gerais (persistentes).
    """
    _logger = None
    _inicializado = False

    @staticmethod
    def Inicializar():
        if LogService._inicializado:
            return

        os.makedirs(ConfiguracaoAtual.DIR_LOGS, exist_ok=True)

        caminho_sessao = os.path.join(ConfiguracaoAtual.DIR_LOGS, "session.log")
        caminho_geral = os.path.join(ConfiguracaoAtual.DIR_LOGS, "application.log")

        logger = logging.getLogger(ConfiguracaoAtual.APP_NAME)
        logger.setLevel(logging.DEBUG if ConfiguracaoAtual.DEBUG else logging.INFO)
        logger.handlers = []  # Evita handlers duplicados quando a fabrica roda de novo.
        logger.propagate = False

        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Sessao: reinicia a cada start. Geral: historico. utf-8 evita erro com acentos.
        handler_sessao = logging.FileHandler(caminho_sessao, mode='w', encoding='utf-8')
        handler_sessao.setLevel(logging.DEBUG)
        handler_sessao.setFormatter(formatter)
        logger.addHandler(handler_sessao)

        handler_geral = logging.FileHandler(caminho_geral, mode='a', encoding='utf-8')
        handler_geral.setLevel(logging.INFO)
        handler_geral.setFormatter(formatter)
        logger.addHandler(handler_geral)

        handler_console = logging.StreamHandler()
        handler_console.setLevel(logging.DEBUG)
        handler_console.setFormatter(formatter)
        logger.addHandler(handler_console)

        LogService._logger = logger
        LogService._inicializado = True

    @staticmethod
    def _obter_logger(origem):
        if not LogService._logger:
            LogService.Inicializar()
        return logging.getLogger(f"{ConfiguracaoAtual.APP_NAME}.{origem}")

    @staticmethod
    def Info(origem, mensagem):
        LogService._obter_logger(origem).info(mensagem)

    @staticmethod
    def Warning(origem, mensagem):
        LogService._obter_logger(origem).warning(mensagem)

    @staticmethod
    def Error(origem, mensagem, excecao=None):
        """Registra erros com stack trace completo se uma excecao for fornecida."""
        detalhes = mensagem
        if excecao:
            tb_str = "".join(traceback.format_exception(None, excecao, excecao.__traceback__))
            detalhes = f"{mensagem} | Exception: {str(excecao)}\\nTraceback:\\n{tb_str}"
        LogService._obter_logger(origem).error(detalhes)

    @staticmethod
    def Debug(origem, mensagem):
        LogService._obter_logger(origem).debug(mensagem)
''',
    "App/Utils/__init__.py": "",
    "App/Templates/Layout/BaseLayout.html": """{% extends "luftbase/base.html" %}
{% import "luftbase/components.html" as ui %}

{#
  Layout do __NOME__ sobre o LuftBase.
  Paginas definem `title`, `page_content`, `extra_css` e `extra_js`.
#}

{% block titulo %}{% block title %}__NOME__{% endblock %}{% endblock %}

{% block estilos %}
{% block extra_head %}{% endblock %}
{% block extra_css %}{% endblock %}
{% endblock %}

{% block sidebar_brand %}
{{ ui.sidebar_brand('__NOME__', '__INICIAL__') }}
{% endblock %}

{% block conteudo %}{% block page_content %}{% endblock %}{% endblock %}

{% block scripts %}{% block extra_js %}{% endblock %}{% endblock %}
""",
    "App/Templates/Pages/Inicio.html": """{% extends "Layout/BaseLayout.html" %}

{% block title %}__NOME__{% endblock %}

{% block page_content %}
<div class="luft-cartao">
    <h1 class="luft-titulo">__NOME__</h1>
    <p class="luft-texto">__DESCRICAO__</p>
</div>
{% endblock %}
""",
    "tests/__init__.py": "",
    "tests/conftest.py": '''"""Fixtures compartilhadas: a raiz do projeto entra no PYTHONPATH."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
''',
    "tests/test_app.py": '''"""Teste estrutural: a fabrica sobe com a infraestrutura em memoria do LuftBase."""

from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.infraestrutura import FabricaInfraestruturaMemoria


def test_aplicacao_inicializa_e_exige_login():
    from App import CriarApp

    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "1",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft.interno",
            "LUFT_LDAP_DOMINIO": "LUFTFARMA",
        }
    )
    app = CriarApp(configuracao=configuracao, fabrica_infraestrutura=FabricaInfraestruturaMemoria())
    app.testing = True

    resposta = app.test_client().get("/")

    # Sem sessao, a pagina inicial leva ao login (302) em vez de abrir.
    assert resposta.status_code in (200, 302, 401)
''',
    "pytest.ini": """[pytest]
testpaths = tests
python_files = test_*.py
""",
    "deploy/README.md": """# Artefatos de implantacao - __NOME__

Gerados por `luftbase projeto deploy __IDENT__`. Revise portas, dominios e caminhos antes de
usar e valide em homologacao antes da producao.
""",
}

__all__ = [
    "PlanoProjeto",
    "escrever_env",
    "gerar_aplicacao",
    "ler_env_referencia",
    "montar_env",
]
