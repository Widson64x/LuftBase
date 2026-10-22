# Registro de Alterações (ChangeLog) - LuftBase

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

## [0.1.0a124] - 2026-10-22

### Corrigido

- A pergunta "enviar e-mail?" nao aparecia ao permitir uma permissao **mae** da base (ex.: `PLATAFORMA.SISTEMA.ADMINISTRAR`, que libera `ACESSAR` por heranca) e o
  e-mail saia direto. Agora vale para a permissao base e para todas as ancestrais dela.

## [0.1.0a123] - 2026-10-22

### Adicionado

- **Perguntar antes de enviar o e-mail de acesso liberado**: ao permitir a permissao base de um sistema, a tela do Gerenciador pergunta "Salvar e enviar e-mail",
  "Salvar sem e-mail" (a notificacao interna sai igual) ou "Cancelar", e so grava depois da resposta. So pergunta quando alguem realmente vai ganhar acesso e o
  e-mail esta configurado. No espelhamento de permissoes ha a caixa "Avisar por e-mail quem ganhar acesso". A API continua avisando como antes, a menos que
  envie `AvisarEmail: false` (ou `avisar_email: false`).

## [0.1.0a122] - 2026-10-22

### Adicionado

- **Auditoria & Analise v2**: aba **Alertas** junto de Rotas HTTP/Sessoes/Eventos/Logs fisicos (situacao com contagens, busca, silenciar 1/8/24 h, reativar,
  gaveta de detalhes), KPI "Alertas abertos" e insignias; chave **Tempo real** (30 s, so com a aba visivel); "Atualizado ha X s"; no Ao vivo, "expira em".
- Filtros se aplicam sozinhos, barra compacta com **Mais filtros** e **Limpar**; uma consulta nova cancela a anterior.
- API: `GET /auditoria/api/alertas` com `situacao/termo/pagina/tamanho/sistema_id`, `GET /opcoes`, `/resumo?opcoes=0` e contagem de alertas.

### Alterado

- Cache de 15 s (resumo e insights) e 60 s (listas de filtros) por aplicacao, janelas arredondadas a 15 s; Atualizar sempre recalcula (`?fresco=1`).

## [0.1.0a121] - 2026-10-22

### Corrigido

- **Sessao "ativa" por quase 2 dias sem uso**: a expiracao so acontecia quando alguem usava o cookie, entao quem fechava o navegador deixava a sessao `ATIVA` indefinidamente (aparecia em "Ao vivo" como ocioso ha 38 h). Agora uma **varredura** (no maximo 1 vez por minuto por processo, ao gravar uma sessao e ao listar quem esta online) encerra toda sessao vencida: `EXPIRADA`, motivo `TIMEOUT_INATIVIDADE`, `encerrada_em` = quando venceu, payload apagado, evento `TIMEOUT` e a pessoa sai de "online". O `luftbase.log` registra quem teve a sessao encerrada.
- O evento `TIMEOUT` dizia "> 10 min sem acao" qualquer que fosse o prazo; agora informa o prazo real.

### Alterado

- **Piso de 30 minutos** para `LUFT_SESSAO_TTL_MINUTOS`: valores menores (ex.: 15) sobem para 30 com um aviso no log (a aplicacao nao deixa de subir) e o painel recusa gravar menos que isso. Quem entra tem a sessao garantida por, no minimo, 30 minutos sem atividade.
- **"Lembrar acesso" passa de 30 dias para 1 dia** sem atividade (`LUFT_SESSAO_LEMBRAR_DIAS`, padrao 1). Quem precisar de mais, define a variavel.

## [0.1.0a120] - 2026-10-22

### Corrigido

- **Logs fisicos cortavam a mensagem e a tabela nao rolava na horizontal**: a mensagem tinha largura fixa maior que a coluna e a celula escondia o excesso. Agora a mensagem ocupa o espaco que sobra (ate 2 linhas, sem corte) e a tabela tem largura minima de 980 px, entao em telas estreitas rola na horizontal (a barra fica a vista, dentro da area de altura limitada da 0.1.0a119).

## [0.1.0a119] - 2026-10-22

### Corrigido

- **Tabelas da Auditoria sem barra de rolagem horizontal a vista**: a area da tabela crescia com o numero de linhas e a barra ficava no fim da lista, fora da tela. Agora a area tem altura maxima (68% da tela), com rolagem nos dois sentidos e cabecalho fixo. A mensagem dos logs fisicos ficou um pouco mais estreita, para caberem mais colunas.

## [0.1.0a118] - 2026-10-22

### Alterado

- **Logs fisicos reformulados**: as abas *Raiz temporaria* e *Arquivos fisicos* viraram **uma so, "Logs fisicos"**, com o seletor *LuftBase | Aplicacao*, filtro de nivel e de arquivo. A gaveta de detalhes mostra a mensagem inteira. A rota `GET .../auditoria/temporarios` foi **removida**; `.../fisicos` aceita `fonte`, `nivel`, `termo` e `arquivo`.
- **`luftbase.log` agora e um diario de mensagens, nao de rotas**: as linhas `GET /x 200` sairam (ficam em *Rotas HTTP*). Entram as mensagens de todos os modulos do LuftBase (`logging` em `luftbase.*`), com o **usuario e o id de correlacao** da requisicao e a area de origem (`[EMAIL]`, `[ACESSO]`...); os eventos de auditoria saem como a frase da descricao; os erros 500 saem legiveis (`Erro interno do servidor em GET /x: ProgrammingError | causa: ... | origem: ...`).
- **Seguranca do arquivo**: excecoes aparecem so como tipos e local (sem mensagem bruta nem pilha); segredos em texto livre (`senha=`, `token:`, `://u:s@`, tokens do Vault) sao mascarados.
- O painel le tambem o **`application.log`** da aplicacao (formato `data | NIVEL | origem | mensagem`) e junta as linhas de pilha de erro na mensagem anterior.

