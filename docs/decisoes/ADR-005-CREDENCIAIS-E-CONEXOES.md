# ADR-005 — Credenciais e conexoes

Status: aceito em 2026-09-15.

## Contexto

Cada aplicacao precisa consultar o diretorio no SQL Server e acessar dados sistemicos e de
negocio no PostgreSQL. O framework nao pode repetir configuracao, expor segredos, usar contas
administrativas nem multiplicar pools sem necessidade.

## Decisao

- Vault e acessado por um contrato substituivel e pelo adaptador HVAC KV v2.
- Tokens permanecem protegidos no ambiente e sao revelados apenas na inicializacao explicita.
- Credenciais sao imutaveis e senhas nao aparecem em `repr` ou `str`.
- Contas `admin`, `postgres` e `sa` sao recusadas no runtime.
- O SQL Server possui pool proprio e fronteira sem unidade de trabalho de escrita.
- Core e aplicacao possuem sessoes separadas sobre um pool PostgreSQL compartilhado.
- O schema de negocio usa `schema_translate_map` depois da validacao do segredo.
- Toda escrita ocorre dentro de unidade de trabalho com commit/rollback definidos.
- O teardown remove sessoes; descarte de pool nao ocorre por requisicao.
- Health checks devolvem somente nome logico, estado, latencia e codigo controlado.

## Consequencias

Os projetos consumidores deixam de montar URLs e engines. A separacao de privilegios precisa
ser aplicada tambem no banco: a protecao em Python e uma segunda barreira, nao substitui roles
corretas. SQL textual nao recebe traducao automatica de schema e deve ser excepcional.
