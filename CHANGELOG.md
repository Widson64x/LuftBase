# Registro de Alterações (ChangeLog) - LuftBase

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

## [0.1.0a75] - 2026-10-06

### Adicionado

- Conteudo rico nas publicacoes: o corpo de comunicados e notas de atualizacao aceita markdown seguro
  (titulos, listas, negrito, links, imagens, destaques `:::sucesso|info|alerta|perigo` e `:::cards`).
  Todo texto e escapado; imagens so por `https://` ou `luftbase:` (estaticos do LuftBase).
- `luftbase.conteudo.changelog_plataforma`: nota global "Nova plataforma Luft" (mudanca para o LuftBase)
  com banner e ilustracoes em SVG, publicada com notificacao e idempotente.

## [0.1.0a74] - 2026-10-06

### Corrigido

- O navegador (User-Agent) nunca era gravado na sessao nem no usuario: `bool(request.user_agent)` e
  sempre falso no Werkzeug. Passa a ler o cabecalho `User-Agent` direto (sessao, log de acesso e
  log tecnico). Sessoes ativas se corrigem sozinhas na proxima requisicao.

## [0.1.0a73] - 2026-10-06

### Alterado

- Perfil: o "Historico de Acessos" mostra os 5 ultimos acessos.

## [0.1.0a72] - 2026-10-06

### Adicionado

- Perfil, aba "Sessoes & Seguranca": cada sessao mostra navegador e sistema (ex.: "Chrome 126 em
  Windows") alem do IP, lidos do `User-Agent` sem dependencia nova, e ha um "Historico de Acessos"
  (ultimos 30: IP, navegador, inicio, fim e motivo do encerramento) em `GET /perfil/sessoes/historico`.

## [0.1.0a71] - 2026-10-06

### Corrigido

- IP do usuario: todos apareciam como `127.0.0.1`. O Waitress 3 apaga os cabecalhos `X-Forwarded-*`
  quando nao ha proxy confiavel, entao o IP que o nginx informava nunca chegava a aplicacao. O
  servidor agora confia no nginx local (`127.0.0.1`; `LUFT_PROXY_CONFIAVEL` troca o IP e
  `desligado` desativa), e so vale o IP que o proprio proxy acrescentou, nunca um valor que o
  cliente forje. A sessao grava `request.remote_addr` em vez de ler `X-Forwarded-For` cru (o 1o item
  era forjavel). A auditoria passa a registrar o IP real tambem.
- "Total de logins" ficava sempre em 0: nada o incrementava. Agora cada login de verdade (sessao
  nova) soma 1; renovacoes e polling nao.

### Alterado

- Tela de perfil: a barra "Carregar nova foto / Remover foto" saiu. O botao da camera no avatar
  (agora com um selo sempre visivel) abre um editor de foto: recorte circular, arrastar, zoom
  (controle, roda do mouse e setas), girar, centralizar, escolher/trocar (tambem arrastando o
  arquivo), remover com confirmacao no proprio botao e salvar. Erros aparecem no modal, sem `alert`.
- Idioma da interface comentado (o sistema e focado em pt-BR por enquanto); o campo nao e mais
  enviado, entao o valor salvo nao e sobrescrito.

## [0.1.0a70] - 2026-10-06

### Corrigido

- Horarios errados no Linux: o servidor roda em UTC e `datetime.now()` devolve o horario DA
  MAQUINA, entao a mesma aplicacao gravava 17:55 no Linux quando em Brasilia eram 14:55. Corrigido em
  tres camadas: (1) relogio unico `luftbase.nucleo.tempo.agora_local()` (America/Sao_Paulo, sem
  tzinfo, formato das colunas `timestamp`), usado nas sessoes, no buffer de logs, no e-mail e no
  conteudo; (2) `aplicar_fuso_do_processo()` poe o processo todo no mesmo fuso na inicializacao
  (Linux), o que corrige tambem o `datetime.now()` das aplicacoes e os horarios dos logs; (3) toda
  conexao PostgreSQL fixa `timezone` da sessao, entao `now()`/`CURRENT_TIMESTAMP` das colunas e das
  aplicacoes saem no mesmo fuso. `LUFT_FUSO_HORARIO` troca o fuso; no Windows vale o fuso do sistema.
- Registros ja gravados com a hora errada (17:xx em vez de 14:xx) nao sao reescritos.

## [0.1.0a69] - 2026-10-06

### Corrigido

- Causa raiz do usuario que continuava ONLINE depois de sair: o login gravava o cookie "lembrar"
  do Flask-Login (`remember=True`, um ano) e o logout nao o apagava (`session.clear()` descartava a
  ordem de remocao). Na requisicao seguinte o Flask-Login lia o cookie e gravava `_user_id` na
  sessao anonima mesmo sem reconhecer o usuario, e o armazenamento ligava essa sessao ao usuario so
  por esse campo: nascia uma sessao `ATIVA` do usuario, renovada pelo polling a cada 10 s.
  Correcoes: (1) o login nao grava mais o cookie (`remember=False`); (2) `descartar_cookie_lembrar`
  remove o cookie que ainda existir nos navegadores, antes de qualquer outro `before_request`, e o
  logout repete a ordem de remocao apos a limpeza; (3) so `luftbase_usuario` liga uma sessao a um
  usuario, `_user_id` sozinho nao.

## [0.1.0a68] - 2026-10-06

### Corrigido

- Usuario continuava ONLINE, com sessao ativa, depois de sair. O armazenamento de sessoes
  reativava (`status = ATIVA`) qualquer sessao ja existente que recebesse uma gravacao tardia, por
  exemplo uma requisicao em segundo plano de outra aba terminando depois do logout, e devolvia o
  usuario ao estado online. Sessao encerrada (logout, expirada ou revogada) agora ignora gravacoes;
  um novo login rotaciona o id e cria sessao nova, entao nada muda para quem entra.
- A presenca (`atualizar_presenca`, chamada pelo polling de mensagens) agora so vale para uma
  sessao ATIVA do proprio usuario e exige o id da sessao.
- O id da sessao corrente era lido de `session["_id"]`, que nao existe (o id fica no objeto da
  sessao): o resultado era sempre vazio. Isso fazia a lista de sessoes nao marcar nenhuma como
  "atual" e o "revogar outras sessoes" tratar a propria sessao como outra. Novo helper
  `id_sessao_atual()` em `luftbase.interface.web`.

## [0.1.0a67] - 2026-10-06

### Corrigido

- SQL Server: quando o driver ODBC pedido (padrao `ODBC Driver 18 for SQL Server`) nao esta
  instalado, o LuftBase usa o melhor que a maquina tem (18, 17, 13, 11, Native Client 11, e por
  ultimo o `SQL Server` legado) e avisa no log. Antes a conexao falhava com `IM002` num servidor
  Windows que so tinha o Driver 17, derrubando o login. Os parametros `Encrypt` e
  `TrustServerCertificate` so sao enviados a drivers que os entendem (o legado nao).

## [0.1.0a66] - 2026-10-06

### Adicionado

- Erro 500 passa a deixar rastro no log fisico (`Logs/luftbase.log`): rota, metodo, cadeia de tipos
  das excecoes e as ultimas linhas da pilha (arquivo, linha e funcao), inclusive de onde a causa
  raiz nasceu. Em servico sem console (NSSM/systemd) o motivo do 500 se perdia. A mensagem e os
  parametros da excecao NAO sao gravados (erros de banco carregam dados e credenciais).

## [0.1.0a65] - 2026-10-06

### Corrigido

- O formulario de login enviava as credenciais para `/login` na RAIZ do dominio quando a aplicacao
  roda sob um prefixo (ex.: `/Luft-Integrador`), porque `action` usava so `request.path`. Atras do
  nginx o POST caia no Workspace: dava certo quando o Workspace respondia (a sessao e compartilhada)
  e falhava com pagina de erro do nginx quando nao. Agora `action` inclui `request.script_root`.

## [0.1.0a64] - 2026-10-06

### Corrigido

- Espelhar permissoes (e dar Permitir/Bloquear) para um usuario que ainda nao fez login no
  LuftBase falhava com violacao de chave estrangeira (`fk_core_permissaousuario_usuario`): a lista
  de usuarios vem do diretorio, mas a regra exige o cadastro em `core.tb_usuario`. Agora o
  cadastro e criado na hora, a partir do diretorio, e completado no primeiro login.

### Alterado

- Tela "Espelhar permissoes" redesenhada em linguagem simples ("Copiar permissoes"): 1) copiar de
  quem (grupo ou pessoa, com busca), mostrando as permissoes que serao copiadas; 2) quem recebe,
  com o que ele ja tem hoje; 3) como aplicar ("Deixar igual a origem" ou "Somar ao que ja tem").
  Uma frase resume o efeito antes de confirmar; erros aparecem no proprio modal em vez de `alert`.
