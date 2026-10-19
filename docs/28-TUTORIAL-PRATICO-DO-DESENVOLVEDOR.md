# Tutorial pratico do desenvolvedor

Aprenda fazendo: do zero a uma funcionalidade completa (tela, API, permissao, tabela, teste e deploy) e, no fim, como **migrar um sistema legado**
para o LuftBase. Todo o codigo da parte 1 foi **executado**: e um sistema de exemplo ("Luft-Avisos", um quadro de avisos) cujos testes passam.

> Este e o guia **usual** (aprende-se fazendo). A **referencia tecnica** esta nos documentos 01 a 27; o [indice](README.md) mostra os dois caminhos.
> Se so quer o caminho mais curto ate um sistema novo, veja antes o [guia rapido](22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md).

## Parte 0 - O modelo mental (3 minutos)

O LuftBase resolve, **uma vez**, o que todo sistema Luft precisa: segredos (Vault), bancos, login corporativo (LDAP), sessao compartilhada (SSO),
permissoes, auditoria, notificacoes, temas, e-mail e o Painel de Controle. Seu sistema escreve so **rotas e regras de negocio**.

| Voce escreve | O LuftBase entrega |
|---|---|
| `App/Catalogo.py`: modulos e permissoes | confere/cria no `core` a cada inicializacao; o Painel de Controle concede |
| `App/Models/POSTGRES/*.py`: tabelas do seu schema | engine, sessao, traducao do schema, conferencia das tabelas na subida |
| `App/Routes/*.py` + `Templates/` | login, `current_user`, layout, menu, tema, notificacoes, busca, perfil |
| `App/Services/*.py`: regras | auditoria, mensagens padrao, e-mail |

Tres regras que explicam quase tudo:

1. **O `.env` e minimo**: identidade (`LUFT_SISTEMA_ID`), ambiente e o token do Vault. Bancos, LDAP e e-mail vem do Vault ([doc 04](04-CONFIGURACAO-E-VAULT.md)).
2. **O schema do seu sistema nunca e fixo no codigo**: os models usam o schema logico `luft_aplicacao`, que o LuftBase troca pelo real (`avisos`, `docs`, `control`...).
3. **Permissao e dado, nao codigo**: voce *declara* o catalogo; quem *concede* e o administrador, no Painel de Controle.

## Parte 1 - Sua primeira funcionalidade (Luft-Avisos)

### 1.1 Criar o projeto

Para aprender, gere so os arquivos (sem tocar em banco nem Vault):

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e "C:\Projetos\LUFT\Python\LuftBase"          # ou: pip install -r requirements.txt, depois de criar o projeto
python -m luftbase projeto criar Luft-Avisos --sistema-id 9 --schema avisos --porta 9020 --destino C:\Projetos\LUFT\Python\Luft-Avisos
```

Para um sistema **de verdade** (cadastra o sistema no core, cria schema, role e segredo no Vault e escreve o `.env` com o ID gerado), use
`python -m luftbase projeto novo Luft-Avisos` ([doc 23](23-REFERENCIA-DA-CLI.md#projeto), [doc 24](24-SISTEMAS-E-CATALOGO.md)).

### 1.2 O que foi gerado (e onde voce mexe)

```text
App.py / Wsgi.py        entradas: desenvolvimento (python App.py) e producao (Waitress). Nao mexa.
App/__init__.py         CriarApp(): ordem fixa (log -> Flask -> LuftBase -> conexoes -> rotas -> contexto). Particularidades no fim.
App/Catalogo.py         <- voce declara permissoes aqui
App/Models/POSTGRES/    <- voce declara tabelas aqui (um arquivo por assunto)
App/Routes/             <- um Blueprint por tela/assunto; registre em Routes/__init__.py
App/Services/           <- regras de negocio (a rota so recebe e responde)
App/Templates/          <- Layout/BaseLayout.html ja estende o layout do LuftBase
App/Conexoes.py         ObterSessaoPostgres(), Tabelas.tb_x, ObterBancoCore()
.env.example            esqueleto padrao (copie para .env)
tests/                  um teste estrutural pronto
```

O padrao completo e as regras de ordem estao no [ADR-017](decisoes/ADR-017-PADRAO-DE-PROJETO-DAS-APLICACOES.md).

### 1.3 Declarar as permissoes (`App/Catalogo.py`)

A chave segue **`MODULO.RECURSO.ACAO`** (maiusculas, tres partes). **Conceder um no concede os filhos**: por isso cada modulo tem um no
`MODULO.MODULO.GERENCIAR` e a raiz `LUFT_AVISOS.SISTEMA.ADMINISTRAR` concede o sistema inteiro.

```python
from enum import StrEnum

