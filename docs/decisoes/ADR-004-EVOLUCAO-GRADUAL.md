# ADR-004 — Evolucao gradual e migrations explicitas

## Estado

Aceita.

## Decisao

O Luft-Workspace sera o primeiro piloto. Cada consumidor fixa uma versao do pacote e migra de
forma independente. Migrations do `core` sao executadas por CLI e nunca no startup.

Mudancas de schema seguem expandir e contrair para permitir que versoes diferentes coexistam
durante uma implantacao gradual.

