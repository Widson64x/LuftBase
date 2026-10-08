# Roadmap do LuftBase

Cada marco precisa atender seus criterios de aceite antes de ser marcado como concluido.
Estado em **2026-10-08**, versao `0.1.0a89`. Legenda: `[x]` feito e em uso, `[ ]` pendente.
O historico por versao esta no [CHANGELOG](CHANGELOG.md); a documentacao, em [docs/](docs/README.md).

Producao hoje: Luft-Workspace e Luft-Integrador (Windows). Homologacao: os tres sistemas (Linux).

## M00 — Fundacao documental

- [x] Registrar a missao e os limites do produto.
- [x] Criar regras permanentes para agentes e contribuidores.
- [x] Registrar as decisoes iniciais de arquitetura.
- [x] Inventariar as repeticoes mais relevantes dos projetos atuais.
- [x] Definir a API publica desejada.

## M01 — Pacote e configuracao

- [x] Criar pacote instalavel com layout `src`.
- [x] Padronizar Python 3.11 ou superior.
- [x] Criar modelo tipado de configuracao da aplicacao.
- [x] Normalizar aliases de ambiente.
- [x] Validar o identificador tecnico da aplicacao.
- [x] Resolver caminhos SQL Server e PostgreSQL no Vault.
- [x] Registrar a extensao no Flask sem estado global compartilhado.
- [x] Definir carregamento seguro dos segredos sem conectar no import.
- [x] Adicionar validacao completa de configuracao de producao.

## M02 — Vault e conexoes

- [x] Criar cliente Vault com contratos testaveis.
- [x] Ler `esquema` na credencial PostgreSQL.
- [x] Validar schema e impedir identificadores reservados.
- [x] Criar conexoes distintas para diretorio, core e aplicacao.
- [x] Implementar pool, `pool_pre_ping` e descarte.
- [x] Criar unidade de trabalho e teardown automatico.
- [x] Implementar health check por dependencia.

## M03 — Persistencia do core

- [x] Criar uma unica base ORM para as tabelas compartilhadas.
- [x] Mapear as 13 tabelas migradas em `core`.
- [x] Adicionar preferencia de usuario e revisao de cache.
- [x] Incorporar migrations Alembic ao pacote.
- [x] Criar comandos `banco versao`, `banco validar` e `banco atualizar`.

## M04 — Identidade e sessao corporativa

- [x] Criar modelos fixos de usuario e grupo para o diretorio corporativo.
- [x] Criar `UsuarioAutenticado` canonico.
- [x] Implementar LDAP com TLS configuravel.
- [x] Implementar sessao compartilhada e revogavel em Redis.
- [x] Centralizar cookies, SSO, renovacao e logout global.

## M05 — Autorizacao

- [x] Consultar somente as chaves solicitadas.
- [x] Implementar cache por requisicao e Redis.
- [x] Implementar invalidacao por revisao.
- [x] Criar decorators e contexto Jinja em portugues.
- [x] Implementar politica fail-closed.

## M06 — Auditoria e observabilidade

- [x] Encadear acesso HTTP, detalhe de dominio e retrato antes/depois.
- [x] Remover singletons e listeners globais.
- [x] Sanitizar dados sensiveis.
- [x] Adicionar correlacao, metricas, health e readiness.
- [x] Incorporar Auditoria como aba global do Painel de Controle.
- [x] Analisar acessos por sistema, usuario e grupo com escopo fail-closed.
- [x] Separar visualizacao, exportacao e dados sensiveis por permissao.

## M07 — Notificacoes e publicacoes

- [x] Reestruturar repositorios, servicos e rotas.
- [x] Implementar consultas incrementais e cache.
- [x] Preparar entrega via Redis/SSE sem perder o PostgreSQL como fonte definitiva.

## M08 — Design system e temas

- [x] Tornar o design system obrigatorio no perfil web.
- [x] Separar tema de modo claro/escuro/system.
- [x] Criar tokens semanticos.
- [x] Criar registro e manifesto de temas.
- [x] Persistir preferencia do usuario.
- [x] Adicionar testes visuais e de acessibilidade.

## M09 — CLI e scaffolding

- [x] Criar comandos de projeto, banco, Vault, diagnostico e temas.
- [x] Gerar aplicacoes novas conforme o padrao LuftBase.
- [x] Validar o conteudo do wheel.

## M10 — Piloto Luft-Workspace

