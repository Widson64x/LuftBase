# ADR-014 — Integracao de e-mail liberada pela plataforma

Status: aceito em 2026-09-30.

## Contexto

Cada aplicacao mantinha sua propria conta SMTP no `.env` (`EMAIL_SMTP_*`), seu proprio envio
com `smtplib`, sua logica de modo teste e seu proprio layout de e-mail. O Luft-ConnectAir foi o
primeiro caso: o template `PlanejamentoFilial.html` misturava o esqueleto corporativo (logo,
faixa de status, rodape) com o conteudo do planejamento, e a senha da conta Gmail ficava no
arquivo de ambiente de cada servidor.

## Decisao

- A conta SMTP e um segredo por ambiente em `luft/{ambiente}/integracoes/email`, compartilhado
  pelas aplicacoes. Nenhuma variavel de e-mail fica no `.env`.
- O segredo e opcional. Ausente, a plataforma sobe e `obter_luftbase().email.configurado` e
  falso. Presente e invalido, a inicializacao falha com o campo indicado.
- Somente `starttls` e `ssl` sao aceitos, como no LDAP. A conta sempre autentica.
- O modo teste e dado do ambiente: `redirecionar_para` preenchido desvia todo envio, prefixa o
  assunto com `[TESTE]` e o layout mostra os destinatarios reais. A aplicacao nao decide isso.
- O nome exibido no remetente e, em ordem: o parametro do envio, o nome do sistema em
  `core.tb_sistema`, o `nome_remetente` do segredo. Um segredo compartilhado nao pode fixar o
  nome de uma aplicacao.
- Falhas de entrega nao geram excecao: viram `ResultadoEnvio` com mensagem segura. Erros de uso
  (sem destinatario, assunto com quebra de linha, e-mail nao configurado) geram `ErroEmail`.
- `enviar_lote` reutiliza uma sessao SMTP; uma recusa nao interrompe as demais mensagens.
- Cada envio gera um evento `EMAIL_ENVIADO` ou `EMAIL_FALHA` no recurso `EMAIL`, sem corpo nem
  anexos. Falha na auditoria apenas registra aviso, para nao induzir reenvio duplicado.
- O esqueleto visual fica em `luftbase/email/base.html` e as macros em
  `luftbase/email/componentes.html`. O conteudo de negocio continua na aplicacao.

## Consequencias

A troca de conta ou senha acontece em um unico lugar por ambiente e todos os sistemas passam a
ter o mesmo visual de e-mail. O envio continua sincrono dentro da requisicao; filas e novas
tentativas automaticas ficam para quando houver volume que as justifique. Contas Gmail possuem
limite diario de envio, que passa a ser compartilhado entre as aplicacoes do ambiente.