- `GET /seguranca/api/permissoes/resumo-origem` tambem devolve a lista de regras (`regras`).

## [0.1.0a63] - 2026-10-06

### Adicionado

- Aplicacoes & Ambiente > Variaveis de Ambiente funciona (antes devolvia 501): le e altera o `.env`
  de cada projeto, mas SO as variaveis NAO sensiveis de uma lista fechada (tempo de sessao e do
  login corporativo, cache de permissoes, validade de links de e-mail e de qual ambiente vem o
  banco de negocio). Tokens, Vault, identidade do sistema, cookies e LDAP nunca sao lidos nem
  gravados pela web. Valores validados (inteiro em faixa ou opcao), com copia de seguranca
  `.env.bak`, gravacao atomica, comentarios e quebra de linha preservados, auditoria e aviso de
  que o servico precisa reiniciar. O projeto vem da pasta irma com o nome do sistema (mesma
  convencao dos servicos, sem `.env`).

### Corrigido

- Servicos do Servidor: `systemctl` e `sudo` sao localizados tambem nos diretorios padrao do
  sistema. Um servico systemd com `PATH` restrito (ex.: so a `.venv`) deixava todos os cartoes
  como UNAVAILABLE. Quando um servico fica indisponivel, a tela passa a mostrar o motivo.

## [0.1.0a62] - 2026-10-06

### Adicionado

- Painel de Controle > Aplicacoes & Ambiente > Servicos do Servidor funciona (antes devolvia 501).
  O servico de cada aplicacao e descoberto pelo NOME do sistema no catalogo, sem `.env` e sem
  nomes fixos: Linux/systemd = nome em minusculo + `.service` (`Luft-ConnectAir` ->
  `luft-connectair.service`); Windows = o proprio nome (`Luft-ConnectAir`). O Workspace ve todas
  as aplicacoes ativas; um satelite ve so a propria. Status em tempo real, iniciar, parar e
  reiniciar, com CSRF, permissao `AMBIENTE.SERVICOS.EXECUTAR` e auditoria.
- Seguranca: so atua em servicos de sistemas cadastrados (nada de nomes livres), nomes passam por
  lista de caracteres permitidos, comandos rodam sem shell e com tempo limite. O Workspace e a
  propria aplicacao em execucao sao somente monitoramento (parar a si mesma derrubaria a tela).
- Linux: as acoes usam `sudo -n systemctl`. O usuario do servico precisa de sudo sem senha para
  esses comandos, por exemplo em `/etc/sudoers.d/luft-servicos`:
  `<usuario> ALL=(root) NOPASSWD: /usr/bin/systemctl start luft-*.service, /usr/bin/systemctl stop luft-*.service, /usr/bin/systemctl restart luft-*.service`.
  O status nao precisa de sudo. Sem a regra, a tela explica o motivo em vez de falhar em silencio.
