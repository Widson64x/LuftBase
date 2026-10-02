# ADR-001 — Criar o LuftBase como novo produto

## Estado

Aceita.

## Decisao

O LuftBase sera construido em um repositorio e pacote novos. O LuftCore 0.4.x permanecera
disponivel para rollback e para aplicacoes ainda nao migradas.

## Motivo

Uma alteracao destrutiva no pacote existente misturaria compatibilidade, arquitetura nova e
correcoes do legado. A separacao permite migracao gradual e uma API realmente limpa.

