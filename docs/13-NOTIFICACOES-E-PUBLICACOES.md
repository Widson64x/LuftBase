# Notificacoes e publicacoes

## Responsabilidades

O LuftBase concentra os modelos, filtros de audiencia, transacoes, recibos de leitura e
contratos HTTP. A aplicacao consumidora informa apenas os dados do evento ou da publicacao;
ela nao fornece models nem reimplementa consultas ao schema `core`.

O PostgreSQL e sempre a fonte definitiva. Redis guarda somente o ultimo cursor sinalizado,
com TTL, para orientar consumidores e uma futura entrega ativa. Ausencia, expiracao ou falha
do Redis nunca apaga conteudo nem transforma o cache em resposta autoritativa.

## Notificacoes

Uma notificacao pertence ao sistema atual e pode ser destinada a:

- um usuario;
- um grupo;
- todos, quando usuario e grupo estiverem ausentes.

Conteudo com `id_sistema` igual a `0` ou `NULL` e global. As consultas combinam sistema,
audiencia, `exibir_a_partir_de` e `expira_em` no PostgreSQL. Notificacoes pessoais usam o
estado de leitura da propria notificacao; notificacoes gerais ou de grupo usam um recibo em
`tb_notificacao_leitura` por usuario.

```python
from luftbase import CategoriaNotificacao, NovaNotificacao, obter_luftbase

id_notificacao = obter_luftbase().notificacoes.criar(
    NovaNotificacao(
        titulo="Integracao concluida",
        mensagem="O arquivo foi processado.",
        categoria=CategoriaNotificacao.INTEGRACAO,
        id_usuario_destino=usuario.id_usuario,
        criado_por=usuario.login,
        metadados={"id_execucao": 123},
    )
)
```

### Notificacao de acesso liberado