- [x] Integrar e iniciar a pre-versao `0.1.0a4` no Workspace em Windows.
- [x] Remover models e inicializacoes sistemicas locais.
- [x] Centralizar bootstrap exclusivamente por `LUFT_SISTEMA_ID` e preservar a identidade visual.
- [x] Concluir e adotar a nova autorizacao hierarquica e catalogo de modulos (0.1.0a16).
- [x] Validar Windows (producao) e Linux (homologacao): fuso unico, driver ODBC, cookie, IP real.
- [ ] Medir desempenho e preparar rollback (plano de carga e procedimento de volta de versao) — ver M18.

## M12 — Integracoes corporativas

- [x] Liberar e-mail SMTP a partir do Vault, opcional por ambiente e validado na inicializacao.
- [x] Modo teste por segredo, envio em lote e auditoria por mensagem.
- [x] Layout e componentes padrao de e-mail no pacote.
- [x] Catalogo declarativo de modulos e permissoes para aplicacoes satelites.
- [x] Publicacao sob prefixo (`SCRIPT_NAME`) e ponte de `flash` para toasts.
- [x] Migrar o Luft-ConnectAir do LuftCore para o LuftBase (em homologacao).
- [ ] Publicar o Luft-ConnectAir em producao.
- [x] Migrar o Luft-Integrador do LuftCore para o LuftBase (em producao).
- [ ] Migrar o Luft-Control.

## M13 — Painel de Controle e operacao

- [x] Aba Integracoes: Vault, bancos, e-mail, LDAP e versoes, sem valores secretos.
- [x] Verificador de versao do LuftBase contra o GitHub.
- [x] Servicos do servidor (status, iniciar, parar, reiniciar) achados pelo nome do sistema, sem lista no `.env`.
- [x] Variaveis de ambiente editaveis por lista fechada, com validacao, copia e troca atomica.
- [x] Copiar permissoes entre usuarios em tres passos, com auditoria.
- [x] Caminho de navegacao com a casinha levando ao Workspace.
- [x] Provisionamento de sistemas por ambiente (schema, role, segredo) e `reprovisionar-sistema`.
- [ ] Alertas automaticos (e-mail ou sino) para erros 5xx e acessos negados em sequencia — ver M20.

## M14 — Identidade, sessao e perfil

- [x] Sessao compartilhada no PostgreSQL com eventos (`INICIO`, `RENOVACAO`, `LOGOUT`, `TIMEOUT`, `REVOGACAO`).
- [x] Logout global confiavel (sessao finalizada nunca reativa; cookie "lembrar" descartado).
- [x] IP real do usuario atras do nginx e navegador gravados por sessao.
- [x] Perfil: foto com editor de recorte, dispositivos conectados, historico de acessos e total de logins.
- [x] Horario unico de Brasilia em Windows e Linux.
- [ ] Aviso ao usuario quando a sessao e encerrada por um administrador — ver M19.
- [ ] Bloqueio de login de um usuario pela tela — ver M19.

## M15 — Auditoria analitica

- [x] Painel em secoes: visao geral, ao vivo, pessoas e sessoes, desempenho, seguranca e registros.
- [x] Drill-down estilo BI (clique filtra e leva aos registros; Shift+clique so filtra).
- [x] Controle de sessoes: encerrar uma, desconectar pessoa, desconectar todos.
- [x] Dados confiaveis desde um marco (`LUFT_AUDITORIA_DADOS_DESDE`).
- [ ] Retencao e arquivamento de logs antigos — ver M21.
- [ ] Agregador corporativo de logs para investigacoes com varios hosts (ADR-013).

## M16 — Comunicacao

- [x] Notas de atualizacao com markdown seguro, imagens, destaques e cards.
- [x] Nota global de lancamento, idempotente, com correcao de texto sem renotificar.

## M17 — Documentacao

- [x] Documentacao tecnica de identidade, painel, auditoria, perfil, servidor, variaveis, satelites e operacao.
- [ ] Atualizar `luftbase projeto criar` para gerar a estrutura do ADR-017.
- [ ] Documentar a API publica final (congelamento da 1.0).

## M18 — Validacao operacional

Por que: os apps instalam o LuftBase pela tag do GitHub (`luft-base @ git+...@v<versao>`). Uma tag ruim chega aos
quatro sistemas no proximo deploy, e hoje nao ha teste em Windows de verdade nem procedimento escrito de volta de versao.
O bug do horario 3 h adiantado (0.1.0a89) passou por isso: os testes cobriam Linux e o ramo Windows nao era exercitado.