- Windows: usa `sc query/start/stop` (rotulo "STATE"/"ESTADO" independe do idioma).

## [0.1.0a61] - 2026-10-06

### Alterado

- Breadcrumb padronizado em todos os sistemas: `[casinha] > [Aplicacao] > [pagina]`. A casinha
  leva a raiz da plataforma (Luft-Workspace; `/`, ou `LUFT_URL_WORKSPACE` no `app.config`) e o nome
  da aplicacao leva a raiz da propria aplicacao. Antes a casinha e o nome eram um unico link, e
  nas paginas do LuftBase ele levava ao Workspace. Novo macro compartilhado
  `luftbase/_breadcrumb.html` (`raiz`), usado por todas as telas do LuftBase; as aplicacoes com
  tela inicial propria passam `href_app=url_for(...)`. Variavel de contexto `luft_url_workspace`.

## [0.1.0a60] - 2026-10-05

### Corrigido

- Comunicados e notas globais (`id_sistema = 0`, criados no Workspace) apareciam no feed dos
  usuarios de todos os sistemas, mas nao na tela de gestao de um sistema satelite, que listava
  so as proprias publicacoes. A gestao de um satelite agora tambem lista as globais ja visiveis
  (publicadas ou agendadas), marcadas "Gerenciado no Workspace" e sem botoes de editar, publicar
  ou arquivar. Criar, editar e arquivar uma global continua exclusivo do Workspace (o backend
  ja recusava a operacao em outro sistema). Rascunhos e arquivadas globais seguem so no Workspace.

## [0.1.0a59] - 2026-10-05

### Corrigido

- O cadastro de um sistema no Workspace cria a permissao base `<NOME>.SISTEMA.ACESSAR` (ex.:
  `LUFT_CONNECTAIR.SISTEMA.ACESSAR`), mas a aplicacao declara no catalogo a sua propria (ex.:
  `CONNECTAIR.SISTEMA.ACESSAR`), que e a que o codigo verifica. A provisoria ficava sobrando,
  sem efeito, ao lado da real. Na primeira sincronizacao do catalogo a provisoria e substituida:
  os vinculos de grupos e usuarios sao copiados para a permissao real (sem sobrescrever regra que
  ja exista nela) e a provisoria e removida (ou desativada, se a role nao puder apagar).
  Sistemas ja cadastrados sao corrigidos na proxima inicializacao.

## [0.1.0a58] - 2026-10-05

### Corrigido

- Conexoes ociosas de SQL Server apareciam no monitor do banco como sessao "sleeping" com
  transacao aberta (por minutos), por exemplo `user.services` no diretorio de usuarios. No modo
  padrao o driver ODBC mantem uma transacao sempre aberta na conexao, mesmo depois do rollback.
  `ConstrutorEngines.criar(credencial, somente_leitura=True)` liga o autocommit do driver em SQL
  Server; o diretorio de usuarios passa a usar essa opcao e as aplicacoes podem usa-la nos bancos
  de negocio somente leitura (ERP). PostgreSQL nao muda.

## [0.1.0a57] - 2026-10-05

### Adicionado

- Aba **Integracoes** no Painel de Controle (antes desabilitada): cartoes por componente (Vault,
  PostgreSQL, SQL Server, sessoes, e-mail/Gmail, login corporativo, LuftBase, componentes e a
  propria aplicacao) com estado de saude, filtro por categoria e modal de detalhes.
- O modal do Vault mostra os caminhos de segredo em uso no ambiente atual (ex.:
  `luft/homologacao/bancos/sqlserver/conexoes/consulta`), a versao de cada segredo, a data da
  ultima alteracao e os NOMES dos campos. Senhas, tokens e chaves nunca saem do servidor: so
  `host`, `porta`, `banco`, `usuario` e similares (lista fixa) tem o valor exibido.
- Verificador de versao do LuftBase contra as tags do GitHub (cache de 15 min; falha nao derruba
  o painel). Repositorio privado ou rede restrita: defina `LUFT_GITHUB_TOKEN`; o repositorio pode
  ser trocado com `LUFT_BASE_REPOSITORIO`.
- `PlataformaLuft(integracoes=[IntegracaoAplicacao(...)])`: a aplicacao declara as integracoes
  proprias (ex.: bancos de negocio) para aparecerem na aba.
- `ClienteVaultHvac.ler_metadados` e `versao_servidor`.
- Rotas `GET /configuracoes/api/configuracoes/integracoes` e `.../integracoes/versao-luftbase`,
  protegidas por `AMBIENTE.SERVICOS.VISUALIZAR`.

## [0.1.0a56] - 2026-10-05

### Corrigido

- O cadastro de um sistema em homologacao (ou desenvolvimento) criava a role `luft_<schema>_app`,
  a MESMA da producao (roles pertencem ao cluster, nao ao banco), e trocava a senha dela. Agora a
  role leva o sufixo do ambiente (`luft_<schema>_hml_app`, `luft_<schema>_dev_app`) e a de
  producao continua `luft_<schema>_app`. O provisionador recusa alterar uma role fora do padrao
  do ambiente e o modal mostra o nome real da role.

### Adicionado

- `luftbase vault postgresql reprovisionar-sistema`: recria schema, role do ambiente e o segredo
  `sistemas/<id>` de um sistema ja cadastrado (simulacao por padrao; nova versao no KV v2).
- Suporte a Oracle (`TipoBanco.ORACLE`, `oracle+oracledb`).

## [0.1.0a49] - 2026-10-01

### Corrigido