from luftbase import CatalogoAplicacao, DefinicaoModulo, PermissaoAplicacao


class Permissao(StrEnum):
    SISTEMA_ADMINISTRAR = "LUFT_AVISOS.SISTEMA.ADMINISTRAR"
    SISTEMA_ACESSAR = "LUFT_AVISOS.SISTEMA.ACESSAR"
    AVISOS_GERENCIAR = "AVISOS.MODULO.GERENCIAR"
    AVISOS_VISUALIZAR = "AVISOS.AVISOS.VISUALIZAR"
    AVISOS_CRIAR = "AVISOS.AVISOS.CRIAR"


P = Permissao
_RAIZ = P.SISTEMA_ADMINISTRAR


def _no(chave, descricao, pai=_RAIZ, *, sensivel=False, acesso=False, ordem=0):
    return PermissaoAplicacao(
        chave=chave.value, descricao=descricao, pai=pai.value if pai else None,
        sensivel=sensivel, acesso_sistema=acesso, ordem=ordem,
        modulo_codigo="PLATAFORMA" if chave.value.startswith("LUFT_AVISOS.") else None,
    )


CATALOGO = CatalogoAplicacao(
    modulos=(
        DefinicaoModulo("PLATAFORMA", "Plataforma", "Acesso e administracao.", "ph-cube", 0),
        DefinicaoModulo("AVISOS", "Avisos", "Quadro de avisos da equipe.", "ph-megaphone", 10),
    ),
    permissoes=(
        _no(P.SISTEMA_ADMINISTRAR, "Administrar todo o Luft-Avisos.", pai=None, sensivel=True),   # a raiz nao tem pai
        _no(P.SISTEMA_ACESSAR, "Acessar o Luft-Avisos.", acesso=True, ordem=1),                    # a "porta" do sistema
        _no(P.AVISOS_GERENCIAR, "Gerenciar todo o quadro de avisos.", ordem=10),
        _no(P.AVISOS_VISUALIZAR, "Ver os avisos.", P.AVISOS_GERENCIAR, ordem=1),
        _no(P.AVISOS_CRIAR, "Publicar avisos.", P.AVISOS_GERENCIAR, ordem=2),
    ),
)
PARAMETROS = ()                                                   # cartoes de "Configuracoes Gerais" (opcional)
PERMISSOES_MENU = {"avisos": Permissao.AVISOS_VISUALIZAR}         # o menu consulta tudo numa unica ida ao banco
```

Pontos que costumam dar problema:

- **A ACAO (ultimo trecho) precisa existir na lista do core.** Valores aceitos (`AcaoPermissao`): `ACESSAR`, `ADMINISTRAR`, `APROVAR`, `ARQUIVAR`,
  `ATIVAR`, `BAIXAR`, `CANCELAR`, `CONCEDER`, `CONFIGURAR`, `CRIAR`, `DESATIVAR`, `EDITAR`, `ENVIAR`, `EXECUTAR`, `EXCLUIR`, `EXPORTAR`, `GERENCIAR`,
  `IGNORAR`, `IMPORTAR`, `IMPRIMIR`, `LISTAR`, `PROCESSAR`, `PUBLICAR`, `REJEITAR`, `REPROCESSAR`, `REVOGAR`, `SINCRONIZAR`, `VISUALIZAR`. Uma acao inventada
  (`VERSIONAR`, `UTILIZAR`...) **derruba a subida** com `A acao 'X' de '...' nao e aceita pelo core`. Escolha a mais proxima (`SINCRONIZAR` para
  "versionar/restaurar", `EXECUTAR` para "usar um assistente").
- A permissao de acesso (`acesso=True`) e a que **faz o sistema aparecer no Hub** e a unica que gera o aviso de "acesso liberado" ([doc 13](13-NOTIFICACOES-E-PUBLICACOES.md)).
- O pai tem de ser declarado **antes** do filho na tupla.
- Valide sem subir nada: `CATALOGO.validar()` (veja o teste, 1.8).

### 1.4 Declarar a tabela (`App/Models/POSTGRES/Avisos.py`)

```python
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from App.Models.POSTGRES.Base import Base