- [x] CI do repositorio LuftBase em Windows e Linux (matriz do GitHub Actions): `ruff`, `pytest`, build do wheel e tag x versao.
      Os apps continuam com o `deploy.yml` como unico workflow. A primeira execucao no GitHub acontece no push da 0.1.0a90.
- [x] Lint zerado (`ruff check src tests`). `E501` ficou fora por ser so estilo; o resto era import e `Any` sem importar.
- [ ] `mypy` ainda tem 36 erros de tipo antigos (roda informativo no CI); zerar e torna-lo bloqueante.
- [x] Teste de fumaca por plataforma (`tests/test_fumaca_plataforma.py`): log fisico grava e le o horario de Brasilia; no
      Windows, `TZ` nao e alterado. Cobre tambem `/_luftbase/saude` e `/prontidao` (`tests/test_plataforma.py`).
- [x] Procedimento de rollback no doc 20 (voltar a tag no `requirements.txt` e redeployar; nao desfazer migracao).
- [x] Regra testada "migracao nova e aditiva" (`tests/test_migracoes_aditivas.py`, vale apos `20260923_0013`).
- [x] Ordem de promocao (homologacao primeiro) escrita no doc 20.
- [x] Ferramenta de carga `tools/carga.py` (p50/p95/p99, erro e codigo de saida), testada contra um servidor local.
      Meta inicial: 100 usuarios, p95 ate 3000 ms, erro abaixo de 1%.
- [ ] Rodar a carga em homologacao e registrar o primeiro resultado real (precisa de cookie de sessao de teste).
- [ ] Ensaiar o rollback uma vez em homologacao.

Aceite: tag publicada so com CI verde nos dois sistemas; rollback ensaiado uma vez em homologacao e descrito no doc 20.

## M19 — Gestao de acesso e avisos ao usuario

Por que: `core.tb_usuario` ja tem `bloqueado` e `motivo_bloqueio`, mas **nenhum login le essas colunas** (so sao gravadas
como `False` na criacao, em `identidade/repositorio_core.py`). A sessao encerrada por admin ja registra `REVOGADA_ADMIN`, mas a
pessoa so descobre ao cair na tela de entrada. E quem recebe acesso a um sistema hoje nao e avisado de nada.

### Acesso liberado: e-mail e notificacao

Quando alguem recebe a permissao base de um sistema (`PLATAFORMA.SISTEMA.ACESSAR` e a equivalente de cada sistema, como
`CONNECTAIR.SISTEMA.ACESSAR`; o codigo usa a marcada `eh_acesso_sistema`), a pessoa e avisada de duas formas:

1. **E-mail** "Seu acesso ao <Sistema> foi liberado", com o nome do sistema e um botao/link para abri-lo. Usa o modulo de
   e-mail do LuftBase (layout padrao, modo teste, auditoria por mensagem).
2. **Notificacao global** gravada em `tb_notificacao`, direcionada so a esse usuario (escopo global, `id_usuario_destino`),
   com o link do sistema; aparece no sino e abre o sistema ao clicar.

Regras:
- vale **so para a permissao base de acesso ao sistema**; as demais permissoes nao disparam aviso;
- dispara na **transicao** de "sem acesso" para "com acesso": salvar de novo, conceder algo ja concedido ou revogar nao envia;
- concessao a **grupo** avisa cada membro que ainda nao tinha acesso; copiar permissoes entre usuarios tambem avisa;
- a pessoa precisa ter e-mail cadastrado; sem e-mail, so a notificacao e o fato fica registrado na auditoria;
- falha de e-mail ou de notificacao **nunca desfaz** a concessao: a permissao grava e o erro vai para o log e a auditoria;
- sem repeticao: como so a transicao "sem acesso -> com acesso" avisa, salvar a mesma regra de novo nao envia outra vez.

- [x] Endereco do sistema no e-mail: nao precisou de coluna nova. Usa `Sistema.link` (ja existe no cadastro): absoluto como
      esta; relativo, preso a `LUFT_URL_PUBLICA` (opcional) ou ao host da requisicao de quem libera o acesso.