### Adicionado

- **Mais logs do que o LuftBase faz**: subida da plataforma (versao, sistema, ambiente, sessoes, e-mail); **e-mails** enviados ou recusados (assunto e destinatarios mascarados); **aviso de acesso liberado** (alvo: usuario ou *grupo com N pessoas*, quem ganhou acesso, notificacoes e e-mails, sem e-mail, modo teste); notificacoes criadas (para quem); publicacoes publicadas (quantas notificacoes); alertas tecnicos enviados.
- `mascarar_texto` e `resumir_excecao` em `observabilidade/sanitizacao.py`; `mascarar_endereco` e `resumir_enderecos` em `integracoes/email/enderecos.py`.

### Removido

- **Raiz temporaria**: `BufferLogsTemporarios`, `RegistroLogTemp`, os arquivos `Logs/temp/*.temp.log` e a escrita de rotas no arquivo. Os arquivos `temp/` antigos podem ser apagados.

### Corrigido

- Mensagens de conveniencia da auditoria (`info`, `aviso`, `erro` com `salvar_banco`) saiam **duas vezes** no arquivo; agora uma so.

## [0.1.0a117] - 2026-10-21

### Alterado

- **Destinatario dos alertas tecnicos**: `DESTINATARIOS_ALERTA` passa de `widson.araujo@luftlogistics.com` para `sistemas.web@luftlogistics.com` (caixa da equipe). Continua fixo no codigo.
- **Nota global da plataforma reescrita** (`conteudo/changelog_plataforma.py`): agora cobre os **cinco sistemas ja migrados** (Workspace, ConnectAir, Integrador, Control e Docs, com as datas) e ganhou secoes sobre o Hub, o acesso liberado, o perfil, a protecao da conta, as notificacoes, os comunicados como e-mails, a busca, os temas, o Painel de Controle, perguntas frequentes e glossario. Passou de 156 para ~400 linhas, de 14 para 29 imagens e de 10 para 21 itens por categoria. O titulo mudou; o anterior segue reconhecido (`TITULOS_ANTERIORES`), entao a nota ja criada e atualizada, nao duplicada.
- **Imagens**: `banner`, `antes-depois`, `linha-do-tempo`, `login-unico` e `tela-hub` foram refeitas (o Control deixou de ser "o proximo a migrar") e ha 11 novas. O gerador novo `tools/gerar_imagens_changelog_sistemas.py` as produz; as 5 antigas saem de `tools/gerar_imagens_changelog.py`, para uma execucao nao desfazer a outra.

### Corrigido

- **Abrir no editor uma publicacao em markdown perdia a formatacao**: os destaques (`:::alerta`...) e os cards viravam texto solto porque o sanitizador descarta as classes `md-*`. `conteudo_para_editor` converte destaques em caixas coloridas e cards em secoes antes de abrir o editor.

## [0.1.0a116] - 2026-10-21

### Corrigido

- **Editor estourava a largura do modal** ao abrir uma publicacao com conteudo largo (tabelas e blocos de codigo): o formulario era uma grade sem `minmax(0, 1fr)`. Agora o editor fica dentro do modal e a area de texto rola por dentro.
- **Aviso de editor vazio sobreposto ao texto**: ao abrir um rascunho so com texto, o editor se achava vazio porque `innerText` ignora o que esta com `visibility: hidden` (modal fechado). A checagem passou a usar o `textContent` nesse caso.
- Tabelas largas na leitura passam a rolar na horizontal em vez de alargar a pagina.

## [0.1.0a115] - 2026-10-21

### Corrigido

- **Tabelas dos comunicados**: o cabecalho de colunas estreitas (ex.: "Atalho") quebrava no meio da palavra; as celulas passam a quebrar so entre palavras.

## [0.1.0a114] - 2026-10-21

### Adicionado

- **Bloco de codigo (`pre`)** no HTML do editor: preserva espacos e quebras de linha; o conteudo continua sanitizado.
- **Nota global da plataforma** (`conteudo/changelog_plataforma.py`): nova secao sobre os comunicados como e-mails (3 imagens novas em `img/changelog`), lista de itens por categoria (`ITENS`) e parametros `criado_por` e `criado_por_id` em `nova_publicacao` e `publicar_changelog_plataforma`.

### Alterado

- **Painel de publicacoes mais leve**: a lista nao embute mais o texto completo (`conteudo` e `conteudo_editor`) de cada publicacao; ele vem de `GET /publicacoes/api/publicacoes/<id>` so ao clicar em Editar. Publicacoes muito grandes deixam de pesar a pagina.

## [Nao lancado]

### Documentacao

- Script `tools/sql/20261021_publicacao_conteudo_rico.sql` (equivale a migracao `20261021_0018`) e aviso no doc 20: `banco atualizar` exige usuario dono das tabelas do `core`.

## [0.1.0a113] - 2026-10-21

### Adicionado

