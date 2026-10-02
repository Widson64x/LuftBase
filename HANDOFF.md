# Handoff

Atualizado em: 2026-09-30

## Estado

O LuftBase esta na versao `0.1.0a21`. A trilha de logs foi refatorada para a estrutura
relacional encadeada: tb_logacesso (requisicoes HTTP/rotas) -> tb_logdetalhe (acoes, erros e detalhes)
-> tb_logs (alteracoes de estado: antes/depois). A observabilidade local inclui arquivos fisicos
rotativos (Logs/*.log) e raiz temporaria de processo (Logs/temp/*.temp.log) com buffer circular.
O modulo analitico de Auditoria no Painel de Controle oferece 5 visoes: Acessos, Detalhes,
Alteracoes, Raiz temporaria e Arquivos fisicos.
Nenhuma operacao deste trabalho alterou o SQL Server ou Vault remoto.

## Entregue nesta continuidade (0.1.0a32)

- Correcao do cache de autorizacao sem Redis: TTL respeitado em `ArmazenamentoSessoesMemoria`.
  Com varios processos (Workspace + aplicacoes), uma concessao passa a valer em ate ~5 s em
  vez de so apos reiniciar a aplicacao.

## Entregue na continuidade anterior (0.1.0a31)

- Cadastro de sistema pelo Workspace provisiona schema, role, privilegios e segredo no Vault
  com credenciais de operador pedidas no modal (`infraestrutura/provisionamento_sistema.py`).
- Nao testado contra PostgreSQL/Vault reais nos testes automatizados (fakes); primeiro uso
  real: cadastro do Luft-ConnectAir (ID 1) no desenvolvimento.

## Entregue na continuidade anterior (0.1.0a30)

- Sistemas permanentes: sem exclusao; inativo = pagina "descontinuado" (HTTP 410) (ADR-016);
- `PlataformaLuft(catalogo=...)` confere e completa o catalogo da aplicacao na inicializacao;
- `CONFIGURACOES.SISTEMAS.DESATIVAR` no lugar de `EXCLUIR`;
- `luftbase vault postgresql remover-sistemas` (a29) para limpeza manual de segredos.

## Entregue na continuidade anterior (0.1.0a28)

- `luftbase catalogo sincronizar` e `CatalogoAplicacao` para sistemas satelites (ADR-015);
- `exigir_ajax`, ponte `flash` -> toasts e correcao de URLs para apps publicados sob prefixo;
- primeiro consumidor: Luft-ConnectAir (sistema 1), branch `feature/migracao-luftbase`.

Pendencias: o sistema 1 ainda nao existe em `core.tb_sistema` de desenvolvimento; a role
`luft_connectair_app` nao pode cadastra-lo, entao a sincronizacao precisa de `--usuario-banco`.
O core de producao esta na revisao `20260918_0008` e precisa de `bootstrap --atualizar` antes de
receber aplicacoes satelites.

## Entregue na continuidade anterior (0.1.0a27)

- Integracao de e-mail (`luftbase.integracoes.email`) liberada pela plataforma a partir do
  segredo `luft/{ambiente}/integracoes/email` (ADR-014, docs 03, 04 e 07);
- `CredencialEmail` e `CarregadorCredenciais.carregar_email`, com `starttls`/`ssl` apenas;
- segredo opcional na `FabricaInfraestruturaPadrao`; invalido interrompe a inicializacao;
- `ServicoEmail` com modo teste, envio em lote, texto alternativo e auditoria;
- layout `luftbase/email/base.html`, macros e logo no wheel;
- CLI `luftbase email testar` e status de e-mail no `vault verificar`;
- `_versao.py` estava em `0.1.0a22` enquanto o `pyproject.toml` estava em `0.1.0a26`; ambos
  agora em `0.1.0a27`.

Proximo passo exato: o segredo `integracoes/email` precisa ser gravado no Vault com as chaves
em minusculo (docs/04). Depois, `luftbase email testar --para <endereco>` em cada ambiente e
inicio da migracao do Luft-ConnectAir (remover `Services/EmailService.py` e as variaveis
`EMAIL_*`, e fazer `Templates/Email/PlanejamentoFilial.html` estender o layout do LuftBase).

## Entregue na continuidade anterior (0.1.0a21)

- Trilha estruturada refeita: `tb_logacesso -> tb_logdetalhe -> tb_logs`;
- `tb_logacesso` concentra rotas e dados de requisicao/resposta HTTP;
- `tb_logdetalhe` armazena acoes, erros, ocorrencias e a identidade historica do usuario e grupo;
- `tb_logs` armazena o retrato sanitizado de dados alterados (`dados_anteriores_json`, `dados_novos_json`);
- Vinculo automatico entre detalhe e acesso por `(id_sistema, id_correlacao)` na conclusao da requisicao HTTP;
- FKs compostas impedindo vinculos entre sistemas diferentes e cascatas na remocao de registros pai;
- Revisao Alembic `20260923_0011` destrutiva para o piloto de desenvolvimento, validada com upgrade/downgrade/upgrade;
- Modulo de Auditoria ampliado com 5 visoes (Acessos, Detalhes, Alteracoes, Raiz temporaria e Arquivos fisicos);
- Logs fisicos rotativos e raiz temporaria protegidos simultaneamente pelas permissoes de auditoria e dados sensiveis;
- Wheel `0.1.0a21` gerado, disponibilizado em `vendor/` e instalado no ambiente do Workspace.

## Entregue na continuidade anterior (0.1.0a20)

- painel de Auditoria com KPIs, serie temporal, rankings, filtros e detalhe lateral;
- consultas e exportacao CSV por sistema, usuario e grupo;
- separacao entre visualizar, exportar e visualizar dados sensiveis;
- retrato historico de grupo nos acessos HTTP, eventos e buffer tecnico;
- migration `20260922_0010` com colunas e indices analiticos;
- escopo de aplicacoes satelites aplicado na propria consulta SQL;
- ADR-012 e documentacao operacional da API e das limitacoes;
- ensaio real da migration e do servico em copia isolada do PostgreSQL local.

## Entregue na continuidade anterior (0.1.0a16)

- **Catálogo de Módulos e Permissões Canônicas**:
  - Nova tabela `core.tb_modulo` e campos hierárquicos em `core.tb_permissao`.
  - 9 módulos padrão e 48 permissões canônicas em formato `MODULO.RECURSO.ACAO`.
  - Resolução RBAC por CTE recursiva no PostgreSQL com 12 regras de precedência (fail-closed, ancestral inativo, usuário sobre grupo, distância na árvore, escopo sistema sobre global).
  - Remoção definitiva de `id_permissao_base` e `categoria_permissao`.
- **Interface Web de Segurança & Permissões**:
  - Tela `gerenciador.html` com controles diretos para Permitir, Bloquear e Restaurar Herança.
  - Exibição de módulo, recurso, ação, permissão pai, nível de profundidade e sensibilidade.
  - Eliminação de qualquer ambiguidade entre "desmarcar" e "bloquear".
- **CLI e Sincronização**:
  - `luftbase bootstrap --atualizar` para migração Alembic e sincronização aditiva sem acessar o cofre.
  - Sincronização idempotente `sincronizar_catalogo_workspace()`.
- **Arquitetura e Sessões**:
  - Registro da ADR-011.
  - Decisão sobre sessões: PostgreSQL definitivo e fallback oficial, Redis opcional no piloto e recomendado para produção multi-instância em namespace único por ambiente.
  - Remocao total de privilegios hardcoded em seguranca e configuracoes.
  - Permissoes granulares: `ADMIN.SEGURANCA.VISUALIZAR`, `ADMIN.SEGURANCA.EDITAR`,
    `ADMIN.PERMISSOES.CRIAR`, `ADMIN.AUDITORIA.VISUALIZAR`, `ADMIN.SESSOES.VISUALIZAR`,
    `ADMIN.SESSOES.REVOGAR`, `ADMIN.MANUTENCAO.GERENCIAR`, `ADMIN.MANUTENCAO.BYPASS`.
  - Invalidação de cache RBAC distribuído pós-commit no PostgreSQL.
  - `validar_csrf_requisicao` uniforme com suporte a header `X-CSRF-Token`, formulário e JSON.
- **Middleware de Manutencao e Respostas Padronizadas**:
  - Middleware de manutencao (`before_request`) com cache local de curto TTL, isencoes
    operacionais (saude, login, estaticos) e bypass para operadores autorizados.
  - Modulo `luftbase.web.respostas` padronizando respostas JSON, popups e toasts corporativos.
  - Handlers de erro 403, 404 e 500 com deteccao automatica de resposta JSON vs HTML.
- **Conteudo e Publicacoes**:
  - `RepositorioNotificacoes` e `ServicoNotificacoes`: `contar_nao_lidas` e `limpar_expiradas`.
  - `RepositorioPublicacoes` e `ServicoPublicacoes`: `atualizar_rascunho`, `arquivar`,
    `listar_administracao`, `obter_administracao`, `importar_comunicado_externo` e `sincronizar_provedor`.
  - Captura de excecoes ajustada (`ConteudoNaoEncontrado` -> 404 antes de `ErroConteudo` -> 400).
  - Inclusao dos arquivos `interface/static/video/*.json` no pacote wheel.

## Regras que nao podem regredir

- sistema `0` significa escopo global (Hub Master), nunca bypass de autorizacao;
- falha ou chave desconhecida nega acesso;
- runtime nao recebe DDL nem conta administrativa;
- migrations nao rodam no startup;
- SQL Server e estritamente somente leitura;
- segredos nunca sao passados por argumento, log, chat ou arquivo de manifesto;
- estruturas legadas do Vault nao sao sobrescritas nem removidas.

## Validacao automatizada mais recente

Em 2026-09-30 (0.1.0a30): `pytest` com 332 testes aprovados; `ruff check` e `ruff format`
aprovados nos arquivos alterados; `build` gerou o wheel com templates e logo de e-mail. A base
ja tinha pendencias fora deste trabalho: `ruff check src tests` aponta 46 erros, `ruff format
--check` 12 arquivos e `mypy src` 16 erros em `identidade/repositorio_core.py`,
`interface/web.py` e `web/configuracoes.py`.

Registro anterior:


- `pytest`: 267 testes aprovados no LuftBase e 16 testes aprovados no Workspace;
- `ruff check` e `ruff format --check`: aprovados em 153 arquivos no LuftBase;
- `mypy`: aprovado em 110 arquivos-fonte com tipagem estrita no LuftBase;
- migration `0011` testada em ciclo upgrade -> downgrade -> upgrade e validada com `validar_trilha_logs_0011.sql`;
- banco local de desenvolvimento `luft_web` atualizado para `20260923_0011` com `aplicar_privilegios_core.sql`;
- wheel `0.1.0a21` gerado e instalado no venv do Workspace.