- [x] Servico de aviso (`autorizacao/aviso_acesso.py`): foto do acesso antes/depois, avisa so a transicao sem -> com acesso.
- [x] Ligado em `salvar` (usuario e grupo) e em espelhar permissoes (`web/seguranca.py`).
- [x] Modelo de e-mail `acesso_liberado.html` (mesmo layout dos demais).
- [x] Testes: transicao dispara uma vez; so a permissao base; bloquear nao avisa; grupo avisa so quem ainda nao tinha;
      sem e-mail; usuario bloqueado; SMTP fora nao desfaz a concessao; limite por operacao; modelo renderizado.
- [x] Documentado nos docs 11 e 13 e em `LUFT_URL_PUBLICA` (doc 18).
- [ ] Ensaiar em homologacao: conceder `PLATAFORMA.SISTEMA.ACESSAR` a um usuario de teste e conferir e-mail e sino.

### Bloqueio de login e aviso de sessao encerrada

- [x] Bloqueio fail-closed no login (`ServicoAutenticacao`): senha certa + bloqueado = 403 com mensagem sem motivo interno e
      `LOGIN_BLOQUEADO` na auditoria; falha ao conferir = 503 "indisponivel", nunca entrada liberada.
- [x] Bloquear derruba as sessoes ativas da pessoa (motivo `BLOQUEIO_ADMIN`); o cookie "lembrar" ja nao existe (sessao no servidor).
- [x] Botao "Bloquear acesso" / "Desbloquear acesso" no Gerenciador de Permissoes (modo Usuario): motivo obrigatorio, permissao
      `SEGURANCA.USUARIOS.DESATIVAR` (rode `luftbase catalogo sincronizar` nos ambientes), auditoria, sem auto-bloqueio.
- [x] Aviso na tela de entrada ("Sua sessao foi encerrada por um administrador" / bloqueio), uma unica vez.
- [x] Testes (`tests/test_bloqueio_login.py`) e docs 10 e 11.
- [ ] Atalho na Auditoria > Pessoas e sessoes (hoje o botao esta so no Gerenciador de Permissoes).
- [ ] Notificacao/e-mail para a pessoa bloqueada: nao feito de proposito (sem acesso ela nem consegue ver o sino).

Aceite: quem recebe acesso a um sistema ganha e-mail e notificacao uma unica vez; usuario bloqueado nao entra por nenhum caminho; tudo auditado.

## M20 — Alertas para o desenvolvedor

Por que: hoje o erro so aparece se alguem abrir a Auditoria. O desenvolvedor passa a ser avisado sozinho, com **quem** teve
o problema e **o que** aconteceu. Reaproveita `ServicoInsights`, `tempo_real`, o e-mail e as notificacoes.

O que dispara alerta:

| Gatilho | Exemplo de aviso |
|---|---|
| Erro 5xx | "widson.araujo: 3 erros 500 em /planejamento/salvar nos ultimos 10 min (Luft-ConnectAir)" |
| Erro 4xx em sequencia (401, 403, 404, 422) | "maria.silva: 8 respostas 403 em 5 min; ultima rota /configuracoes/usuarios (Luft-Workspace)" |
| Evento critico | acao com severidade `ALTA` ou `CRITICA` na trilha de eventos |
| Aplicacao fora do ar ou lenta | sem acesso por N min em horario comercial; p95 acima do limite |
| Falha tecnica | falha ao gravar o log fisico, falha de e-mail, falha de conexao com o banco |

Cada aviso traz: sistema, ambiente, usuario (login), IP, rota normalizada, status, contagem, janela, primeira e ultima ocorrencia
e o id de correlacao para abrir direto no registro da Auditoria. **Nunca** inclui corpo de requisicao, senha, token nem dado
de formulario (reaproveita a sanitizacao existente).

Como funciona:
- Um unico erro isolado gera **um aviso imediato** para 5xx e eventos criticos; 4xx so alerta em **sequencia** (limite abaixo),
  porque um 404 solto e ruido.
- Antirruido: alerta aberto nao se repete antes do intervalo de silencio; ocorrencias novas somam no mesmo alerta e viram um
  resumo; fecha sozinho quando a condicao some.
- Limites iniciais assumidos (ajustaveis no Painel): 5xx = qualquer ocorrencia, resumo a cada 15 min; 4xx = 10 respostas iguais
  do mesmo usuario em 5 min; lentidao = p95 acima de 3 s por 10 min; fora do ar = 10 min sem acesso, das 07h as 19h.
