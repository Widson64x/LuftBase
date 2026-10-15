# Glossario

Os termos que aparecem na documentacao e na CLI, em ordem alfabetica. Onde ha um documento com o assunto completo, o link esta no fim
da definicao.

**Aditivo** - que so acrescenta. Migracoes e scripts do LuftBase nao apagam dados nem removem colunas. Veja [doc 20](20-OPERACAO-E-DEPLOY.md).

**ADR** (*Architecture Decision Record*) - registro curto de uma decisao de arquitetura: contexto, decisao e consequencias. Ficam em
[`docs/decisoes/`](decisoes/).

**Alembic** - ferramenta de migracoes do banco. As migracoes do `core` vem **dentro do pacote** do LuftBase. Veja [doc 09](09-PERSISTENCIA-E-MIGRACOES.md).

**Ambiente** - onde um sistema roda: `desenvolvimento` (sua maquina), `homologacao` (validacao, Linux) ou `producao` (Windows). Cada um tem
seu banco, sua pasta no Vault e suas roles. Escolhido por `LUFT_AMBIENTE`. Veja [doc 22](22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md).

**Aplicacao satelite** - um sistema Luft (ConnectAir, Integrador, Control, Faturas...) que usa o LuftBase como plataforma e escreve so as
regras de negocio. Veja [doc 19](19-GUIA-DA-APLICACAO-SATELITE.md).

**Baseline** - a revisao inicial do `core` (`20260915_0001`, as 13 tabelas migradas do SQL Server). Bancos antigos a "adotam" com `banco registrar-base`.

**Categoria** - o que um sistema *e* (aplicacao web, API, servico, ferramenta, relatorio, integracao, hub). So agrupa e rotula o card.
Veja [doc 24](24-SISTEMAS-E-CATALOGO.md).

**Catalogo** - a lista de sistemas do ecossistema (`core.tb_sistema`). Tambem se chama **catalogo de permissoes** a arvore de modulos e
permissoes que uma aplicacao declara em `App/Catalogo.py`.

**CAS 0** (*check-and-set*) - forma de gravar no Vault que **falha se o segredo ja existe**. O provisionamento usa para nunca sobrescrever um segredo.

**Core** - o schema `core` do banco PostgreSQL: tabelas **compartilhadas** pela plataforma (usuarios, sessoes, permissoes, sistemas, auditoria,
notificacoes). Pertence ao LuftBase; as aplicacoes leem e usam, nao criam tabelas ali. Veja [doc 05](05-BANCO-E-SCHEMAS.md).

**Diretorio** - o SQL Server corporativo com usuarios e grupos (Luftinforma). **Somente leitura** para o LuftBase.

**Espelho** - copia do banco de homologacao na sua maquina, feita por `banco espelhar`. Veja [doc 25](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md).

**Externo** - sistema do catalogo que **nao usa o LuftBase** (`integra_luftbase = false`): ferramenta em C#, executavel, sistema de terceiros.
Tem card e link, mas nao tem schema, role nem segredo. Veja [doc 24](24-SISTEMAS-E-CATALOGO.md).

**Fail-closed** - na duvida, **nega**. Se a plataforma nao consegue comprovar uma permissao (banco fora do ar, por exemplo), a resposta e 503, nunca "liberado".

**Grupo** - conjunto de usuarios no diretorio. Permissoes podem ser dadas a um grupo ou a uma pessoa (a regra da pessoa vence).

**Hub** - o Luft-Workspace como portal central (o sistema de `id_sistema = 0`), com os cards de todos os sistemas.

**Idempotente** - que pode ser repetido sem efeito colateral. Os scripts gerados e os de `tools/sql/` podem rodar duas vezes sem erro.

**Integrado** - sistema que **usa o LuftBase** (`integra_luftbase = true`): login, permissoes, auditoria e banco da plataforma.

**KV v2** - o tipo de area de segredos do Vault usado aqui (`secret/`). Guarda **versoes**: sobrescrever cria uma nova versao em vez de perder a anterior.

**LuftBase** - esta plataforma. Um pacote Python instalado nas aplicacoes Luft. Veja o [README](../README.md).