- Notificacao de um comunicado ja arquivado continuava no sino: o wheel a48 foi gerado antes da
  regra que recolhe a notificacao emitida por uma publicacao arquivada. O wheel a49 inclui a
  regra (lista, contagem, leitura e eventos de notificacao).

## [0.1.0a46] - 2026-10-01

### Adicionado

- Busca global na barra superior (antes era so decorativa). No navegador ela pesquisa os itens do
  menu lateral que o usuario pode ver (sem acento e sem maiusculas, com destaque do trecho
  encontrado) e abre com `Ctrl+K` ou `/`; setas navegam, Enter abre, Esc fecha.
- Provedores de busca por aplicacao: `PlataformaLuft(..., buscas=[ProvedorBusca(...)])` e
  `ResultadoBusca`. O endpoint `GET /_luftbase/busca?q=` consulta os provedores em paralelo, so os
  que o usuario pode usar (`permissao`), com prazo de 4 s por requisicao, tolerando falha de um
  provedor e descartando URLs que nao sejam do proprio sistema (`urls_externas=True` aceita
  `http(s)` completo, para catalogos como o de sistemas do Hub).
- `luft_url_busca` no contexto dos templates.

## [0.1.0a45] - 2026-10-01

### Corrigido

- Auditoria & Analise respondia HTTP 400 em toda aplicacao que nao e o escopo global (sistema 0),
  como o Luft-ConnectAir: o painel envia `sistema_id=todos` por padrao e so o sistema 0 entendia
  esse valor. Agora, nas demais aplicacoes, "todos" significa o proprio sistema.
- A lista de sistemas do filtro da Auditoria mostrava todos os sistemas ativos em qualquer
  aplicacao (nomes de sistemas alheios). Agora so o escopo global (sistema 0) ve os demais; as
  outras aplicacoes veem apenas a si mesmas. Detalhe, exportacao, rankings e as listas de
  usuarios e grupos ja respeitavam o escopo.

## [0.1.0a44] - 2026-10-01

### Adicionado

- Componente de e-mail `botao(url, texto, cor, centralizar=False)`: com `centralizar=True` o botao
  fica no meio da mensagem (tabela com `align="center"`, compativel com Outlook e Gmail).

## [0.1.0a43] - 2026-10-01

### Corrigido

- Login com o diretorio LDAP lento ou fora do ar (timeout no bind) estourava erro 500 com
  traceback. Agora responde 503 com a mensagem "O serviço de autenticação está indisponível no
  momento", registra um aviso no log e nao conta como credencial invalida.

## [0.1.0a42] - 2026-10-01

### Adicionado

- `contexto_painel()`: sinalizadores `pode_ver_*` do Painel de Controle para o contexto dos
  templates, em uma consulta em lote. Substitui o calculo que cada aplicacao repetia no seu
  `context_processor`.
- ADR-017: padrao de projeto das aplicacoes (estrutura de pastas, arquivos-base, ordem de
  `App/__init__.py` e nomes fixos), adotado por Luft-Workspace e Luft-ConnectAir.

## [0.1.0a41] - 2026-10-01

### Adicionado

- `luftbase.servidor.executar_desenvolvimento(alvo)`: servidor de desenvolvimento do Flask
  (depurador e recarga automatica fora de producao) com o mesmo console e banner do Waitress.
  O processo pai da recarga so supervisiona; a aplicacao e criada uma unica vez por ciclo.
  Padrao de entrada das aplicacoes: `App/__init__.py` (fabrica), `App.py` (desenvolvimento) e
  `Wsgi.py` (producao), na raiz do projeto.

## [0.1.0a40] - 2026-10-01

### Adicionado

- `luftbase.servidor.executar(alvo)` e o comando `luftbase servir [modulo:atributo]`: todas as
  aplicacoes sobem do mesmo jeito, com Waitress (agora dependencia do LuftBase), console no
  formato `DATA | NIVEL | ORIGEM | MENSAGEM` configurado antes da inicializacao e banner padrao
  (nome, versao, sistema, ambiente, versao do LuftBase e URL). Cada requisicao vai so para
  `Logs/luftbase.log`; o console mostra subida, avisos e erros. Configuracao por
  `LUFT_SERVIDOR_HOST|PORTA|PREFIXO|THREADS`, aceitando `HOST`, `PORT` e `ROUTE_PREFIX`.

### Alterado

- Sessoes no PostgreSQL sem Redis deixaram de ser aviso: viraram uma linha informativa curta.

## [0.1.0a39] - 2026-10-01

### Corrigido

- Preferencia de tema "Sistema" com o navegador em modo escuro deixava a tela pela metade
  (fundo escuro, sidebar e cabecalho claros): as cores escuras vinham da media query, mas
  `data-theme` continuava `light`. O `base.html` agora resolve claro/escuro no cliente antes da
  pintura, como o seletor do perfil ja fazia.

## [0.1.0a38] - 2026-10-01

### Corrigido

- Login com o mesmo `login_usuario` e outro `codigo_usuario` (diretorio apontado para outro
  servidor, por exemplo) violava `uq_core_usuario_login`: o usuario nao era gravado em
  `core.tb_usuario` e toda auditoria falhava por chave estrangeira, em todas as requisicoes.
  O cadastro antigo agora e aposentado (inativo, login marcado com `~codigo`, historico
  preservado) e o novo e gravado, com aviso no log.

## [0.1.0a37] - 2026-09-30

### Alterado

- O diretorio de usuarios (SQL Server) passa a ser lido de uma conexao nomeada:
  `luft/{ambiente}/bancos/sqlserver/conexoes/{conexao}`. O nome vem de
  `LUFT_VAULT_CONEXAO_DIRETORIO` (padrao `user.services`).
