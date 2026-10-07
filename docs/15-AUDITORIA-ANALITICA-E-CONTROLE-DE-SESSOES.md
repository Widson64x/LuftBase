# Auditoria analitica, "Ao vivo" e controle de sessoes

Este documento complementa o [doc 12](12-AUDITORIA-E-OBSERVABILIDADE.md) (que explica como os registros sao **gravados**)
mostrando como a tela **Auditoria & Analise** os transforma em informacao e como um administrador age sobre as sessoes.

Codigo: `observabilidade/analise.py`, `insights.py`, `tempo_real.py`, `filtros.py`, `controle_sessoes.py`;
rotas em `web/auditoria.py`; tela em `interface/templates/luftbase/seguranca/_auditoria.html` e
`interface/static/js/auditoria*.js`.

## De onde vem cada numero

| Fonte | Tabela | Usada para |
|---|---|---|
| Acessos HTTP | `core.tb_logs` | requisicoes, erros, tempo, mapa de calor, rotas, IPs, navegadores |
| Eventos de dominio | `core.tb_logevento` | acoes, severidades, eventos criticos |
| Sessoes | `core.tb_sessao` | logins, navegadores, duracao, como terminaram |
| Usuarios | `core.tb_usuario` | nome, grupo, foto (Ao vivo) |

> Nomes atuais das tabelas: acesso HTTP = `tb_logs`; evento de dominio = `tb_logevento`; retrato antes/depois =
> `tb_logdetalhe`. O doc 12 e o ADR-013 foram escritos com os nomes anteriores a migracao 0012 (`tb_logacesso`,
> `tb_logdetalhe`, `tb_logs`): leia-os pela **funcao** de cada tabela, nao pelo nome.

## As seis secoes da tela

A secao escolhida fica lembrada no navegador. Os **filtros do topo** valem para todas.

1. **Visao geral** — destaques em frases, 8 KPIs, volume por intervalo, ranking (rotas, usuarios, grupos, sistemas),
   **mapa de calor** (dia da semana x hora) e **saude das respostas** (2xx a 5xx).
2. **Ao vivo** — quem esta conectado agora (veja abaixo).
3. **Pessoas & sessoes** — logins, pessoas e IPs diferentes, duracao media, navegadores, SO, dispositivos, como as sessoes
   terminam, pessoas mais ativas e IPs mais frequentes.
4. **Desempenho** — telas mais lentas e rotas com falhas.
5. **Seguranca** — tentativas sem permissao (com a permissao que faltou) e eventos de severidade alta ou critica.
6. **Registros** — tabelas de acessos, eventos, detalhes de alteracao, **sessoes**, raiz temporaria e arquivos fisicos.

### Regras que o painel aplica (e por que)

- **Comparativo**: cada KPI mostra a variacao em relacao ao periodo anterior **de mesma duracao**. So aparece quando o
  periodo anterior tem **pelo menos 30 requisicoes** (`BASE_MINIMA_COMPARACAO`); antes disso "subiu 1056%" so engana.
- **Rotas agrupadas**: `/clientes/42/testar` e `/clientes/7/testar` viram `/clientes/:id/testar` (numeros e UUIDs).
  "Rotas lentas" exige 3 chamadas ou mais.
- **Visitantes nao sao pessoas**: sessoes sem usuario (tela de login, verificacoes) ficam fora de "logins", "conectados" e
  "sessoes ativas". Nos acessos, requisicoes sem usuario aparecem como **visitante** (a tela de entrada e o instante da
  saida), escondidas por padrao no feed.
- **Navegador desconhecido** (sessoes antigas, anteriores a captura) sai dos rankings e dos destaques; um aviso informa
  quantas ficaram de fora.
- **Sessao "ATIVA" mas ja vencida** aparece como **Expirou**, nao "Em andamento".
- **127.0.0.1** e rotulado como **servidor local** e nao dispara o aviso de "varias pessoas no mesmo IP".
- **Mapa de calor e rosca mostram o todo**: ao filtrar por hora/dia (ou por resultado), eles ignoram o proprio recorte e
  destacam a parte escolhida, em vez de encolher para uma celula.
- **Destaques** (`gerar_destaques`): frases ordenadas por importancia — erros 5xx (com a rota mais afetada e a tendencia),
  acessos negados, rota lenta (media >= 800 ms), pico de uso, variacao grande (>= 20%), navegador lider. Sem nada relevante:
  "Tudo tranquilo".

### Corte de dados antigos: `LUFT_AUDITORIA_DADOS_DESDE`

Registros de antes de uma correcao (sem IP, sem navegador, horario errado) podem poluir as analises. Defina no `.env`:

```text
LUFT_AUDITORIA_DADOS_DESDE=2026-10-06T17:00
```

Tudo na Auditoria (analises, comparativo e Registros) ignora o que veio antes desse instante e a tela exibe uma faixa
avisando. **Nada e apagado.** Valor invalido ou vazio = sem corte. A variavel aparece (e e editavel) em
Aplicacoes & Ambiente > Variaveis; reinicie o servico depois de alterar.

## "Ao vivo"

Atualiza a cada 10 s (pausavel; nao consulta com a aba do navegador oculta; com a secao escondida atualiza so o contador).
Endpoint: `GET /configuracoes/api/auditoria/tempo-real` (somente leitura, `Cache-Control: no-store`).

- **Janelas**: "online" = atividade nos ultimos **5 min**; atividade recente = **15 min**; "ativo agora" = ate 90 s.
- **Uma linha por pessoa**: a sessao mais recente representa a pessoa; as demais aparecem como "+N sessoes" e seus
  navegadores no balao.