- **Editor rico de comunicados e notas de atualizacao (estilo e-mail)**: o campo de texto virou um editor visual com estilo (paragrafo, titulo, subtitulo, secao), tamanho da letra, negrito, italico, sublinhado, tachado, cor do texto, marca-texto, alinhamento, listas, citacao, linha divisoria, destaques (informacao, sucesso, alerta, perigo), links, tabelas e **imagens** (botao, colar ou arrastar; PNG, JPEG, GIF ou WebP de ate 5 MB, reduzidas no navegador quando passam de 1600 px). Aba "Pre-visualizar" mostra o que o leitor vera, ja sanitizado pelo servidor.
- **Formato do conteudo**: `tb_publicacao.formato_conteudo` (`MARKDOWN` ou `HTML`). O conteudo existente continua em markdown e segue funcionando; ao abrir uma publicacao antiga para editar, ela e convertida para o editor e passa a ser salva como HTML.
- **Sanitizador de HTML de lista fechada** (`conteudo/html_seguro.py`): so tags, atributos e estilos conhecidos; sem `script`, eventos (`onclick`...), `javascript:` ou `data:`; imagens so internas, estaticas do LuftBase ou `https://`.
- **Imagens das publicacoes** em `core.tb_publicacaoimagem` (migracao `20261021_0018`, aditiva), entregues por `GET /publicacoes/imagem/<id>` a quem pode ver a publicacao (ou a quem gere publicacoes), com `nosniff` e cache privado.
- Rotas `POST /publicacoes/api/imagens` (upload) e `POST /publicacoes/api/previa`.
- **Resumo automatico**: sem resumo, o LuftBase gera um texto limpo (sem marcacao) a partir da mensagem; ele tambem e a mensagem da notificacao (antes a notificacao podia sair com o texto cru).

### Alterado

- **Telas de publicacao renovadas**: caixa de entrada (fixados no topo, mais novo primeiro, ponto de nao lido, autor e data), leitura como e-mail (remetente, data, audiencia, imprimir) e painel com indicadores por situacao que tambem filtram a lista. Corpo do texto com estilo unico entre editor, previa e leitura; tema escuro.
- O feed de quem le agora ordena do mais novo para o mais antigo (antes vinha do mais antigo).

### Corrigido

- **Editar rascunho dava erro 405**: a tela enviava `PUT` e a rota so aceitava `POST`; agora aceita os dois.
- A leitura de uma nota de atualizacao nao mostrava os itens do changelog ("O que mudou") nem o autor real.
- Publicacao sem resumo aparecia em branco no feed.

### Documentacao
- Novo [doc 28](docs/28-TUTORIAL-PRATICO-DO-DESENVOLVEDOR.md): tutorial pratico (sistema de exemplo executado com testes) e roteiro de migracao de sistema legado.
- Corrigido que o CSRF nao e automatico nas rotas da aplicacao (docs 10 e 19); README com Control e Docs; docs 20 e 26 com mapa de portas e erros de subida.

## [0.1.0a112] - 2026-10-19

### Corrigido

- **Segredo de e-mail invalido derrubava a aplicacao na subida**: `luft/<ambiente>/integracoes/email` presente mas com campo
  faltando ou invalido (ex.: sem `senha`) levantava `ErroCredencial` e a aplicacao nao iniciava (todas as apps do ambiente,
  em qualquer reinicio). Agora o e-mail e acessorio: a aplicacao sobe, registra um aviso no log (so caminho e campo, nunca o
  valor) e o envio fica indisponivel; as telas ja informam "o e-mail nao esta configurado neste ambiente".

### Documentacao

- Novos documentos 14 a 21: Painel de Controle, auditoria analitica e controle de sessoes, perfil, servidor/rede/fuso,
  referencia de variaveis de ambiente, guia da aplicacao satelite, operacao e deploy, conteudo rico.
- `10-IDENTIDADE-E-SESSAO.md` reescrito (a sessao fica no PostgreSQL; o Redis e opcional).
- `README.md`, `ROADMAP.md`, `HANDOFF.md` e o indice de `docs/` atualizados; nota sobre os nomes atuais das tabelas de log
  no doc 12.

## [0.1.0a111] - 2026-10-15

### Corrigido

- **Erro 500 ao salvar a edicao de sistema (regressao da 0.1.0a110)**: a consulta da permissao de desativar rodava dentro da
  transacao de escrita e, por usar a mesma sessao do `core`, a fechava ("Can't operate on closed transaction"). A permissao
  agora e consultada antes de abrir a transacao.

## [0.1.0a110] - 2026-10-15

### Corrigido

- **Desativar sistema nao persistia**: a checagem da permissao `CONFIGURACOES.SISTEMAS.DESATIVAR` rodava no meio da gravacao e
  fazia `abort(403)`, descartando a edicao inteira sem aviso. Agora e feita antes de qualquer alteracao e devolve JSON com a
  mensagem "Voce nao tem permissao para desativar ou reativar sistemas." (nada e salvo pela metade).

### Alterado

- Painel de Controle: o checkbox "Ativo no Catalogo" fica desabilitado para quem nao tem a permissao de desativar.
- Card de sistema desativado: borda tracejada, conteudo esmaecido, selo "DESATIVADO - OCULTO NO HUB", status "Desativado" e
  interruptor de operacao travado. O Hub ja escondia sistemas inativos (`Sistema.ativo`).

## [0.1.0a109] - 2026-10-15

### Documentacao

- **Novos documentos 22 a 27**: guia rapido do desenvolvedor (do zero a producao), referencia completa da CLI, sistemas e catalogo,
  banco local e promocao de estrutura, solucao de problemas (com as mensagens reais) e glossario.
- **Revistos**: `README.md` (porta de entrada), `docs/README.md` (indice por finalidade, com o ADR-010 marcado como rejeitado), visao do
  produto, arquitetura (diagramas Mermaid de camadas, inicializacao e requisicao), banco e schemas (tabelas do `core`, um banco por
  ambiente), padroes e contribuicao (portao de qualidade e receitas), API publica (mapa de tudo o que `luftbase` exporta), Painel de Controle,
  design system (componentes e seletor de icones), guia da aplicacao satelite e operacao e deploy.
- **Correcoes**: caminho do Flask no Windows em `20-OPERACAO-E-DEPLOY.md` (um `\f` virou caractere de controle); Redis nao e mais descrito
  como armazenamento padrao de sessao; preferencia visual esta em `core.tb_usuario`; nomes atuais das tabelas de auditoria no doc 03;
  "mais de 240 icones" trocado pela contagem real (225).
