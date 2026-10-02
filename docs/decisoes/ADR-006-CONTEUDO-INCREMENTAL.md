# ADR-006 — Conteudo incremental com PostgreSQL autoritativo

Status: aceito em 2026-09-16.

## Contexto

Notificacoes e publicacoes precisam ser compartilhadas entre aplicacoes, respeitar audiencia
e continuar disponiveis mesmo se o Redis estiver vazio. Consultas que carregam todo o
historico ou SSE dependente de um processo conectado permanentemente aumentariam o custo e a
complexidade operacional antes do piloto.

## Decisao

- PostgreSQL e a unica fonte definitiva de conteudo e recibos de leitura.
- IDs crescentes funcionam como cursores de retomada e recebem indices dedicados.
- A janela sem cursor traz somente os itens recentes; a janela com cursor traz itens
  posteriores em lotes de no maximo 100.
- Redis armazena somente o ultimo cursor sinalizado, com TTL e falha em melhor esforco.
- SSE usa `Last-Event-ID`, consulta o PostgreSQL e encerra depois de um lote curto.
- GET nunca marca leitura. Recibos sao criados por PUT idempotente.
- Publicacao, notificacoes derivadas e vinculos sao confirmados na mesma transacao.
- Repositorios devolvem DTOs destacados do ORM.

## Consequencias

A entrega funciona sem broker e pode perder somente a oportunidade de um sinal imediato,
nunca o dado. A reconexao recupera eventos pelo cursor. O modelo atual nao oferece push
instantaneo entre reconexoes; um broker ou Redis Streams pode ser acrescentado depois sem
alterar a fonte de verdade nem o contrato de retomada.
