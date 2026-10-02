# ADR-003 — Schema global fixo e schema particular dinamico

## Estado

Aceita.

## Decisao

O schema `core` e contrato fixo do LuftBase. O schema particular vem do campo `esquema` da
credencial PostgreSQL da aplicacao. `public` nao armazenara tabelas da plataforma.

Todos os acessos sao governados por roles PostgreSQL. Compartilhar acesso ao `core` nao
significa compartilhar credenciais ou conceder administracao a todas as aplicacoes.