class Aviso(Base):
    __tablename__ = "tb_aviso"          # padrao: tb_ + minusculas

    Id = Column(Integer, primary_key=True)
    Titulo = Column(String(120), nullable=False)
    Texto = Column(Text, nullable=False)
    Autor = Column(String(100), nullable=False)
    CriadoEm = Column(DateTime, nullable=False, default=datetime.now)
```

- **O LuftBase nao cria tabela sozinho** (politica `validar`): na subida ele *confere* e registra `Tabela ausente: ...` no log. Crie a estrutura
  por DDL do seu `SQL/` ou, para dados vindos de um sistema antigo, por um script de migracao (Parte 2).
- Chave estrangeira e `secondary` precisam do **schema logico**: `ForeignKey("luft_aplicacao.tb_modulos.Id")`. Sem o prefixo, o SQLAlchemy nao resolve.
- SQL cru? Use `Tabelas.tb_aviso` (de `App.Conexoes`), nunca o nome do schema escrito no texto.

### 1.5 A tela e a API (`App/Routes/Avisos.py`)

```python
from flask import Blueprint, render_template, request
from flask_login import current_user, login_required
from luftbase import (
    SeveridadeAuditoria, exigir_ajax, exigir_permissao, registrar_evento_auditoria,
    resposta_api_erro, resposta_api_sucesso,
)
from luftbase.interface.web import validar_csrf_requisicao

from App.Catalogo import Permissao
from App.Conexoes import ObterSessaoPostgres
from App.Models.POSTGRES.Avisos import Aviso

avisos_bp = Blueprint("Avisos", __name__)


@avisos_bp.get("/avisos")
@login_required
@exigir_permissao(Permissao.AVISOS_VISUALIZAR)          # 401, 403 ou 503; nunca concede em caso de falha
def Listar():
    sessao = ObterSessaoPostgres()                        # quem abre, fecha
    try:
        avisos = sessao.query(Aviso).order_by(Aviso.CriadoEm.desc()).limit(50).all()
        return render_template("Pages/Avisos.html", avisos=avisos)
    finally:
        sessao.close()


@avisos_bp.post("/avisos/api/criar")
@login_required
@exigir_permissao(Permissao.AVISOS_CRIAR)
@exigir_ajax                                              # aberta direto no navegador: 404
def Criar():
    validar_csrf_requisicao()                             # ATENCAO: o CSRF NAO e automatico nas rotas da aplicacao
    dados = request.get_json(silent=True) or {}
    titulo, texto = str(dados.get("titulo") or "").strip(), str(dados.get("texto") or "").strip()
    if not titulo or not texto:
        return resposta_api_erro("Informe o titulo e o texto.", status_http=400)

    sessao = ObterSessaoPostgres()
    try:
        aviso = Aviso(Titulo=titulo, Texto=texto, Autor=current_user.login)
        sessao.add(aviso)
        sessao.commit()
        registrar_evento_auditoria(
            acao="AVISO_CRIADO", recurso="AVISOS", descricao=f"Aviso '{titulo}' publicado.",
            dados_novos={"id": aviso.Id}, severidade=SeveridadeAuditoria.BAIXA,
        )
        return resposta_api_sucesso({"id": aviso.Id}, "Aviso publicado.", 201)
    except Exception:
        sessao.rollback()
        return resposta_api_erro("Nao foi possivel publicar o aviso.", status_http=500)   # o detalhe vai para o log, nunca ao navegador
    finally:
        sessao.close()