- **Estado**: ponto verde (ativo agora), amarelo (visto ha ate 5 min), sem ponto (ocioso).
- **O que esta fazendo**: a ultima requisicao util da pessoa nos ultimos 15 min (ignora chamadas automaticas da tela:
  `/static`, notificacoes, presenca, sinaliza, favicon).
- **Escopo por sistema**: o login e unico (SSO) e a sessao nasce no sistema onde a pessoa entrou. Por isso, quando o painel
  esta restrito a um sistema, valem as pessoas que **entraram por ele ou o usaram nos ultimos 15 min**, e o sistema mostrado
  e o do **ultimo acesso**.
- **Avatar**: o mesmo do botao de perfil (foto, ou iniciais da primeira e ultima palavra do nome).

## Interatividade (drill-down, estilo BI)

Quase tudo e clicavel e leva aos registros por tras do numero (`auditoria_drill.js`):

- **Clique**: aplica o recorte e abre **Registros** ja filtrado (na aba certa: acessos, sessoes ou eventos).
- **Shift+clique** (ou Ctrl/Cmd): so filtra; todos os graficos se recalculam sem trocar de secao.
- **Barra de filtros ativos**: um chip removivel por filtro, "Ver registros" e "Limpar tudo". Clicar de novo com Shift no mesmo
  valor remove o filtro.

Recortes aceitos (validados no servidor, valor invalido = HTTP 400): `rota` (com `:id`), `metodo`, `ip`, `login`, `grupo`,
`navegador`, `hora` (0-23), `dia_semana` (0=segunda), `motivo` (de sessao) e os filtros do formulario (`resultado`,
`severidade`, `sistema_id`, `usuario_id`, `termo`). Valem para acessos, eventos, sessoes, graficos e exportacao CSV.

`resultado` aceita `sucesso` (2xx), `redirecionamento` (3xx), `cliente` (4xx), `servidor` (5xx) e `negado`.

`navegador` usa **as mesmas regras do grafico**: `observabilidade/filtros.py` espelha em SQL o parser
`identidade/agente_usuario.py`, e um teste confere os dois lados com os mesmos user-agents.

## Controle de sessoes

Permissao: `SEGURANCA.SESSOES.REVOGAR` (quem nao a tem nem ve os botoes; o servidor confere de novo).

| Acao | Onde | Rota | O que faz |
|---|---|---|---|
| Encerrar uma sessao | Registros > Sessoes | `POST .../sessoes/revogar` `{ref}` | encerra so aquela sessao |
| Desconectar pessoa | Ao vivo (linha da pessoa) | `POST .../sessoes/revogar-pessoa` `{codigo_usuario}` | encerra todas as sessoes ativas da pessoa |
| Desconectar todos | Ao vivo (cabecalho) | `POST .../sessoes/revogar-todas` `{confirmacao:"DESCONECTAR", incluir_propria}` | encerra todas as ativas; exige digitar `DESCONECTAR` |

(prefixo `/configuracoes/api/auditoria`)

Garantias (`ServicoControleSessoes`):

- so atinge sessoes **ATIVAS** e de **pessoas logadas** e ainda nao vencidas; visitantes e sessoes mortas nao entram;
- a sessao em uso do administrador **nao** e encerrada, salvo "Incluir a minha sessao" em "Desconectar todos" (nesse caso a
  sua e a ultima a cair e a pagina recarrega na tela de entrada); ha tambem "Encerrar minhas outras sessoes";
- escopo: um sistema satelite so alcanca quem o usa ou entrou por ele;
- a sessao e identificada na tela por uma **referencia** (hash SHA-256 truncado em 20 hex); o identificador real nunca
  sai do servidor;
- cada acao pede confirmacao, valida CSRF e escopo, grava o evento `REVOGACAO`, marca a pessoa offline e registra na
  auditoria (`REVOGAR_SESSAO`, `DESCONECTAR_PESSOA`, `DESCONECTAR_TODOS`) com severidade media;
- erros esperados: `409` ("esta e a sessao que voce usa" ou "nao ha outras sessoes alem da sua"), `404` (a sessao ja terminou).

Limites conhecidos: a pessoa desconectada so percebe no proximo clique (volta ao login, sem mensagem explicando o motivo) e
desconectar nao **bloqueia** novo login.

## Permissoes da tela

| Chave | Efeito |
|---|---|
| `OBSERVABILIDADE.AUDITORIA.VISUALIZAR` | ver a tela, o Ao vivo e as analises |
| `OBSERVABILIDADE.AUDITORIA.EXPORTAR` | botao Exportar CSV (ate 5.000 linhas, sem payloads sensiveis) |
| `OBSERVABILIDADE.DADOS_SENSIVEIS.VISUALIZAR` | abas de raiz temporaria e arquivos fisicos, e payloads |
| `SEGURANCA.SESSOES.REVOGAR` | botoes de encerrar sessao |

## Rotas

`GET /configuracoes/api/auditoria/`: `resumo`, `insights`, `tempo-real`, `acessos`, `detalhes`, `alteracoes`, `sessoes`,
`temporarios`, `fisicos`, `detalhes/<tipo>/<id>`, `exportar`.

O seletor "Arquivo" so aparece nas abas **Arquivos fisicos** e **Raiz temporaria** (nesta ultima mostra apenas o arquivo do
processo atual, sem opcao de troca).