- O caminho antigo `luft/{ambiente}/sqlserver` continua como reserva, com aviso no log, ate
  ser removido de cada ambiente. Sem nenhum dos dois, a mensagem aponta o caminho novo.
- `luftbase vault caminhos/verificar` mostram o caminho novo, o legado e o estado da conexao.

## [0.1.0a36] - 2026-09-30

### Corrigido

- `CatalogoEstruturas.verificar` nao traduzia o schema logico dos models da aplicacao
  (`luft_aplicacao`) para o schema real do segredo; toda tabela da aplicacao aparecia como
  "Tabela ausente" no log mesmo existindo. O `Inspector` agora recebe o nome ja traduzido.

## [0.1.0a35] - 2026-09-30

### Adicionado

- `ParametroAplicacao` e `PlataformaLuft(parametros=...)`: a aplicacao registra seus parametros
  internos (titulo, descricao, icone, rota e permissao opcional) e a aba **Configuracoes Gerais**
  do Painel de Controle desenha os cartoes sozinha, so para quem tem a permissao. Substitui as
  telas de "Parametros" que cada sistema criava por conta propria.

## [0.1.0a34] - 2026-09-30

### Corrigido

- Card do usuario no `base.html`: o cargo usava `text-primary font-semibold text-xs`, que vencia
  `.luft-user-role` (peso 800, 10,5px) e deixava a fonte mais fina que a do Workspace. Agora so a
  classe da sidebar define o estilo; as iniciais do avatar usam `.luft-avatar-initials`.

## [0.1.0a33] - 2026-09-30

### Alterado

- Novo `css/sidebar.css`, carregado por `base.html`: card do usuario, grade de acoes rapidas
  (Tema/Config./Sair), grupos colapsaveis e subitens em arvore. O estilo vivia no `Hub.css` do
  Workspace, entao os demais sistemas apareciam com a sidebar sem acabamento.

## [0.1.0a32] - 2026-09-30

### Corrigido

- Permissoes concedidas em um sistema (ex.: pelo Workspace) nao chegavam a outro sistema ja em
  execucao. Sem Redis, o cache de autorizacao usa `ArmazenamentoSessoesMemoria`, que ignorava o
  TTL: a revisao ficava presa na memoria do processo e decisoes antigas (inclusive "negado")
  eram servidas ate reiniciar. O TTL agora e respeitado e a revisao volta a ser lida do banco a
  cada `LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS` (5 s por padrao).

## [0.1.0a31] - 2026-09-30

### Adicionado

- Cadastro de sistema pelo Workspace com provisionamento completo: com a opcao "Provisionar
  banco e Vault agora", o modal pede token de operador do Vault e usuario/senha
  administrativos do PostgreSQL (usados so na requisicao, nunca gravados) e cria schema, role
  `luft_<schema>_app` com senha SCRAM, privilegios no core e o segredo
  `bancos/postgresql/sistemas/{id}` (CAS 0). Ambiente, Vault, host e banco sao os do Workspace;
  o alias da conexao e lido do segredo do proprio Workspace.
- O segredo e a ultima etapa da transacao; se o core nao confirmar, ele e removido.
- `GET /configuracoes/api/configuracoes/sistema/provisionamento` informa o destino ao modal.

## [0.1.0a30] - 2026-09-30

### Adicionado

- `PlataformaLuft(catalogo=...)`: o catalogo da aplicacao e conferido no core a cada
  inicializacao e completado somente quando ha pendencias (`pendencias_catalogo`).
- `PermissaoAplicacao.modulo_codigo` para manter chaves no modulo `PLATAFORMA` do Workspace.
- Sistema descontinuado: pagina `pages/descontinuado.html` e HTTP 410 para sistemas inativos,
  sem bypass.
- ADR-016.

### Alterado

- `CatalogoAplicacao.sistema` agora e opcional; o cadastro do sistema pertence ao Workspace.
- `CONFIGURACOES.SISTEMAS.EXCLUIR` substituida por `CONFIGURACOES.SISTEMAS.DESATIVAR`,
  exigida ao alterar `Ativo` na edicao de sistema. Sistemas nunca sao excluidos.

## [0.1.0a29] - 2026-09-30

### Adicionado

- `luftbase vault postgresql remover-sistemas --ambiente <amb> [--sistema-id N]`: apaga, com
  token de operador e confirmacao digitada, os segredos `bancos/postgresql/sistemas/{id}`.
  Roles, schemas, core e conexoes compartilhadas nao sao tocados.
- Cadastro de sistema no Painel com validacao por campo e transacao unica (sessao do Workspace).

### Decisao

- Criar e excluir sistema pela tela nao altera o Vault; segredos e roles continuam manuais e
  exclusao nunca apaga dados.

## [0.1.0a28] - 2026-09-30

### Adicionado

- Catalogo declarativo de aplicacoes (`CatalogoAplicacao`, `SistemaAplicacao`,
  `PermissaoAplicacao`) e comando `luftbase catalogo sincronizar`, com `--usuario-banco` e
  `--grupo-administrador`.
- `exigir_ajax` e exportacao publica de `exigir_alguma_permissao` e `DefinicaoModulo`.
- Mensagens de `flask.flash` exibidas como toasts pelo endpoint `/_luftbase/mensagens`.
- ADR-015.

### Corrigido

- Aplicacoes publicadas sob prefixo (`SCRIPT_NAME`): login, `next`, logout, pagina 404,
  manutencao, notificacoes, perfil, mensagens e gerenciador de seguranca usam a raiz da
  aplicacao em vez de `/`.

## [0.1.0a27] - 2026-09-30

### Adicionado

- Integração de e-mail `luftbase.integracoes.email`: conta SMTP lida do Vault em
  `luft/{ambiente}/integracoes/email`, exposta como `obter_luftbase().email` e `enviar_email`.
