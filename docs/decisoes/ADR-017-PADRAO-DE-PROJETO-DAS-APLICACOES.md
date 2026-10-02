# ADR-017 - Padrao de projeto das aplicacoes Luft

Status: aceita (0.1.0a42)

## Contexto

Luft-Workspace e Luft-ConnectAir comecaram com estruturas, nomes e pontos de entrada
diferentes. Cada novo sistema (Control, Integrador...) repetiria a divergencia, e correcoes de
plataforma (servidor, contexto do painel, conexoes) teriam de ser copiadas a mao.

## Decisao

Todo sistema Luft tem a mesma estrutura, os mesmos arquivos-base e a mesma ordem dentro deles.
O que e comum vem primeiro; o que e particular do sistema fica no fim do arquivo, sob o bloco
`Particularidades do <sistema>`. O que e de plataforma mora no LuftBase, nao nos sistemas.

```text
<Sistema>/
|-- App/                       pacote da aplicacao
|   |-- __init__.py            fabrica CriarApp() + contexto global; particularidades no fim
|   |-- _version.py            __version__ (fonte unica da versao)
|   |-- Catalogo.py            Permissao, CATALOGO, PARAMETROS, PERMISSOES_MENU
|   |-- Buscas.py              BUSCAS: provedores da busca global da barra superior
|   |-- Conexoes.py            Inicializar, ObterBancoCore, ObterSessaoPostgres, TabelaPostgres...
|   |-- Configuracoes.py       ConfiguracaoAtual (diretorios e parametros locais)
|   |-- Models/POSTGRES/       Base.py + um arquivo por dominio (schema proprio)
|   |-- Routes/                __init__.py (BLUEPRINTS + RegistrarRotas) e um Blueprint por dominio
|   |-- Services/              regras de negocio (LogService.py e <Dominio>Service.py)
|   |-- Static/                CSS/, JS/, Img/ ...
|   |-- Templates/             Layout/BaseLayout.html, Pages/ ...
|   `-- Utils/                 helpers genericos
|-- App.py                     entrada de DESENVOLVIMENTO (executar_desenvolvimento)
|-- Wsgi.py                    entrada de PRODUCAO (executar -> Waitress)
|-- Data/  Logs/  SQL/  Docs/  scripts/  tests/  _DEV/   fora do pacote
`-- requirements.txt           LuftBase em vendor/
```

### Ordem de `App/__init__.py`

1. docstring; 2. imports (flask, luftbase, `App.*` em ordem alfabetica);
3. `CriarApp`: `LogService.Inicializar` -> Flask -> `PlataformaLuft(...)` -> `Conexoes.Inicializar`
   -> `RegistrarRotas` -> contexto global -> particularidades;
4. `_RegistrarContextoGlobal` (layout, `contexto_painel()`, `SidebarPermissoes`);
5. `Particularidades`: `_ContextoParticular(estado)` e `_RegistrarParticularidades(app, estado)`.

### Nomes fixos (todos os sistemas)

- `App.CriarApp(configuracao=None, fabrica_infraestrutura=None)`
- `Catalogo.Permissao`, `CATALOGO` (ou `None`), `PARAMETROS` (ou `()`), `PERMISSOES_MENU` (ou `{}`)
- `Buscas.BUSCAS` (ou `()`): `ProvedorBusca` registrados no `PlataformaLuft(buscas=...)`
- `Conexoes.Inicializar/ObterBancoCore/ObterEnginePostgres/ObterSessaoPostgres/EsquemaPostgres/TabelaPostgres`
- `Routes.BLUEPRINTS` e `Routes.RegistrarRotas(app)`; pagina inicial em `Routes/Principal.py`
- `Configuracoes.ConfiguracaoAtual` e `NOME_APLICACAO`

### Esqueleto do `.env` (e do `.env.example`)

Mesma ordem em todos os sistemas: Identidade (`LUFT_SISTEMA_ID`, `LUFT_AMBIENTE`,
`LUFT_APLICACAO_VERSAO` vazia, pois a versao vem de `App/_version.py`), Vault, LDAP, Sessao (SSO),
Autorizacao (opcional, comentada), Processo HTTP (`HOST`, `PORT`, `ROUTE_PREFIX`) e, por ultimo,
`Particularidades do <sistema>` (ex.: ERP e link publico no ConnectAir; servicos do Windows no
Workspace).

### O que e plataforma (LuftBase)

- `luftbase.servidor.executar/executar_desenvolvimento` e `luftbase servir`: Waitress, console,
  banner e recarga iguais em todos.
- `luftbase.contexto_painel()`: `pode_ver_*` do Painel de Controle.
- Autenticacao, permissoes, auditoria, notificacoes, e-mail, temas, sessoes.

## Consequencias

- Um sistema novo copia a estrutura e preenche so as particularidades.
- Mudancas de plataforma chegam a todos por nova versao do LuftBase, sem copiar codigo.
- Os blocos de particularidades concentram as diferencas reais (ex.: o ERP somente leitura do
  ConnectAir em `Conexoes.py`), o que torna a comparacao entre sistemas direta.

## Pendente

- `luftbase projeto criar` ainda gera o esqueleto antigo (`src/<pacote>`); deve passar a gerar
  esta estrutura.