```

Registre o blueprint em `App/Routes/__init__.py` (`BLUEPRINTS = ((main_bp, None), (avisos_bp, None))`).

O que cada peca faz:

| Peca | Funcao |
|---|---|
| `@login_required` | sem sessao, vai para o login do ecossistema |
| `@exigir_permissao(...)` | confere a permissao (com heranca e cache); falha do banco **nega**, nunca concede |
| `@exigir_ajax` | exige `X-Requested-With: XMLHttpRequest` ou corpo JSON; senao 404 (a API nao vira "pagina") |
| `validar_csrf_requisicao()` | confere `X-CSRF-Token` (ou o campo `csrf_token`) contra o token da sessao; 403 se faltar |
| `resposta_api_sucesso/erro` | envelope padrao `{status, message, data}` |
| `registrar_evento_auditoria` | grava o evento (quem, o que, antes/depois) no painel de Auditoria |
| `current_user` | o usuario logado: `login`, `nome_completo`, `email`, `id_usuario`, `id_grupo`, `nome_grupo`... |

> **CSRF**: as rotas do **proprio LuftBase** (login, painel...) validam sozinhas; as da **sua** aplicacao nao. Valide em cada rota que grava ou num
> `before_request` para todas as escritas do seu sistema (como faz o Luft-Docs). Nos formularios HTML use
> `<input type="hidden" name="csrf_token" value="{{ luft_csrf_token }}">`; no `fetch`, envie o cabecalho a partir da meta do layout.

### 1.6 O template e o `fetch`

```jinja
{% extends "Layout/BaseLayout.html" %}
{% block title %}Avisos{% endblock %}

{% block page_content %}
<h1>Quadro de avisos</h1>
{% for aviso in avisos %}
  <article class="luft-cartao"><h3>{{ aviso.Titulo }}</h3><p>{{ aviso.Texto }}</p>
  <small>{{ aviso.Autor }} - {{ aviso.CriadoEm.strftime('%d/%m/%Y %H:%M') }}</small></article>
{% else %}
  <p>Nenhum aviso publicado.</p>
{% endfor %}
{% endblock %}
```

```javascript
const token = document.querySelector('meta[name="luft-csrf-token"]')?.content || '';
const r = await fetch('/Luft-Avisos/avisos/api/criar', {          // com o ROUTE_PREFIX; em producao use request.script_root
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token, 'X-Requested-With': 'XMLHttpRequest' },
  body: JSON.stringify({ titulo, texto }),
});
const resposta = await r.json();   // { status: 'success' | 'error', message, data }
```

O `Layout/BaseLayout.html` do seu projeto estende `luftbase/base.html`. Os **blocos** que voce pode sobrescrever: `title` (ou `titulo`), `extra_head`/`estilos`,
`sidebar_brand`, `sidebar_menu`, `sidebar_actions`, `breadcrumb`, `topbar_actions`, `content`/`conteudo`, `extra_modals` e `extra_scripts`/`scripts`. Os
componentes ficam em `{% import "luftbase/components.html" as ui %}` (`ui.nav_item`, `ui.modal`, `ui.card`, `ui.btn`, `ui.empty_state`...). No menu, use as
permissoes de `PERMISSOES_MENU` (variavel `SidebarPermissoes` nos templates) para esconder o que a pessoa nao pode usar ([doc 07](07-DESIGN-SYSTEM-E-TEMAS.md)).

Mensagens ao usuario sem escrever HTML: `mensagem_sucesso(...)`, `mensagem_erro(...)` (toasts do LuftBase, [doc 12](12-AUDITORIA-E-OBSERVABILIDADE.md)).

### 1.7 Rodar

```powershell
Copy-Item .env.example .env         # preencha LUFT_SISTEMA_ID (o do cadastro), LUFT_AMBIENTE, LUFT_VAULT_TOKEN, LUFT_TOKEN_ACESSO
python App.py                       # http://127.0.0.1:<PORT>/
```

Na subida, leia o log: `Catalogo do sistema N sincronizado (...)` (a primeira vez cria as permissoes), `Tabela ausente ...` (falta criar a tabela),
`Luft-Avisos v... | sistema N | ambiente ...`. Depois, no **Painel de Controle > Seguranca & Permissoes**, conceda `AVISOS.AVISOS.VISUALIZAR` ao seu usuario
(ou `LUFT_AVISOS.SISTEMA.ADMINISTRAR`, que concede tudo). Mudou o catalogo? Reinicie: ele e sincronizado a cada subida.

### 1.8 Testar sem Vault, sem banco real

O LuftBase fornece uma infraestrutura **em memoria** (`FabricaInfraestruturaMemoria`). O padrao de teste do Luft-Avisos:

```python
@pytest.fixture()
def app(monkeypatch):
    from App import CriarApp
    configuracao = ConfiguracaoLuftBase.de_mapeamento({
        "LUFT_SISTEMA_ID": "9", "LUFT_AMBIENTE": "desenvolvimento", "LUFT_VAULT_ENDERECO": "http://vault:8200",
        "LUFT_LDAP_SERVIDOR": "ad.luft.interno", "LUFT_LDAP_DOMINIO": "LUFTFARMA",
    })
    aplicacao = CriarApp(configuracao=configuracao, fabrica_infraestrutura=FabricaInfraestruturaMemoria())
    aplicacao.testing = True
    # O schema logico `luft_aplicacao` vira "sem schema" no SQLite:
    engine = create_engine("sqlite://", execution_options={"schema_translate_map": {"luft_aplicacao": None}})
    Base.metadata.create_all(engine)
    sessoes = sessionmaker(bind=engine)
    monkeypatch.setattr("App.Routes.Avisos.ObterSessaoPostgres", lambda: sessoes())
    # Sem o core, auditoria e checagem de manutencao viram duples:
    aplicacao.auditadas = []
    monkeypatch.setattr("App.Routes.Avisos.registrar_evento_auditoria", lambda **kw: aplicacao.auditadas.append(kw))
    monkeypatch.setattr("luftbase.web.manutencao._sistema_em_manutencao", lambda _id: False)
    return aplicacao