- Modo teste pelo segredo (`redirecionar_para`), com prefixo `[TESTE]` e destinatários reais
  exibidos no corpo.
- Envio em lote numa única sessão SMTP, `ResultadoEnvio` sem exceções de entrega e auditoria
  `EMAIL_ENVIADO`/`EMAIL_FALHA` por mensagem.
- Layout corporativo `luftbase/email/base.html`, macros `luftbase/email/componentes.html` e
  logo embutido no pacote.
- Geração automática da parte `text/plain` a partir do HTML.
- Comando `luftbase email testar` e status do e-mail em `luftbase vault caminhos/verificar`.
- ADR-014.

### Corrigido

- `luftbase.__version__` voltou a acompanhar a versão do `pyproject.toml`.

## [0.1.0a21] - 2026-09-23

### Alterado

- Trilha estruturada refeita como `tb_logacesso -> tb_logdetalhe -> tb_logs`.
- `tb_logacesso` concentra requisições e rotas; `tb_logdetalhe` concentra ações, erros e
  ocorrências; `tb_logs` concentra estados anterior/novo sanitizados.
- Associação automática dos detalhes HTTP pelo par sistema/correlação após a persistência da
  resposta, corrigindo vínculos vazios durante a execução da rota.
- FKs compostas impedem vínculos entre sistemas e cascatas preservam a integridade da cadeia.
- Revisão Alembic destrutiva `20260923_0011`, destinada aos dados descartáveis do piloto.

### Auditoria e diagnóstico

- Painel ampliado com Acessos, Detalhes, Alterações, Raiz temporária e Arquivos físicos.
- Raiz temporária por processo em `Logs/temp/*.temp.log` e buffer circular em memória.
- Leitura segura dos arquivos rotativos, limitada por nome conhecido, linhas e bytes.
- Fontes locais protegidas simultaneamente pelas permissões de auditoria e dados sensíveis.
- Logging técnico do LuftBase encaminhado às fontes locais sem gravar mensagem bruta da
  exceção ou segredos conhecidos.

## [0.1.0a20] - 2026-09-23

### Adicionado

- Painel **Auditoria & Análise** como aba global de **Painel de Controle**, com KPIs, série
  temporal, rankings, filtros, paginação, detalhe lateral e exportação CSV segura.
- API analítica somente leitura para acessos HTTP, eventos de domínio, usuários, grupos e
  sistemas, com limite de período e isolamento SQL por `LUFT_SISTEMA_ID`.
- Permissões separadas para visualizar, exportar e acessar payloads sensíveis.
- Retrato histórico de grupo em `tb_logacesso` e `tb_logdetalhe`, inclusive no buffer técnico.
- Revisão Alembic `20260922_0010` e índices para consultas por grupo e severidade.
- Decorator `exigir_alguma_permissao` para entradas administrativas com mais de uma
  capacidade válida.

### Segurança e operação

- Payloads, traceback e estados anterior/novo permanecem ocultos por padrão e nunca entram no
  CSV.
- Aplicações satélites filtram o detalhe no próprio SQL; o sistema `0` consolida sem ignorar
  autorização.
- Migração ensaiada em cópia isolada do PostgreSQL local; o banco `luft_web` original não foi
  alterado durante o ensaio.

## [0.1.0a16] - 2026-09-22
### Adicionado
- **Catálogo de Módulos e Autorização Hierárquica**:
  - Nova tabela `core.tb_modulo` organizando funcionalmente recursos e permissões por sistema.
  - Modelagem hierárquica em `core.tb_permissao` com `id_modulo`, `id_permissao_pai`, `recurso`, `acao`, `sensivel` e `eh_acesso_sistema`.
  - Resolução RBAC por CTE recursiva no PostgreSQL com 12 regras de precedência (fail-closed, negação por ancestral inativo, usuário prevalece sobre grupo, menor distância na árvore, herança mestre, escopo de sistema sobre global).
  - Catálogo canônico de 9 módulos padrão e 48 permissões canônicas estruturadas estritamente em `MODULO.RECURSO.ACAO`.
  - Enums `AcaoPermissao` (28 ações) e `PermissaoLuftBase` (chaves canônicas do ecossistema).
  - Remoção definitiva de `id_permissao_base` e `categoria_permissao`.
  - Interface de Segurança e Permissões (`gerenciador.html`) com controles inequívocos para **Permitir**, **Bloquear** e **Restaurar Herança**, com distinção clara entre decisões diretas e herdadas.
- **CLI e Sincronização de Catálogo**:
  - Modo `luftbase bootstrap --atualizar` com confirmação segura `ATUALIZAR-{AMBIENTE}-{BANCO}`, validação de `current_database()` e aplicação aditiva sem tocar em credenciais ou cofre.
  - Função `sincronizar_catalogo_workspace()` para upsert idempotente do sistema 0, dos 9 módulos e 48 permissões com concessão mestre opcional.
- **Decisão Arquitetural sobre Sessões e Redis (ADR-011)**:
  - PostgreSQL como backend persistente definitivo de sessões e autorização; Redis opcional no piloto/desenvolvimento e recomendado para ambientes multi-instância em produção com namespace único por ambiente.
- **Migração Alembic**:
  - Versão `20260922_0009_catalogo_hierarquico.py` com upgrade e downgrade idempotentes e preservação de dados legados.

## [0.1.0a14] - 2026-09-21
### Alterado
- CLI `bootstrap`: Ajustado o valor padrão de `admin_user` para `postgres` com prompt indicando DBA/Superuser.
- CLI `bootstrap`: Adicionada verificação e criação automática do banco de dados alvo conectando primeiro à base de manutenção `postgres` com fallback seguro.

## 0.1.0a13 — 2026-09-21