**LuftCore** - o sistema **antigo** que o LuftBase substitui. Os documentos o citam para explicar de onde vieram certas decisoes ([doc 08](08-INVENTARIO-LUFTCORE.md)).

**Migracao / revisao** - uma mudanca versionada no `core`. Cada banco registra em `core.alembic_version` em qual revisao esta (ex.: `20261015_0017`).
Aplicada **somente por comando explicito**, nunca na inicializacao do app.

**Modulo** - agrupador de permissoes dentro de um sistema (`PLATAFORMA`, `RELATORIOS`...). Todo sistema nasce com o modulo `PLATAFORMA`.

**NSSM** - programa que roda um executavel como servico do Windows; e como as aplicacoes rodam em producao no Windows.

**Painel de Controle** - a area administrativa que todo sistema Luft herda do LuftBase (`/configuracoes/painel`). Veja [doc 14](14-PAINEL-DE-CONTROLE.md).

**Permissao** - uma chave `MODULO.RECURSO.ACAO` (ex.: `RELATORIOS.DRE.VISUALIZAR`). Conceder um no da arvore concede os filhos. Veja [doc 11](11-AUTORIZACAO.md).

**Permissao base de acesso** - a permissao `<PREFIXO>.SISTEMA.ACESSAR` que abre a porta de um sistema (e o card dele) para uma pessoa.

**Pin** - fixar a versao do LuftBase no `requirements.txt` da aplicacao (`luft-base @ git+...@v0.1.0aNN`).

**Prefixo** (`ROUTE_PREFIX`) - o caminho sob o qual a aplicacao e publicada (`/Luft-Faturas`). Links e `action` de formulario devem usar `url_for` e
`request.script_root`, nunca caminho fixo. Veja [doc 17](17-SERVIDOR-REDE-E-FUSO.md).

**Promocao** - levar uma mudanca de um ambiente para o seguinte (desenvolvimento -> homologacao -> producao).

**Role** - usuario/papel do PostgreSQL. Cada sistema integrado tem a sua, so com acesso ao proprio schema e ao basico do `core`:
`luft_<schema>_app` em producao; `luft_<schema>_hml_app` e `luft_<schema>_dev_app` nos outros ambientes.

**Runtime** - a aplicacao em execucao. Nunca usa usuario administrativo do banco: so a role do sistema.

**SCRAM-SHA-256** - forma segura de guardar senha no PostgreSQL. O espelho leva o *hash* da senha, nunca a senha.

**Schema** - "pasta" de tabelas dentro de um banco PostgreSQL. Ha o `core` (da plataforma) e um por sistema integrado (`connectair`, `integrador`, `faturas`...).

**Segredo** - conjunto de valores no Vault (host, usuario, senha...). O de cada sistema fica em `luft/<ambiente>/bancos/postgresql/sistemas/<id>`.

**Sessao / SSO** - o login e unico e compartilhado entre os sistemas (cookie `luft_sessao`); a sessao fica no PostgreSQL. Veja [doc 10](10-IDENTIDADE-E-SESSAO.md).

**Sistema** - cada linha do catalogo. O `id_sistema` e **gerado por ambiente**: o mesmo sistema pode ter IDs diferentes em cada um.

**Tag** - marca de versao no Git (`v0.1.0a110`). As aplicacoes instalam o LuftBase **pela tag**.

**Token de operador** - token do Vault de quem administra (diferente de `LUFT_VAULT_TOKEN`, que e o da aplicacao). Pedido no terminal, nunca gravado.

**Trilha de auditoria** - registro encadeado de acessos, eventos e alteracoes (antes/depois). Veja [doc 12](12-AUDITORIA-E-OBSERVABILIDADE.md).

**Vault** - o cofre de segredos (HashiCorp Vault). Um so para os tres ambientes; o que muda e a pasta (`luft/<ambiente>/...`).

**WSL** - Windows Subsystem for Linux. Quem roda o PostgreSQL local nele usa `banco espelhar --via-wsl`.

**Workspace** - o Luft-Workspace: portal central e Painel de Controle de todo o ecossistema (sistema `0`).
