# ADR-010 — Aplicacao ID e layout Vault v2

Status: rejeitado em 2026-09-17. Substituido pelo ADR-009 antes da liberacao do a4.

Esta alternativa foi implementada de forma experimental, mas criava novamente duas
identidades para o mesmo sistema. Nao faz parte do contrato final do LuftBase.

## Contexto

O bootstrap por ID numerico duplicava uma identidade interna e obrigava o Vault a conhecer
uma chave relacional do banco. Usar `schema` como identidade tambem acoplaria o produto a uma
decisao de armazenamento que pode mudar.

## Decisao

- `LUFT_APLICACAO_ID` e a unica identidade fornecida pela aplicacao.
- `core.tb_sistema.identificador_aplicacao` e uma chave tecnica unica e imutavel; a chave
  primaria numerica `id_sistema` continua sendo usada nas FKs existentes.
- O runtime resolve os segredos em:
  - `{namespace}/{ambiente}/infraestrutura/postgresql/conexoes/{alias}`;
  - `{namespace}/{ambiente}/aplicacoes/{aplicacao_id}/postgresql`.
- O primeiro segredo concentra host, porta, banco, tipo e `sslmode`. O segundo contem alias da
  conexao, schema, usuario e senha da aplicacao.
- Depois de conectar, o LuftBase consulta `tb_sistema` pelo identificador e obtem o ID numerico,
  nome, status e demais metadados.
- O sistema `0` continua sendo o escopo global de autorizacao, nunca um bypass. Ausencia,
  divergencia ou falha de consulta nega por padrao.
- A migracao do Vault e paralela e usa CAS 0. Caminhos legados so podem ser removidos depois
  do corte validado em desenvolvimento, homologacao e producao.

## Consequencias

Uma mudanca de servidor altera um unico segredo compartilhado por ambiente, mesmo com centenas
de schemas. Cada projeto configura apenas um slug estavel. O runtime precisa da migration 0006
e dos segredos v2 antes de iniciar; nao existe fallback silencioso para o layout antigo.