- **Assistente Interativo de Provisionamento (`bootstrap`)**:
  - Novo comando interativo disponível via `luftbase bootstrap`, `luftbase banco bootstrap`, `flask banco bootstrap` e `luftbase vault postgresql bootstrap`.
  - Operação estritamente aditiva (CAS 0) com garantias de não-destruição: isolamento do ambiente alvo sem tocar em desenvolvimento ou chaves legadas.
  - Criação automatizada de schemas (`core`, `workspace`, etc.) e roles com senhas fortes SCRAM-SHA-256 no PostgreSQL.
  - Gravação de segredos no Vault sob `bancos/postgresql/conexoes/{alias}` e `bancos/postgresql/sistemas/{id}`.
  - Execução transacional das migrações do Alembic para criar todas as 17 tabelas do Core e registro do sistema 0 (Workspace).
  - Exportação automática do manifesto não sensível em `docs/manifesto-postgresql-{ambiente}.json`.

## 0.1.0a12 — 2026-09-21

- **Rodapé com Versão e Ambiente (Paridade LuftCore)**:
  - Adicionada classe CSS `.luft-footer-version-link` e `.luft-footer-version-meta` posicionando o ambiente e versão no canto inferior direito do rodapé (`luft-main-footer`).
  - Função `formatar_versao_rodape` formatando tipo de versão/ambiente (e.g. `DESENVOLVIMENTO`, `HOMOLOGACAO`, `PRODUCAO`) e versão (`vX.Y.Z`).
  - Injeção das variáveis `luft_tipo_versao_app`, `luft_app_version_type`, `luft_versao_app`, `luft_app_version`, `luft_versao_rodape`, `luft_app_version_text` e `luft_url_changelog` no processador de contexto Jinja.
  - Link de ChangeLog atualizado na navegação secundária e no link discreto de versão do rodapé.

## 0.1.0a11 — 2026-09-21

- **Estabilização de Escopo e Hub Master**:
  - Política central de escopo (`luftbase.web.escopo`): resolução canônica de `id_sistema` com validação de satélites e proteção estrita do sistema 0 contra manutenção.
  - Auditoria habilitada para `id_sistema >= 0`, garantindo persistência de auditoria HTTP e de domínio para o Workspace (sistema 0).
  - Remoção de privilégios hardcoded em Segurança & Permissões e separação granular de permissões (`ADMIN.SEGURANCA.VISUALIZAR`, `ADMIN.SEGURANCA.EDITAR`, `ADMIN.PERMISSOES.CRIAR`).
  - Invalidação de cache RBAC distribuído pós-commit no PostgreSQL.
- **Segurança e CSRF**:
  - `validar_csrf_requisicao` unificado para cabeçalho `X-CSRF-Token`, formulário `csrf_token` e JSON payload.
  - Validação CSRF e permissões em todas as rotas mutantes de segurança, configurações, publicações e sessões.
  - Endpoints de observabilidade protegidos: `/_luftbase/auditoria/logs-temp` (`ADMIN.AUDITORIA.VISUALIZAR`), `/_luftbase/sessoes/online` (`ADMIN.SESSOES.VISUALIZAR`) e `/_luftbase/sessoes/revogar` (`ADMIN.SESSOES.REVOGAR`).
- **Middleware de Manutenção e Respostas Padronizadas**:
  - Middleware de manutenção (`before_request`) com cache local de curto TTL, isenções operacionais (saúde, login, estáticos) e bypass para operadores (`ADMIN.MANUTENCAO.BYPASS`, `ADMIN.MANUTENCAO.GERENCIAR`).
  - Módulo `luftbase.web.respostas` padronizando contratos de resposta JSON, popups e toasts corporativos.
  - Handlers de erro 403, 404 e 500 com detecção automática de resposta JSON vs HTML.
- **Conteúdo e Publicações**:
  - Novos métodos em `RepositorioNotificacoes` e `ServicoNotificacoes`: `contar_nao_lidas` e `limpar_expiradas`.
  - Novos métodos em `RepositorioPublicacoes` e `ServicoPublicacoes`: `atualizar_rascunho`, `arquivar`, `listar_administracao`, `obter_administracao`, `importar_comunicado_externo` e `sincronizar_provedor`.
  - Inversão de captura de exceções em `publicacoes.py` (`ConteudoNaoEncontrado` -> 404 antes de `ErroConteudo` -> 400).
  - Inclusão dos arquivos `interface/static/video/*.json` no `package-data` do wheel.

- `LUFT_SISTEMA_ID` e a unica identidade de bootstrap; nao existe ID paralelo por aplicacao.
- O Vault usa `bancos/postgresql/conexoes/{alias}` para o servidor compartilhado e
  `bancos/postgresql/sistemas/{id}` para schema, role e metadados do sistema.
- Migration `20260917_0007` remove `identificador_aplicacao` de `core.tb_sistema`.
- CLI `migrar-layout-sistemas` copia segredos legados com CAS 0 e nao remove origens.
- Models particulares podem declarar politicas `EXTERNA_SOMENTE_LEITURA`, `VALIDAR` ou
  `GERENCIAR`; a verificacao e a criacao permanecem comandos explicitos.

## 0.1.0a3 — 2026-09-17

- `LUFT_SISTEMA_ID` tornou-se o unico bootstrap de identidade; o runtime valida o segredo canonico `bancos/postgresql/sistemas/{id}`.
- Suporte a `sslmode` PostgreSQL na credencial composta e na URL SQLAlchemy.
- CLI de operador tolera policies enxutas que podem usar KV v2 sem listar todos os mounts.
- Permissoes do sistema `0` passam a ser herdadas globalmente; escopo especifico prevalece e ausencia continua negada.
- Identidade visual oficial Luft incorporada ao LuftBase com shell lateral, paleta, componentes, logos e login institucional.
- Painel-base de administracao restabelece os dominios Segurança & Permissões, Publicacoes e Aplicacoes & Ambiente.

