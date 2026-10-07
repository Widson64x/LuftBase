# Guia da aplicacao satelite

Uma **aplicacao satelite** e um sistema Luft (ConnectAir, Integrador, Control...) que usa o LuftBase como plataforma e cuida
**so das regras de negocio dele**. Este guia mostra o que o LuftBase entrega, o que a aplicacao declara e como colocar uma nova
no ar. A estrutura de pastas e a ordem dos arquivos estao no [ADR-017](decisoes/ADR-017-PADRAO-DE-PROJETO-DAS-APLICACOES.md).

## O que o LuftBase entrega e o que e da aplicacao

| LuftBase (nao reescreva) | Aplicacao (o que voce escreve) |
|---|---|
| Login LDAP, SSO, sessoes, cookie | Rotas e telas de negocio |
| Permissoes (arvore, cache, decorators) | `Catalogo.py`: a arvore de permissoes do sistema |
| Auditoria (acesso, evento, antes/depois) | Chamadas `Auditar(...)` nas acoes de negocio |
| Painel de Controle, perfil, notificacoes, comunicados | `ParametroAplicacao`: cartoes de parametros proprios |
| Temas, layout base, componentes | `Templates/Layout/BaseLayout.html` e CSS proprio |
| Servidor (Waitress), fuso, proxy, health | `App.py` e `Wsgi.py` de poucas linhas |
| Conexoes via Vault (core, aplicacao, diretorio) | Modelos do schema proprio e consultas ao ERP/SILT |
| E-mail (SMTP) com modo teste e auditoria | O conteudo e o gatilho do e-mail |

## Anatomia minima

```text
App.py            executar_desenvolvimento("App:CriarApp")
Wsgi.py           executar("App:CriarApp")
App/__init__.py   CriarApp()  ->  PlataformaLuft(catalogo=CATALOGO, parametros=PARAMETROS, modelos=..., buscas=BUSCAS)
App/Catalogo.py   Permissao (StrEnum), CATALOGO, PARAMETROS, PERMISSOES_MENU
App/Conexoes.py   sessoes do PostgreSQL da aplicacao e (se existir) do ERP, somente leitura
```

`CriarApp()` faz, nesta ordem: logs -> Flask -> `PlataformaLuft(...).inicializar(app)` -> `Conexoes.Inicializar(estado)` ->
rotas -> contexto global (layout, `contexto_painel()`, permissoes do menu) -> particularidades.

### O que `inicializar()` faz por baixo

1. Poe o processo no fuso de Brasilia.
2. Le a configuracao (`.env`) e resolve os caminhos do Vault pelo `LUFT_AMBIENTE` e `LUFT_SISTEMA_ID`.
3. Cria as fronteiras de banco (diretorio, core, aplicacao) com as credenciais do Vault; le nome e icone do sistema em
   `core.tb_sistema`.
4. Monta autenticacao, autorizacao, notificacoes, publicacoes, temas, auditoria, metricas e e-mail.
5. Instala identidade (sessao compartilhada, Flask-Login, CSRF), os blueprints do LuftBase e o contexto Jinja.
6. **Sincroniza o catalogo**: confere a arvore declarada em `Catalogo.py` com o core e cria o que faltar (aditivo; nunca
   remove nem altera concessoes). Se existir uma permissao provisoria com a mesma funcao, adota a real.
7. Confere (sem DDL) as tabelas dos modelos declarados e avisa no log as que faltarem.

## Permissoes (`Catalogo.py`)

Chaves seguem `MODULO.RECURSO.ACAO` ([doc 11](11-AUTORIZACAO.md)). Regras praticas:

- Cada modulo tem um no `MODULO.MODULO.GERENCIAR`; a raiz `SISTEMA.SISTEMA.ADMINISTRAR` concede o sistema inteiro. Conceder um
  no concede os filhos.
- `SISTEMA.SISTEMA.ACESSAR` (`acesso_sistema=True`) e o que abre a porta do sistema para a pessoa.
- Marque `sensivel=True` em acoes de risco (excluir, importar, editar parametros).
- Use `Permissao.X` nas rotas: `@exigir_permissao(Permissao.X)` (uma) ou `@exigir_alguma_permissao((A, B))` (qualquer). Nos
  templates, `SidebarPermissoes` (montado por `consultar_permissoes(PERMISSOES_MENU.values())`) decide o que o menu mostra.
- **Nunca** conceda por codigo: quem concede e a equipe de seguranca no Painel de Controle (ou "Copiar permissoes").

## Respostas e auditoria

- JSON: `resposta_api_sucesso` / `resposta_api_erro` (ou os envelopes proprios do sistema, como `Sucesso`/`Erro` do
  Integrador), sempre com `status` e `message`.