- Destino: **e-mail do desenvolvedor** (lista configuravel por sistema) e **notificacao no sino** para quem tem a permissao
  `AUDITORIA.ALERTAS.RECEBER`. O seu e-mail entra como destinatario inicial.
- Roda como **tarefa agendada** no servidor (`luftbase alertas avaliar`, a cada minuto): um unico executor, sem trava no banco,
  fora do request, com janela curta e os indices que a Auditoria ja usa. Nunca atrasa nem derruba uma requisicao.

- [ ] Regras declarativas (`observabilidade/alertas.py`) com janela, limite e escopo por sistema.
- [ ] Tabela `core.tb_alerta` (regra, sistema, usuario, rota, status, contagem, aberto_em, ultima_ocorrencia, resolvido_em,
      ultima_notificacao); migracao Alembic aditiva.
- [ ] Avaliador `luftbase alertas avaliar` e a receita para agendar no Windows (Agendador de Tarefas) e no Linux (systemd timer).
- [ ] Mensagem do alerta com usuario, rota, contagem e correlacao, sem dado sensivel.
- [ ] Destinos: e-mail por sistema e sino por permissao; modo teste do e-mail respeitado.
- [ ] Aba "Alertas" na Auditoria: abertos, historico, silenciar por X horas, ligar/desligar regra e editar limite.
- [ ] Testes com relogio injetavel: dispara, soma, nao repete, fecha, respeita escopo e nao vaza dado sensivel.
- [ ] Documentar no doc 12 e variaveis novas no doc 18.

Aceite: um pico simulado de 5xx e outro de 403 em homologacao geram um alerta cada, com usuario e rota, enviados por e-mail e sino,
e fecham sozinhos.

## M21 — Retencao e arquivamento de logs

Por que: o log fisico rotaciona (30 arquivos diarios), mas `tb_logs`, `tb_logevento`, `tb_logdetalhe`, `tb_sessao` e
`tb_sessao_evento` crescem sem limite e sao a base das consultas da Auditoria.

- [ ] Medir antes: `luftbase banco tamanho-logs` (linhas e MB por tabela e crescimento por semana).
- [ ] Politica por tabela em variaveis (`LUFT_RETENCAO_*_DIAS`, doc 18). Valores iniciais assumidos ate a medicao:
      acesso HTTP 180 dias, sessoes 365, eventos e retrato antes/depois (trilha de alteracao) 730 (ajustar se houver exigencia legal).
- [ ] Arquivar antes de apagar: exportar o lote vencido para tabelas `*_arquivo` em schema separado e so entao remover, em lotes
      pequenos com `COMMIT` por lote, na ordem `tb_logdetalhe` -> `tb_logevento` -> `tb_logs`, sem quebrar a trilha encadeada.
- [ ] Comando `luftbase banco retencao [--simular|--executar]`: o padrao e simular (nao apaga); a execucao e auditada e agendavel.
- [ ] A Auditoria avisa quando o periodo pedido passa da retencao (mesma ideia de `LUFT_AUDITORIA_DADOS_DESDE`).
- [ ] Testes da ordem de remocao, do lote e do modo simular; ensaio em homologacao antes de producao.

Aceite: `--simular` em homologacao lista o volume por tabela; `--executar` reduz o tamanho sem quebrar a Auditoria nem a trilha.

## Ordem de execucao dos marcos M18 a M21

1. **M18** primeiro: reduz o risco de tudo o que vem depois (CI e rollback antes de mexer em login e banco).
2. **M19** (acesso liberado + bloqueio): baixo risco, alto valor e fecha a lacuna do bloqueio.
3. **M20** (alertas ao desenvolvedor).
4. **M21** por ultimo: apaga dados, so depois de medir e de simular em homologacao.

Cada marco e publicado em versoes proprias (LuftBase na `main` com tag, depois os apps em homologacao), com CHANGELOG e docs
atualizados no mesmo commit. Producao so por pedido seu.

Riscos: o lint real pode alongar o M18; a migracao de `url_acesso` e de `tb_alerta` e aditiva, mas precisa de `banco atualizar`
em cada ambiente antes do app novo; M21 apaga dado de auditoria e nunca roda no primeiro deploy do marco.

## M11 — Estabilizacao 1.0

- [ ] Publicar alpha, beta e release candidate.
- [ ] Congelar a API publica.
- [x] Concluir documentacao operacional (docs 14 a 21).
- [ ] Publicar `1.0.0` somente depois do piloto homologado.