## 0.1.0a2 — 2026-09-16

- Resolucao de credenciais PostgreSQL compostas no Vault: conexoes compartilhadas (`bancos/postgresql/conexoes/{alias}`) e credenciais por aplicacao (`bancos/postgresql/aplicacoes/{id}`).
- Carregamento de identidade e metadados estaveis (`nome`, `descricao`, `ativo`, `em_manutencao`, `icone`, `link`) diretamente de `core.tb_sistema`.
- Eliminacao da redundancia de `LUFT_APLICACAO_NOME` no `.env` e `.env.example`, reduzindo configuracao repetida.
- Incorporacao do utilitario oficial de provisionamento e auditoria na CLI: subcomandos `luftbase vault postgresql auditar`, `provisionar`, `associar-sistemas` e `aplicar-senhas-do-vault`.
- Parser declarativo de manifestos de provisionamento YAML/JSON (`ManifestoProvisionamento`).
- Adaptador `ArmazenamentoSessoesMemoria` para testes e fallback gracioso em desenvolvimento/homologacao quando segredos Redis nao estiverem provisionados no Vault.
- Script idempotente de concessao de privilegios PostgreSQL no schema `core` com menor privilegio funcional (`luft_core_*`) e concessao ao runtime da aplicacao (`luft_workspace_app`).
- Validacao completa do piloto M10 com startup limpo de `Wsgi.py` no Luft-Workspace na porta 9010.

## 0.1.0a1 — 2026-09-16

- Fundacao documental do LuftBase.
- Configuracao tipada de aplicacao e Vault.
- Normalizacao de ambientes e caminhos de segredos.
- Extensao Flask minima para sustentar os proximos marcos.
- Cliente Vault KV v2 testavel e carregamento tardio de segredos.
- Compatibilidade com tokens Fernet existentes sem chave embutida no pacote.
- Credenciais imutaveis com senha mascarada e bloqueio de contas administrativas.
- Pools SQLAlchemy para SQL Server e PostgreSQL com `pool_pre_ping`.
- Fronteiras separadas para diretorio, schema `core` e schema da aplicacao.
- Unidade de trabalho com commit/rollback e teardown automatico no Flask.
- Health check sanitizado por dependencia.
- Base ORM unica com os 13 modelos migrados no schema `core`.
- Preferencia de usuario preparada para familias de tema e modos claro/escuro/sistema.
- Revisao persistente para invalidacao de caches distribuidos.
- Baseline Alembic reproduzivel e revisao separada para as duas tabelas novas.
- CLI segura para versao, validacao, adocao de baseline e atualizacao confirmada.
- Modelos SQL Server fixos de usuario e grupo, isolados das migrations do core.
- `UsuarioAutenticado` canonico e independente do ORM.
- LDAP somente com LDAPS ou STARTTLS, timeout e falha sanitizada.
- Interface de sessao server-side em JSON assinado, com TTL, rotacao e revogacao.
- Redis e chave de assinatura carregados do Vault, com TLS, timeouts e health check.
- Flask-Login por aplicacao e sessao compartilhada entre projetos sem consulta SQL recorrente.
- Autorizacao sob demanda por usuario e grupo, com negacao direta prevalecendo.
- Cache de permissao por requisicao e Redis, com invalidacao automatica por revisao.
- Decorator, consultas programaticas e helpers Jinja de autorizacao em portugues.
- Auditoria HTTP e de dominio separada do logging tecnico.
- Sanitizacao recursiva, ID de correlacao e metricas de baixa cardinalidade.
- Endpoints de prontidao e metricas, sem dados sensiveis.
- Migrations 0003 e 0004 para revisao de autorizacao e observabilidade.
- Servicos fixos de notificacoes e publicacoes, sem models fornecidos pelas aplicacoes.
- Audiencia por usuario/grupo, vigencia, recibos idempotentes e publicacao transacional.
- Feeds incrementais e SSE retomavel por cursor, com PostgreSQL como fonte definitiva.
- Sinal de ultimo cursor no Redis em melhor esforco e migration 0005 para indices de busca.
- Perfil web obrigatorio com template base, assets locais e macros acessiveis.
- Tokens semanticos e tema corporativo nos modos claro, escuro e sistema.
- Registro extensivel de manifestos, fallback controlado e preferencia persistida no core.
- Atualizacao de preferencia autenticada e protegida por CSRF, com retrato na sessao Redis.
- CLI corporativa `luftbase` via `[project.scripts]` e integracao unificada com a CLI do Flask (`app.cli`).
- `luftbase projeto criar`: scaffolding deterministico com pacote, factory, blueprint, templates e testes.
- `luftbase projeto deploy`: geracao de artefatos revisaveis de proxy reverso Nginx e servico NSSM.
- `luftbase banco historico` e `luftbase banco pendencias`: inspecao segura de revisoes Alembic.
- `luftbase diagnostico configuracao` e `luftbase diagnostico saude`: relatorios sanitizados de ambiente e saude.
- `luftbase vault caminhos` e `luftbase vault verificar`: validacao estrutural e teste seguro de segredos.
- `luftbase tema listar` e `luftbase tema validar`: listagem de temas e validacao estrita de tokens CSS.
- `FabricaInfraestruturaMemoria`: adaptador deterministico em memoria para viabilizar testes unitarios imediatos.
- Piloto M10 do Luft-Workspace sem models, conexoes ou injecoes sistemicas locais.
- Suporte ao sistema global de autorizacao com `LUFT_SISTEMA_ID=0`, mantendo negacao por padrao.
- Protecao CSRF compartilhada nas mutacoes de leitura de notificacoes e publicacoes.