- Mensagens para a pessoa: `mensagem_sucesso`, `mensagem_erro` (viram toasts) e `enfileirar_toast`.
- Acoes de negocio: `registrar_evento_auditoria(acao, recurso, descricao, ...)` e `registrar_alteracao_auditoria(...)`
  (com antes/depois). **Nunca** coloque senha, token ou valor sensivel nos dados; o LuftBase sanitiza, mas nao confie nisso.
- Rotas que nao devem gerar log de acesso (polling): `@sem_log`.
- Erros 500 sao registrados so com **tipos e linhas da pilha**, nunca a mensagem nem valores.
- Toda mutacao via fetch envia `X-CSRF-Token` (`<meta name="luft-csrf-token">`).

## Bancos

- **Core** (`ObterBancoCore`): usuarios, sessoes, permissoes, auditoria. A aplicacao le e usa; nao cria tabelas ali.
- **Aplicacao** (`ObterSessaoPostgres`): schema proprio (`connectair`, `integrador`...). A role do sistema so enxerga o proprio
  schema e os objetos operacionais do core. Em homologacao o schema e a role tem sufixo `_hml` (`luft_<schema>_hml_app`).
- **ERP/TMS (SQL Server) e SILT (Oracle)**: bancos de negocio **somente leitura**. Cada aplicacao protege a engine com um evento do
  SQLAlchemy que **recusa** qualquer instrucao que nao seja `SELECT`/`WITH` (ConnectAir: `EscritaNoErpRecusada`; Integrador:
  `EscritaEmBancoDeNegocioRecusada`).
- `TabelaPostgres('tb_nome')` devolve o nome qualificado com o schema certo do ambiente.

## Busca global e parametros

- `Buscas.BUSCAS`: `ProvedorBusca` que alimentam a barra superior (Ctrl K).
- `Catalogo.PARAMETROS`: `ParametroAplicacao(titulo, descricao, endpoint, icone, permissao)` vira um cartao em Painel de
  Controle > Configuracoes Gerais, visivel so a quem tem a permissao.

## Colocar uma aplicacao nova no ar (roteiro)

1. **Estrutura**: copie a de um sistema existente (ADR-017) e troque nomes, `LUFT_SISTEMA_ID` e prefixo.
2. **Cadastro**: no **Luft-Workspace**, crie o sistema (Painel de Controle > Aplicacoes & Ambiente > Sistemas) com o **nome
   exato** que sera o do servico (`Luft-<Nome>`) — o nome e a chave para achar o servico no servidor. O Workspace
   provisiona schema e role e registra o id.
3. **Vault e banco**: `luftbase vault postgresql provisionar --manifesto <arquivo.json>` cria os segredos e a senha da role
   (pede confirmacao digitada; use `--help` em cada comando). Ha comandos para auditar, migrar o layout, clonar um ambiente e
   reprovisionar um sistema (`reprovisionar-sistema`).
4. **`.env`** na pasta do servico: `LUFT_AMBIENTE`, `LUFT_SISTEMA_ID`, Vault, LDAP, sessao (cookie igual aos outros),
   `HOST`/`PORT`/`ROUTE_PREFIX`. Esqueleto: o `.env.example` do repositorio.
5. **Permissoes**: suba a aplicacao uma vez; o catalogo e criado sozinho. Depois conceda no Painel de Controle.
6. **nginx**: um `location /Luft-<Nome>/` para a porta da aplicacao, com `X-Forwarded-For` e `X-Forwarded-Proto`
   ([doc 17](17-SERVIDOR-REDE-E-FUSO.md)).
7. **Servico**: Windows (NSSM, nome = nome do sistema) ou Linux (`luft-<nome>.service`).
8. **Deploy automatico**: copie `.github/workflows/deploy.yml` e `scripts/DeployMirror.py` de um sistema irmao e troque so os
   nomes ([doc 20](20-OPERACAO-E-DEPLOY.md)).
9. **Dependencia**: `luft-base @ git+https://github.com/Widson64x/LuftBase.git@v<versao>` no `requirements.txt`.

## Armadilhas conhecidas

- **Prefixo**: use `url_for` e `request.script_root`; link ou `action` fixo quebra sob `/Luft-<Nome>/`.
- **Datas**: use `luftbase.nucleo.tempo.agora_local()`; `datetime.now()` depende do fuso da maquina.
- **IP e navegador**: leia `request.remote_addr` e o cabecalho `User-Agent` (nao `bool(request.user_agent)`).
- **Sessao `session.clear()`** apaga a ordem de limpar o cookie "lembrar": use `encerrar_sessao_global()`.
- **Escrever no ERP**: nao funciona e nao deve: grave no PostgreSQL da aplicacao.
