# ADR-002 — Uma extensao e uma API publica em portugues

## Estado

Aceita.

## Decisao

`PlataformaLuft.inicializar(app)` sera a unica inicializacao publica. Models, sessoes do core,
auditoria, notificacoes e assets nao serao registrados manualmente pelos consumidores. A API
publica sera em portugues e nao tera aliases em ingles.

## Consequencia

O framework assume mais responsabilidade e precisa de testes fortes de integracao. Em troca,
as aplicacoes ficam menores e consistentes.