Gerada pelo LuftBase (nao pela aplicacao) quando alguem recebe a permissao base de um sistema: categoria `SEGURANCA`, tipo
`SUCESSO`, escopo **global** (sistema 0, aparece em qualquer aplicacao), destinada so a essa pessoa, com
`metadados.acao_url` = link do sistema e `texto_link` = "Abrir <Sistema>". Regras e e-mail no
[doc 11](11-AUTORIZACAO.md#aviso-de-acesso-liberado).

### Limpar notificacoes (some so para mim)

No painel, o botao **Limpar** (cabecalho) e o **X** de cada item tiram a notificacao da lista **de quem clicou**. Nada e apagado:
a notificacao continua em `tb_notificacao` e segue aparecendo para as demais pessoas. A escolha fica em
`core.tb_notificacao_oculta` (`id_notificacao`, `id_usuario`, `data_ocultacao`), vale para notificacao pessoal, de grupo e global, e
`filtro_notificacao_visivel` a aplica em todas as consultas (lista, contagem de nao lidas, marcar como lida). A notificacao
limpa tambem sai da contagem do sino. Limpar de novo a mesma notificacao e idempotente; limpar a de outra pessoa responde 404.
O botao **Limpar** tem um menu ("Limpar as lidas" / "Limpar todas") e, depois de limpar, um aviso de 8 s oferece **Desfazer**
(`POST /_luftbase/notificacoes/restaurar` com `{"ids": [...]}`, de 1 a 500 ids, so afeta a lista de quem pediu). Se a notificacao expirar ou for removida, a linha de `tb_notificacao_oculta` vai junto (`ON DELETE CASCADE`).

Em todo sistema que le notificacoes o papel do banco precisa de acesso a essa tabela (a migracao `20261008_0015` concede a todos os
papeis `luft_*_app`); sem isso a lista de notificacoes falha.

## Publicacoes

Uma publicacao nasce como rascunho. `publicar()` bloqueia a linha, altera seu estado e cria
as notificacoes e os vinculos na mesma transacao. Repetir a publicacao nao cria duplicatas.
Quando `id_externo` e informado, o par `(fonte, id_externo)` torna a criacao do rascunho
idempotente.

```python
from luftbase import NovaPublicacao, TipoAudiencia, obter_luftbase

servico = obter_luftbase().publicacoes
id_publicacao = servico.criar_rascunho(
    NovaPublicacao(
        titulo="Janela de manutencao",
        resumo="Indisponibilidade prevista para sabado.",
        conteudo="Detalhes da manutencao...",
        criado_por=usuario.login,
        audiencia=TipoAudiencia.GERAL,
    )
)
servico.publicar(id_publicacao)
```

Publicacoes para grupos exigem ao menos um grupo e nunca misturam audiencia geral com uma
lista de grupos. Notas de atualizacao exigem versao e podem receber itens ordenados.

## Consultas incrementais

`listar_para_usuario()` aceita `cursor` e `limite`. Sem cursor, devolve apenas a janela mais
recente. Com cursor, devolve IDs maiores em ordem crescente e informa `tem_mais`, permitindo
consumo em lotes sem carregar o historico completo. O cursor e um identificador opaco para o
cliente; ele nao deve ser decrementado nem usado como contagem.

O feed nunca retorna o corpo completo da publicacao. O corpo e lido somente no endpoint de
detalhe, reduzindo transferencia e memoria.

## Rotas instaladas

Todas as rotas exigem uma sessao Flask-Login valida:

- `GET /_luftbase/notificacoes`;
- `PUT /_luftbase/notificacoes/<id>/leitura`;
- `POST /_luftbase/notificacoes/<id>/ocultar`, `POST /_luftbase/notificacoes/ocultar-todas` (`?apenas_lidas=1` limpa so as lidas; devolve os `ids`) e `POST /_luftbase/notificacoes/restaurar`;
- `GET /_luftbase/notificacoes/eventos`;
- `GET /_luftbase/publicacoes`;
- `GET /_luftbase/publicacoes/<id>`;
- `PUT /_luftbase/publicacoes/<id>/leitura`;
- `GET /_luftbase/publicacoes/eventos`.

Rotas das telas de publicacao (prefixo `/publicacoes`, exigem login):

- `GET /publicacoes/comunicados` e `GET /publicacoes/atualizacoes` (caixa de entrada), `GET /publicacoes/<id>` (leitura);
- `GET /publicacoes/painel/comunicados` e `/painel/atualizacoes` (administracao);
- `POST /publicacoes/api/{comunicados|atualizacoes}` (criar), `POST` ou `PUT` em `.../<id>` (editar rascunho), `.../<id>/publicar`, `.../<id>/arquivar`;
- `POST /publicacoes/api/imagens` (upload), `GET /publicacoes/imagem/<id>` (entrega) e `POST /publicacoes/api/previa` (pre-visualizacao). Detalhes do editor e da seguranca no [doc 21](21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md).

As rotas de leitura sao idempotentes. Consultar um detalhe nao grava implicitamente; o
cliente confirma a leitura por `PUT`. Essa separacao evita escrita inesperada em prefetch,
robos ou repeticao de GET.

## SSE e retomada

Os endpoints `eventos` respondem `text/event-stream`, aceitam `Last-Event-ID` e consultam no
PostgreSQL apenas IDs posteriores. Cada resposta entrega um lote curto e termina; o
`EventSource` reconecta depois do `retry` informado. Isso oferece retomada sem exigir broker,
conexao longa ou processo residente nesta fase.

Nginx deve preservar `Last-Event-ID`, desabilitar buffering para essas rotas e manter
`Cache-Control: no-cache`. O LuftBase tambem envia `X-Accel-Buffering: no`.

## Fila de e-mails

Enviar e-mail dentro da requisicao deixava a tela carregando (dar acesso a um grupo de 200 pessoas = 200 e-mails). Agora quem precisa enviar **grava na
fila** (`core.tb_email_fila`, modelo `EmailFila`) e segue; um servico em segundo plano entrega.

- **Enfileirar**: `estado.fila_email.enfileirar(para, assunto, template=..., contexto={...}, origem="MINHA_ORIGEM")` ou `enfileirar_varios([fila.montar(...), ...])`
  (uma transacao, tudo ou nada). Guarda a *intencao* (template + contexto JSON, ou `html`/`texto`), nao a mensagem pronta: o modo teste, o remetente e o layout
  valem como estao na hora da entrega. O contexto precisa ser JSON simples (texto, numeros, listas); **anexos e imagens embutidas nao sao suportados** na fila
  (use `estado.email.enviar` direto). Erros de uso (sem destinatario, sem assunto, contexto nao serializavel) levantam `ErroEmail` ja ao enfileirar.
- **Entregar**: a thread `EntregadorEmSegundoPlano` sobe junto com o servidor (`servidor.executar`), a cada `LUFT_EMAIL_FILA_INTERVALO_SEGUNDOS` (10) entrega lotes de
  ate 50 por conexao SMTP. O lote e reservado com `FOR UPDATE SKIP LOCKED`, entao varios servidores podem entregar ao mesmo tempo sem duplicar; um lote
  `ENVIANDO` parado ha mais de 10 min (processo morreu) volta para a fila. Desligue num servidor com `LUFT_EMAIL_FILA_ATIVO=false`. Sem nenhum servidor entregando,
  agende `luftbase email processar`.
- **Tentativas**: falha de entrega reagenda com espera de 1, 5 e 30 min; na 4a falha o e-mail fica `FALHOU` (e pode ser reenviado na tela). Endereco invalido ou template
  ausente falha na hora, sem repetir. Sem e-mail configurado o lote volta para a fila sem gastar tentativa.
- **Retencao**: enviados saem depois de `LUFT_EMAIL_FILA_RETENCAO_DIAS` (30); falhas e cancelados, depois de 90.
- **Tela**: Auditoria > Registros > **Fila de e-mails** (so com dados sensiveis): pendentes, enviados, falhas e todos com contagem, busca, **Cancelar** (pendente) e **Reenviar**
  (falha), ambos auditados. A insignia da aba mostra as falhas. `GET /auditoria/api/fila-email?situacao=` e `POST /auditoria/api/fila-email/<id>/{reenviar|cancelar}`.
- **Quem ja usa**: o aviso de **acesso liberado** (o resumo diz "N e-mail(s) na fila"). Se a tabela ainda nao existir (migracao `20261022_0019` pendente) o aviso envia direto, como antes.
  Alertas e comunicados continuam enviando direto por enquanto.

## Seguranca e operacao

- o filtro de audiencia roda no banco antes da serializacao;
- um item invisivel responde como inexistente;
- cursores e limites sao validados, com limite maximo de 100;
- metadados precisam ser JSON valido;
- conteudo retornado pela API nao deve ser inserido em HTML sem escape ou sanitizacao;
- falha do Redis nao reverte um commit PostgreSQL;
- falha PostgreSQL e visivel e nunca devolve uma lista vazia como fallback;
- a migration 0005 e aplicada manualmente e cria somente indices de cursor.