- Marco **M22** no ROADMAP; HANDOFF com o estado real e o proximo passo.

### Adicionado

- **Tipos de sistema** (ADR-018): `tb_sistema.integra_luftbase`, `tipo_acesso` (`WEB`/`DOWNLOAD`/`SEM_ACESSO`) e `url_download`
  (migracao `20261015_0016`, aditiva; rodar `banco atualizar`). Modais de cadastro e edicao do Painel ganham a escolha e o
  card mostra o selo EXTERNO. Externo nao tem schema, role nem segredo.
- `luftbase sistema externo`: cadastra ferramenta externa (C#, executavel, terceiros).
- `luftbase projeto novo`: pasta no padrao ADR-017 + sistema, schema, role, segredo no Vault e `.env`, em um comando.
- `luftbase banco espelhar`: copia integral de homologacao para o PostgreSQL local; `LUFT_BANCO_LOCAL_HOST/PORTA` apontam a
  aplicacao para ele (so loopback, nunca producao). O espelho se chama, por padrao, como a origem com `_dev` no lugar de
  `_hml` (`luft_web_dev`), e `LUFT_BANCO_LOCAL_NOME` leva o nome para a aplicacao. `--via-wsl` roda `pg_dump`/`pg_restore`
  no WSL.

- `luftbase banco comparar`: compara a estrutura dos schemas entre dois ambientes (desenvolvimento -> homologacao ->
  producao) e escreve um `.sql` por schema com o que falta no destino. So le o catalogo, nunca dados; o script so cria
  (`IF NOT EXISTS`), nao tem `DROP` nem altera tipo/nulidade/padrao (isso vai para "revisao manual" no relatorio) e roda
  em uma transacao. Nada e aplicado pelo comando: o dev revisa, roda em homologacao e depois o mesmo arquivo em producao.
- **Seletor de icones redesenhado** (`LuftBase.abrirSeletorIcones`): busca com largura total, botao de limpar e sem diferenciar
  acento ou maiuscula (varias palavras exigem todas; Enter aplica o unico resultado; Esc limpa antes de fechar); segmentos em
  linhas, sem barra de rolagem horizontal, e com icones Phosphor no lugar de emoji; subtitulo e contador com a contagem real;
  nomes em ate duas linhas; cartoes acessiveis (botoes com `aria-selected`), duplo clique aplica e o icone ja escolhido e
  rolado para a vista. Estilos saem do JS inline para `components.css` (tema escuro e movimento reduzido incluidos).
- **Catalogo de icones corrigido**: 5 nomes nao existiam no Phosphor e apareciam como cartao vazio (`forklift`, `safe`, `server`,
  `gears`, `thumbs-up-bold`); trocados por `truck-trailer`, `lock-simple`, `stack`, `gear-six` e `seal-check`. Quem ja salvou um
  desses nomes em `tb_sistema.icone` continua vendo icone vazio ate editar o sistema.
- **Categorias de sistema** ampliadas e escolhidas por cartoes (Painel de Controle > Sistemas): Aplicacao web, API, Servico /
  Daemon, Ferramenta / Executavel, Relatorios e paineis, Integracao / Conector e Hub. A lista vive em
  `persistencia/core/categorias_sistema.py` e e usada pelo CHECK do banco, pela validacao, pela CLI e pela tela; o card mostra
  rotulo, icone e cor da categoria. Escolher Ferramenta num cadastro novo sugere "externo + download". Migracao `20261015_0017`
  (alarga o CHECK; rode `banco atualizar` ou `tools/sql/20261015_tb_sistema_categorias.sql`, depois do script da `0016`).
- `luftbase banco atualizar-core` (so desenvolvimento): leva o core local, tipicamente copiado de homologacao, a revisao deste
  LuftBase com o usuario administrativo informado, sem subir uma aplicacao. `projeto novo` e `sistema externo` agora conferem a
  revisao do core antes de gravar e orientam a rodar esse comando, em vez do erro cru de coluna inexistente.
- `tools/sql/20261015_tb_sistema_tipo_de_integracao.sql`: script SQL repetivel e transacional para criar as colunas novas de
  `tb_sistema` a mao em homologacao e producao (carimba a revisao 20261015_0016 so se o core estiver na 20261008_0015). A migracao
  `0016` passou a tolerar colunas ja existentes, entao a ordem script/`banco atualizar` nao importa.
- `banco espelhar` tambem espelha o Vault de desenvolvimento: para cada sistema com schema do core copiado cria a role
  `luft_<schema>_dev_app` (senha aleatoria, nunca exibida) e o segredo `luft/desenvolvimento/bancos/postgresql/sistemas/<id>`.
  Segredo existente que bate e mantido; o que aponta para outro schema/role e conflito e so e trocado com
  `--substituir-segredos`; `--sem-vault` pula a etapa. Nunca escreve em homologacao ou producao.
- `banco espelhar`: depois da copia, as roles locais `luft_<schema>_dev_app` recebem acesso ao core e ao schema restaurado (o
  dump so traz permissoes das roles de homologacao).
- `banco espelhar`: role que ja existe no PostgreSQL local **mantem a senha local** (antes o espelho a trocava pela de
  homologacao, o que podia travar o acesso do dev, ex.: ao dono do banco); `--sobrescrever-senhas` restaura o comportamento antigo.
- `banco espelhar --somente-estrutura`: copia so a estrutura (banco limpo, sem usuarios, sessoes nem logs).

### Alterado

- `luftbase projeto criar NOME` passa a gerar a estrutura da ADR-017 (antes, o esqueleto antigo `src/<pacote>`); `--sistema-id`
  e opcional. O `nssm.ps1` gerado executa `Wsgi.py`.

## [0.1.0a108] - 2026-10-15

### Alterado

- **Bloco de origem do e-mail com rotulos**: passa a mostrar "Ambiente: Homologacao", "Aplicacao: v0.1.1a01" e
  "LuftBase: 0.1.0a108", uma por linha, no canto inferior direito.

## [0.1.0a107] - 2026-10-15

### Corrigido

- **Nome do remetente voltou a respeitar o Vault**: o `nome_remetente` do segredo `integracoes/email` agora vence o
  nome da aplicacao. Antes, o e-mail saia como "Luft-Workspace" mesmo com `"nome_remetente": "LuftBase"` no segredo.
  Ordem atual: parametro do envio, `nome_remetente` do Vault, nome do sistema, "Luft Logistics". Segredo sem
  `nome_remetente` continua usando o nome do sistema.

## [0.1.0a106] - 2026-10-15

### Alterado

- **Origem do e-mail no canto inferior direito**: o bloco empilhado (ambiente, versao do projeto, versao do LuftBase e
  link) vai para o canto inferior direito do rodape. O nome do sistema saiu do canto superior direito do cabecalho,
  que fica so com o logo; o bloco `titulo_cabecalho` do layout base foi removido.

## [0.1.0a105] - 2026-10-15

### Alterado

- **Origem do e-mail no canto direito do cabecalho, empilhada**: ambiente, versao do projeto, versao do LuftBase e
  link (sem `https://`) ficam em linhas pequenas e cinza claro abaixo do nome do sistema, em vez de uma linha no rodape.

## [0.1.0a104] - 2026-10-15

### Alterado

- **Origem do e-mail mais discreta**: ambiente, versao do projeto, versao do LuftBase e link saem do cabecalho e do
  cartao e viram uma unica linha pequena e cinza claro no fim do rodape. Removido o selo de ambiente do cabecalho.
- **Modo teste sem a tabela "Destinatarios reais"**: a faixa "MODO TESTE" continua, mas o e-mail nao lista mais
  quem receberia de verdade.

## [0.1.0a103] - 2026-10-15

### Alterado

- **E-mails de alerta e de acesso liberado trazem ambiente, versao e link**: o cabecalho ganha o selo do ambiente
  (Desenvolvimento, Homologacao ou Producao) e o rodape mostra ambiente, versao do projeto, versao do LuftBase e o
  link da aplicacao. Vale para todo e-mail que estende `luftbase/email/base.html`. O alerta ganhou o botao
  "Abrir <sistema>". `ServicoEmail` aceita `versao` e `url_publica`; a plataforma preenche com
  `LUFT_APLICACAO_VERSAO` e `LUFT_URL_PUBLICA` (ou o `link` absoluto do sistema).

## [0.1.0a102] - 2026-10-13

### Corrigido

- **Portal deslogava em poucos minutos mesmo com "Lembrar acesso"**: o checkbox era ignorado e toda sessao valia
  `LUFT_SESSAO_TTL_MINUTOS` (padrao 10) sem atividade. Agora, quem marca "Lembrar acesso" tem sessao de
  `LUFT_SESSAO_LEMBRAR_DIAS` (padrao 30 dias sem atividade, cookie persistente pelo mesmo prazo). Nova opcao
  `iniciar_sessao_usuario(usuario, lembrar=True)`.
- Padrao de `LUFT_SESSAO_TTL_MINUTOS` subiu de 10 para 60 minutos.

## [0.1.0a101] - 2026-10-08

### Alterado

- **Aba Integracoes com os logos das ferramentas**: Vault, PostgreSQL, SQL Server, Gmail, Login corporativo (Microsoft),
  Componentes (Python) e Sessoes (PostgreSQL ou Redis, conforme o armazenamento). Sao SVGs do Simple Icons (CC0) pintados com a cor
  de cada cartao; o cartao do **LuftBase** passa a usar o icone novo. Quem nao tem logo conhecido (ex.: e-mail que nao e Gmail,
  a propria aplicacao) continua com o icone padrao. Procedencia e licenca em `static/img/integracoes/LEIAME.md`.
- O painel devolve `logo` e `imagem` em cada cartao; o JavaScript so aceita nomes de arquivo com letras, numeros, `.`, `-` e `_`.

## [0.1.0a100] - 2026-10-08

### Alterado

- Ao conceder uma permissao que NAO e a de acesso ao sistema a quem ainda nao tem o acesso base, a tela avisa: "Atencao: <pessoa>
  ainda nao tem a permissao de acesso ao sistema ... esta regra nao gera aviso". Antes nada aparecia e parecia que o aviso de
  acesso liberado tinha falhado (so a permissao base, `<SIS>.SISTEMA.ACESSAR`, gera e-mail e notificacao).

## [0.1.0a99] - 2026-10-08

### Alterado

- **Painel de notificacoes redesenhado**: mais recente primeiro e agrupado por dia (Hoje, Ontem, Esta semana, Anteriores); resumo
  no cabecalho ("2 nao lidas" / "Tudo em dia"); abas em formato segmentado; filtro por tipo (aparece com mais de um tipo);
  botao de acao em destaque ("Abrir Luft-Workspace"); icones de ler e limpar por item; estados vazios mais claros; tela cheia no
  celular. Antes a lista aparecia com as mais antigas no topo e o "Carregar mais" repetia as mesmas notificacoes (o servidor ignora
  `pagina`); agora o limite cresce de 20 em 20 ate 100.
- **Limpar com menu e Desfazer**: "Limpar as lidas" ou "Limpar todas", sem janela de confirmacao; um aviso de 8 s oferece
  "Desfazer" (`POST /_luftbase/notificacoes/restaurar`). `ocultar-todas` agora devolve os `ids` limpos.
- Links de notificacao so viram botao se forem caminho do proprio site ou `http(s)` (`javascript:` e afins sao descartados).
- O painel passou para arquivos novos (`notificacoes_v2.js` e `notificacoes_v2.css`), o antigo `notificacoes.js` saiu: o nome novo
  evita que um navegador com cache antigo misture a tela nova com o JavaScript velho.

## [0.1.0a98] - 2026-10-08

### Corrigido

- O aviso de acesso liberado agora pega o e-mail de `core.tb_usuario` (PostgreSQL), com o diretorio como reserva, e tambem avisa
  membros do grupo que so existem no PostgreSQL. Antes so olhava o diretorio: quem tinha e-mail no perfil e nao no diretorio
  recebia apenas a notificacao.
- Ao conceder a permissao de acesso, a tela explica quando ninguem foi avisado ("as N pessoas ja tinham acesso" ou "nao
  encontrei pessoas para esta regra").

## [0.1.0a97] - 2026-10-08

### Alterado

- Ao liberar um acesso (Gerenciador de Permissoes, regra de usuario/grupo ou espelhar), a tela mostra o que de fato saiu:
  "Acesso liberado a N pessoa(s): X notificacao(oes) e Y e-mail(s) enviado(s)", quantas ficaram sem e-mail cadastrado no
  diretorio, se o e-mail esta em modo teste ou nao configurado e se houve falha. Antes o administrador nao tinha como saber
  por que um e-mail nao chegou.

## [0.1.0a96] - 2026-10-08

### Adicionado

- **Limpar notificacoes**: botao "Limpar" no painel e "X" em cada item tiram a notificacao so da lista de quem clicou; ela
  continua no banco e para as demais pessoas. Tabela nova `core.tb_notificacao_oculta` (migracao aditiva `20261008_0015`, com
  acesso concedido a todos os papeis `luft_*_app`). **Aplique a migracao antes de subir o pin nos apps.**
  Rotas `POST /_luftbase/notificacoes/<id>/ocultar` e `/ocultar-todas`.

### Alterado

- E-mail de acesso liberado: layout centralizado, com selo de confirmacao, cartao com sistema, quem liberou e como entrar, botao
  centralizado e o endereco abaixo para copiar.

## [0.1.0a95] - 2026-10-08

### Corrigido

- O avaliador de alertas enviava o e-mail dentro da transacao do banco; a auditoria do envio abre outra na mesma sessao e
  falhava ("A transaction is already begun on this Session"). Agora o e-mail sai entre duas transacoes, a trava continua valendo
  durante o envio e e solta mesmo se o ciclo falhar.

## [0.1.0a94] - 2026-10-08

### Corrigido

- E-mail renderizado dentro de comando de CLI (`flask alertas avaliar`) falhava com "Working outside of request context": ha
  contexto de app mas nao de requisicao, e os context processors leem a sessao. Agora usa uma requisicao de teste vazia.

## [0.1.0a93] - 2026-10-08

### Corrigido

- O avaliador de alertas subia em qualquer processo que carregasse o app, inclusive comandos de CLI (`bootstrap`, `banco ...`),
  e despejava um traceback por ciclo enquanto as tabelas nao existiam. Agora so sobe no servidor (`servidor.executar`) e repete
  no log apenas quando a falha muda.

### Documentacao

- Doc 20: os comandos sao `flask --app App:CriarApp <grupo> <comando>` (nao `luftbase ...`); `bootstrap --atualizar` ja
  sincroniza o catalogo do Workspace.

## [0.1.0a92] - 2026-10-08

### Adicionado

- **Alertas para o desenvolvedor**: erros 5xx, rajadas de 4xx, eventos criticos, lentidao e sistema parado em horario comercial
  viram um e-mail para `widson.araujo@luftlogistics.com` (fixo no codigo) com pessoa, IP, rota, status, contagem, janela e id de
  correlacao, sem dado sensivel. Antirruido: um alerta por problema, silencio de 15 min, fecha sozinho, e-mail unico por ciclo.
  `LUFT_ALERTAS_ATIVO=true` (so no Workspace) liga o avaliador; `luftbase alertas avaliar|listar`; API em
  `/auditoria/api/alertas`. Migracao aditiva `20261008_0014` (`tb_alerta`, `tb_alerta_controle`): rode `luftbase banco atualizar`
  antes do deploy.
- **Retencao de logs**: `luftbase banco tamanho-logs` e `luftbase banco retencao [--simular|--executar --arquivar-em PASTA]`
  (acesso 180 dias, sessoes 365, eventos 730, alertas 180; ajustaveis por `LUFT_RETENCAO_*_DIAS`). Arquiva em CSV compactado
  antes de apagar e preserva a trilha de alteracao ainda no prazo.

## [0.1.0a91] - 2026-10-08

### Adicionado

- **Acesso liberado**: quem recebe a permissao base de um sistema (`PLATAFORMA.SISTEMA.ACESSAR`, `CONNECTAIR.SISTEMA.ACESSAR`...)
  ganha um e-mail com o link do sistema e uma notificacao global so para essa pessoa. Dispara so na mudanca de "sem acesso"
  para "com acesso" (usuario, grupo e espelhar permissoes) e nunca desfaz a concessao se o e-mail falhar. Novo `LUFT_URL_PUBLICA`
  (opcional) para o endereco dos links.
- **Bloqueio de login**: botao "Bloquear acesso / Desbloquear acesso" no Gerenciador de Permissoes (permissao nova
  `SEGURANCA.USUARIOS.DESATIVAR`; rode `luftbase catalogo sincronizar`). O login confere `tb_usuario.bloqueado` (fail-closed) e
  bloquear derruba as sessoes ativas da pessoa.
- **Aviso de sessao encerrada**: quando um administrador derruba a sessao, a tela de entrada diz isso uma vez.

### Alterado

- `_resolver_estados` foi para `autorizacao/resolucao.py` (`resolver_estados`, com filtro `somente`); o catalogo passa a ter 50 permissoes.

## [0.1.0a90] - 2026-10-08

### Adicionado

- CI do LuftBase em Windows e Linux (`ruff`, `pytest`, build do wheel e conferencia tag x versao).
- Teste de fumaca por plataforma (log fisico no horario de Brasilia), teste que exige migracao aditiva e
  `tools/carga.py` (roteiro de carga com p95 e taxa de erro), documentados no doc 20 com o procedimento de rollback.

### Corrigido

- `web/configuracoes.py` usava `Any` sem importar; lint zerado (`E501` fica fora, por ser so de estilo).

## [0.1.0a89] - 2026-10-08

### Corrigido

- Horario dos logs 3 h adiantado no Windows (ex.: 12:20 as 09:20). `aplicar_fuso_do_processo()` gravava
  `TZ=America/Sao_Paulo`, que o runtime C do Windows le como UTC; agora so mexe em `TZ` onde existe `time.tzset()`.
- Logs fisicos e de console passam a usar `FormatadorDeLog` (horario de Brasilia independente da maquina); a data
  de modificacao dos arquivos de log usa `de_timestamp()`.

## [0.1.0a88] - 2026-10-07

### Alterado

- Auditoria > Ao vivo: "Quem esta conectado" usa o mesmo avatar do botao de perfil (foto da pessoa, ou
  iniciais da primeira e da ultima palavra do nome, com o ponto de online), com as mesmas classes
  `luft-avatar`.

## [0.1.0a87] - 2026-10-07

### Alterado

- "Desconectar todos": quando so existe a sua sessao ativa, a mensagem agora diz isso (antes: "nenhuma sessao
  ativa encontrada") e ha a opcao "Incluir a minha sessao (eu tambem serei desconectado)"; com ela a sua
  sessao e a ultima a cair e a pagina recarrega na tela de entrada. Na sua linha do Ao vivo, com mais de uma
  sessao, aparece "Encerrar minhas outras sessoes".

## [0.1.0a86] - 2026-10-07

### Adicionado

- **Controle de sessoes na Auditoria** (permissao `SEGURANCA.SESSOES.REVOGAR`; somente quem a tem ve os botoes):
  - **Desconectar pessoa** (Ao vivo): encerra todas as sessoes dela, em qualquer navegador.
  - **Encerrar sessao** (Registros > Sessoes): encerra uma sessao especifica; a sessao em uso aparece como "sua
    sessao", sem botao.
  - **Desconectar todos** (Ao vivo): encerra todas as sessoes menos a sua; exige digitar `DESCONECTAR`.
  - Toda acao pede confirmacao, valida CSRF e escopo (um sistema satelite so alcanca quem o usa ou entrou por
    ele), registra `REVOGACAO` na sessao, marca a pessoa como offline e deixa o rastro na auditoria
    (`REVOGAR_SESSAO`, `DESCONECTAR_PESSOA`, `DESCONECTAR_TODOS`). A sessao e referenciada por um hash:
    o identificador real nunca sai do servidor. Rotas `POST /configuracoes/api/auditoria/sessoes/revogar|revogar-pessoa|revogar-todas`.

### Corrigido

- `POST /_luftbase/sessoes/revogar` respondia sucesso sem encerrar nada com o armazenamento PostgreSQL (procurava
  um metodo `revogar` que nao existe). Passa a chamar `revogar_sessao` e responde 404 se a sessao nao existe.

## [0.1.0a85] - 2026-10-07

### Corrigido

- Auditoria > Registros: o seletor "Arquivo" aparecia em todas as abas (o atributo `hidden` perdia para
  `display: flex`). Agora so aparece em "Arquivos fisicos" e em "Raiz temporaria"; nesta ultima mostra, sem
  opcao de troca, o arquivo do processo atual.

## [0.1.0a84] - 2026-10-07

### Adicionado

- **Auditoria interativa, no estilo de um BI**: tudo o que aparece na tela e clicavel e leva aos registros
  por tras do numero.
  - Clique em celula do **mapa de calor** (ou no titulo de uma hora/dia), barra do **volume**, fatia ou
    legenda da **rosca**, **KPI**, **destaque**, linha de **ranking**, **rotas lentas/com falha**, **tentativas
    negadas**, **eventos criticos**, **pessoas mais ativas**, **IPs**, **navegadores**, **motivos de
    encerramento** e **pessoa online**: aplica o recorte e abre os Registros ja filtrados.
  - **Shift+clique** so filtra: todos os graficos e numeros se recalculam sem trocar de secao. Mapa de calor e
    rosca mostram o todo e destacam a parte escolhida.
  - Barra de **filtros ativos** (chips removiveis, "Ver registros", "Limpar tudo") sempre visivel.
  - Nova aba **Sessoes** em Registros (pessoa, sistema, navegador, SO, IP, situacao, duracao) e detalhe em
    gaveta. `GET /configuracoes/api/auditoria/sessoes`.
  - Novos recortes validados no servidor: `rota` (ids agrupados), `metodo`, `ip`, `login`, `grupo`,
    `navegador` (as mesmas regras do grafico, conferidas por teste), `hora`, `dia_semana`, `motivo`; valem
    para acessos, eventos, sessoes, graficos e exportacao CSV. Resultado ganhou "Redirecionamento (3xx)";
    "Sucesso" passou a ser so 2xx.

## [0.1.0a83] - 2026-10-07

### Corrigido

- Auditoria, dados mais fieis ao que acontece:
  - **Visitantes nao sao "conectados" nem "logins"**: sessoes sem usuario (tela de login, verificacoes) deixam
    de aparecer como "Usuario @—" e de inflar "sessoes ativas" e "logins no periodo".
  - **Uma linha por pessoa** em "Quem esta conectado" (com "+N sessoes" e os outros navegadores no balao),
    em vez de uma por sessao.
  - **"anonimo" virou "visitante"** no feed (a tela de entrada e o instante da saida), escondido por padrao
    (caixa "mostrar visitantes").
  - Navegador **"Desconhecido"** (sessoes de antes da captura) sai dos rankings e dos destaques e e contado a
    parte; sessao "ATIVA" no banco mas ja expirada aparece como "Expirou", nao "Em andamento".
  - **127.0.0.1** e rotulado como servidor local e nao dispara o aviso de "varias pessoas no mesmo IP".
  - Variacao frente ao periodo anterior so aparece com base minima (30 requisicoes): chega de "subiu 1056%".

### Adicionado

- `LUFT_AUDITORIA_DADOS_DESDE` (ISO 8601, ex.: `2026-10-06T17:00`): ignora nas analises e nos registros da
  auditoria o que veio antes do marco, sem apagar nada. Aparece em Ambiente e a tela avisa quando esta ativo.

## [0.1.0a82] - 2026-10-07

### Corrigido

- Auditoria > Ao vivo mostrava "ninguem conectado" fora do Workspace: a sessao e unica (SSO) e nasce no sistema
  onde a pessoa entrou, entao filtrar por `Sessao.id_sistema` escondia quem estava usando o Integrador ou o
  ConnectAir. No escopo de um sistema, agora vale quem o usou nos ultimos 15 minutos ou entrou por ele, e o
  sistema mostrado e o do ultimo acesso.

### Alterado

- **Auditoria & Analise reorganizada** em secoes (Visao geral, Ao vivo, Pessoas & sessoes, Desempenho,
  Seguranca, Registros), com a escolha lembrada no navegador e contadores nas abas (online agora, alertas).
  - Visao geral: destaques em linguagem simples ("16 erros no servidor, 300% a mais que antes"), KPIs com a
    variacao frente ao periodo anterior de mesma duracao, mapa de calor (dia da semana x hora) e saude das
    respostas (2xx a 5xx).
  - Pessoas & sessoes: logins, pessoas e IPs diferentes, duracao media da sessao, navegadores, sistemas e
    dispositivos, motivos de encerramento, pessoas mais ativas e IPs compartilhados por varias pessoas.
  - Desempenho: telas mais lentas e rotas com falhas (ids agrupados: `/clientes/:id`).
  - Seguranca: tentativas sem permissao (com a permissao que faltou) e eventos de severidade alta ou critica.
  - Rota `GET /configuracoes/api/auditoria/insights` (somente leitura, `AUDITORIA.VISUALIZAR`),
    `observabilidade/insights.py`. Registros, filtros e exportacao continuam como eram.

## [0.1.0a81] - 2026-10-06

### Adicionado

- Auditoria & Analise, secao **Ao vivo** (atualiza a cada 10 s, com pausa e sem consultar quando a aba
  esta oculta): usuarios online agora, sessoes ativas, requisicoes por minuto, tempo medio e erros 5xx; lista
  de quem esta conectado (nome, navegador e SO, IP, sistema, o que fez por ultimo e ha quanto tempo,
  situacao ativo/recente/ocioso); navegadores, sistemas operacionais e dispositivos em uso; feed das ultimas
  acoes (sem as chamadas automaticas da tela). Segue o filtro de Sistema e o escopo da aplicacao.
  Rota `GET /configuracoes/api/auditoria/tempo-real` (permissao `AUDITORIA.VISUALIZAR`, somente leitura),
  `observabilidade/tempo_real.py`.

## [0.1.0a80] - 2026-10-06

### Alterado

- Nota de lancamento: deixa de falar em "todos os sistemas web". Cita o Workspace, o ConnectAir e o
  Integrador (ja na nova base) e o Luft-Control como proximo; os demais sistemas da Luft, de outras
  tecnologias, seguem como estao. O titulo mudou e a nota publicada com o titulo anterior e reconhecida.

## [0.1.0a79] - 2026-10-06

### Corrigido

- Script da nota de lancamento: se a nota existir em mais de uma copia (rodado com textos de versoes
  diferentes), mantem a mais nova, corrige o texto dela e arquiva as demais.

## [0.1.0a78] - 2026-10-06

### Corrigido

- Nota de lancamento ja publicada mostrava imagens quebradas: a a77 apagou as imagens administrativas que o
  texto antigo ainda citava. Agora o script reconhece a nota publicada (mesmo com titulo de versoes
  anteriores) e **corrige o texto** no banco, sem notificar de novo (`ServicoPublicacoes.corrigir_texto`).

## [0.1.0a77] - 2026-10-06

### Alterado

- Nota global de lancamento reescrita como comunicado para o usuario final: fala dos "sistemas web" da
  Luft (Workspace, ConnectAir e Integrador ja adaptados; Luft-Control e os demais virao a seguir) e deixa
  de fora o que e de TI (cofre, auditoria, servicos, parametros). 14 imagens, sem telas administrativas.

## [0.1.0a76] - 2026-10-06

### Alterado

- Nota global de lancamento reescrita como nota de atualizacao completa (~15 mil caracteres, 22 imagens
  PNG em `img/changelog`, geradas por `tools/gerar_imagens_changelog.py`: ilustracoes e maquetes de tela com
  dados ficticios). O texto fala apenas de Workspace, ConnectAir e Integrador.

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