def _entrar(app, monkeypatch, permitido=True):
    estado = app.extensions["luftbase"]
    monkeypatch.setattr(type(estado.autorizacao), "possui", lambda *_: permitido)
    monkeypatch.setattr(type(estado.autorizacao), "consultar", lambda _s, _u, chaves: {c: permitido for c in chaves})
    usuario = UsuarioAutenticado(10, "ana.silva", "Ana Silva", None, 7, "TI")
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id(); sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_csrf"] = "c" * 32
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}
    return cliente


def test_catalogo_e_aceito_pelo_core():
    CATALOGO.validar()                      # pega acao invalida ANTES de subir no servidor

def test_api_exige_csrf(app, monkeypatch):
    cliente = _entrar(app, monkeypatch)
    resposta = cliente.post("/avisos/api/criar", json={"titulo": "x", "texto": "y"}, headers={"X-Requested-With": "XMLHttpRequest"})
    assert resposta.status_code == 403
```

Os testes do exemplo cobrem: sem login vai ao login; lista vazia e criacao pela API (201, com auditoria); acesso direto sem AJAX (404); CSRF ausente (403); catalogo valido.
Rode com `python -m pytest -q tests`.

### 1.9 Publicar

1. Commit na branch `homologacao` -> o GitHub Actions faz o deploy no servidor Linux ([doc 20](20-OPERACAO-E-DEPLOY.md)). O **servico precisa existir** antes
   (systemd `luft-avisos.service`), com o `.env` do ambiente.
2. Conferir: `GET /Luft-Avisos/_luftbase/saude`, o log de subida e o login.
3. Producao so por *merge* `homologacao` -> `main` (Windows, servico NSSM com o **nome do sistema**).

## Parte 2 - Migrando um sistema legado (roteiro e licoes do Luft-Docs)

O Luft-Docs (Flask + API FastAPI + LuftCore + SQL Server para permissoes) virou um sistema LuftBase de um unico projeto. O roteiro abaixo e o que funcionou
e as armadilhas que apareceram de verdade.

### 2.1 Ordem recomendada

| # | Passo | Como |
|---|---|---|
| 1 | **Esqueleto** | `luftbase projeto criar <Nome> --sistema-id <id> --schema <schema> --porta <p>` num diretorio de rascunho; copie `App.py`, `Wsgi.py`, `App/__init__.py`, `Conexoes.py`, `Configuracoes.py`, `Models/POSTGRES/Base.py`, `.env.example` |
| 2 | **Reorganizar o codigo** | tudo vai para `App/{Models,Routes,Services,Static,Templates,Utils}`; `from Services.X` vira `from App.Services.X` |
| 3 | **Eliminar login e API proprios** | o usuario vem de `current_user` (`login`, `id_usuario`...); apague telas de login, tokens de URL, API de usuarios e a tela de permissoes (e o Painel de Controle) |
| 4 | **Catalogo de permissoes** | desenhe `MODULO.RECURSO.ACAO`, valide **as acoes**, guarde o mapa `CHAVES_LEGADAS` (chave antiga -> nova) |
| 5 | **Tabelas e models** | renomeie para `tb_<nome>` minusculo, `Base` com schema logico, FKs com `luft_aplicacao.` |
| 6 | **Templates e JS** | `luftcore/...` -> `luftbase/...`; `LuftCore.abrirModal` -> `LuftBase.abrirModal`; remova `token` das URLs; ponha CSRF nos formularios e `fetch`; blocos novos do layout |
| 7 | **Testes de coerencia** | templates compilam, todo `url_for` aponta para endpoint existente, `CATALOGO.validar()`, nada de resquicio do sistema antigo |
| 8 | **Dados** | script de migracao do schema antigo (2.2) |
| 9 | **Permissoes de producao** | extrair -> gerar SQL -> simular -> aplicar (2.3) |
| 10 | **Conteudo em disco** | caminho em variavel de ambiente, permissao de escrita da conta do servico (2.4) |
| 11 | **Servico, `.env`, nginx, deploy** | 2.5 |

### 2.2 Migrar o banco: o padrao dos scripts `Migrar*Schema.py`

Os scripts `MigrarDreSchema.py` (Control) e `MigrarLuftdocsSchema.py` (Docs) seguem o mesmo desenho; copie um deles:

- **Diagnostico por padrao**: sem `--executar` so le e mostra, tabela a tabela, o que sera feito (contagens, colunas so na origem/so no model, conflitos no destino).
- **Origem somente leitura** (uma barreira recusa tudo que nao for `SELECT`); **destino pela role do proprio sistema** (dona do schema novo).
- **Uma transacao** para criar tabelas, copiar, acertar sequencias, criar chaves estrangeiras (**depois** da carga) e indices; qualquer falha desfaz tudo.
- **Confere a contagem** de cada tabela antes do commit; **nao sobrescreve** (so com `--substituir` e uma frase de confirmacao); `--executar --confirmar <FRASE>`.
- Regra de nomes explicita (`Tb_Docs_AvaliacoesDocumentos` -> `tb_avaliacoesdocumentos`); **as colunas mantem os nomes**.
- Ignora de proposito o que mudou de dono (tabelas de permissao antigas): permissao vive no `core`.

### 2.3 Migrar as permissoes

Permissao antiga e de **outro banco** (SQL Server) e de **outro modelo**. Faca em dois passos, homologacao primeiro:

```powershell
python scripts/ExtrairPermissoesProducao.py --sistema-id <id antigo>                      # so SELECT -> Data/Temp/permissoes_producao.json
python scripts/GerarSqlPermissoesProducao.py --sistema-id <id novo> --simular             # roda e DESFAZ; confira os relatorios
python scripts/GerarSqlPermissoesProducao.py --sistema-id <id novo> --executar --confirmar APLICAR_PERMISSOES
```

Licoes: (1) o **ID de usuario difere entre ambientes**: use `--casar-por-login` fora da producao; (2) o sistema precisa **ter subido uma vez** antes (as chaves novas so existem
depois da primeira sincronizacao do catalogo); (3) usuarios bloqueados e chaves sem equivalente ficam de fora e sao listados; (4) idempotente: so insere o que nao existe.

### 2.4 Conteudo que nao e banco

Documentos, imagens, planilhas e modelos de IA **nao vao para o Git nem para o espelho do deploy**: guarde-os numa pasta persistente apontada por variavel de ambiente
(`DOCS_DATA_ROOT` no Docs). Em cada ambiente: (a) defina a variavel **no `.env` do servidor** (vazio = pasta padrao dentro do projeto, que nao existe); (b) de **escrita** a
conta do servico (`icacls`/`chown`); (c) nao monte a pasta de producao em homologacao (o editor escreve nela); (d) lembre que o `DeployMirror` do Windows **apaga** tudo que nao
esta no repositorio, exceto as pastas preservadas. Faca o sistema **avisar no log** se a pasta nao existe.

### 2.5 Servico, `.env` e nginx

- **Servico antes do deploy**: systemd (Linux) ou NSSM (Windows). Sem ele o job falha no primeiro passo, sem alterar nada.
- **`.env`** a partir do `.env.example`, **com as mesmas variaveis de sessao e LDAP dos outros sistemas do ambiente** (senao o SSO nao funciona). No PowerShell 5, escreva
  sem BOM (`[IO.File]::WriteAllText(..., (New-Object Text.UTF8Encoding($false)))`). O app so le o `.env` na subida: reinicie o servico.
- **Porta**: a do `.env` precisa **bater com o upstream do nginx** do ambiente (veja o [mapa de portas, doc 20](20-OPERACAO-E-DEPLOY.md#mapa-de-portas-e-prefixos)).
- **nginx**: o prefixo (`ROUTE_PREFIX`) **diferencia maiusculas e minusculas** (`/Luft-Docs/` nao e `/luft-docs/`); repasse o caminho inteiro (sem barra no `proxy_pass`) quando o
  app publica no proprio prefixo; ponha `client_max_body_size` para uploads; mantenha o endereco antigo por redirecionamento (`rewrite ^/antigo/(.*)$ /Novo/$1 permanent;`).
  Com o servico fora do ar o nginx devolve 502 (e o `error_page` pode mostra-lo como 404).

### 2.6 Armadilhas reais (e como reconhecer)

| Sintoma | Causa | Correcao |
|---|---|---|
| Subida cai: `A acao 'VERSIONAR' de ... nao e aceita pelo core` | acao fora da lista do core | trocar por uma acao valida; teste com `CATALOGO.validar()` |
| Subida cai por e-mail do Vault | segredo `integracoes/email` sem `senha` (LuftBase anterior a 0.1.0a112) | atualizar o LuftBase; a partir da 0.1.0a112 vira aviso no log |
| Pagina abre mas a lista de itens vem vazia, console com 403 | falta a permissao nova de leitura (as chaves sao novas) | conceder no Painel de Controle |
| Cartoes sem o botao de leitura | pasta de conteudo nao encontrada | variavel de ambiente, reiniciar, permissao da conta |
| `Tabela ausente: ... luft_aplicacao.tb_...` | schema vazio | rodar a migracao |
| Escritas por `fetch` passam sem token | o LuftBase nao valida CSRF nas rotas da app | `validar_csrf_requisicao()` |
| `FK ... could not find table` ao subir | `ForeignKey("tb_x.Id")` sem o schema logico | `ForeignKey("luft_aplicacao.tb_x.Id")` |
| Links antigos com `?token=...` ou prefixo antigo no texto | conteudo gravado pelo sistema anterior | normalizar **na leitura** (filtro), sem reescrever o conteudo |
| Aviso "acesso liberado" nao saiu | so a permissao base muda "sem -> com acesso"; quem ja tinha acesso (ex.: pelo grupo) nao e avisado | conceder `...SISTEMA.ACESSAR` a quem nao tinha ([doc 13](13-NOTIFICACOES-E-PUBLICACOES.md)) |

Mais mensagens e o que fazer: [solucao de problemas](26-SOLUCAO-DE-PROBLEMAS.md). Glossario: [27](27-GLOSSARIO.md).

## Checklist de um sistema pronto

- [ ] `.env.example` completo; `.env` fora do Git
- [ ] `CATALOGO.validar()` no teste; permissoes concedidas em homologacao
- [ ] toda rota que grava: login + permissao + CSRF + auditoria; erro sem vazar detalhe
- [ ] SQL cru so com `Tabelas.tb_x`; sessoes fechadas
- [ ] testes passando sem Vault nem banco real
- [ ] servico criado; porta igual ao nginx; `GET /<prefixo>/_luftbase/saude` responde
- [ ] README e CHANGELOG atualizados; versao em `App/_version.py`
