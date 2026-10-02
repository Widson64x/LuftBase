# ADR-007 — Familia de tema separada do modo visual

Status: aceito em 2026-09-16.

## Contexto

O legado tratava tema como alternancia entre claro e escuro e permitia desligar partes do
CSS e do JavaScript. Isso fazia cada aplicacao escolher uma combinacao diferente e tornava a
adicao de uma nova identidade visual uma alteracao transversal.

## Decisao

- familia (`luft`, `operacoes`) e modo (`CLARO`, `ESCURO`, `SISTEMA`) sao conceitos distintos;
- o perfil web sempre instala base, tokens, acessibilidade e JavaScript essencial;
- familias sao descritas por manifestos locais e registradas no estado da aplicacao;
- toda familia fornece variantes clara e escura usando os mesmos tokens semanticos;
- a preferencia corporativa fica no PostgreSQL e seu retrato de sessao fica no Redis;
- alteracoes usam PUT autenticado com token CSRF;
- o wheel inclui o tema `luft`, a base e macros iniciais sem dependencias de CDN;
- tema desconhecido usa fallback explicito para `luft`.

## Consequencias

Aplicacoes novas estendem um unico template e deixam de copiar CSS estrutural. Uma familia
nova nao muda componentes, mas precisa hospedar uma URL CSS local, registrar seu manifesto e
comprovar tokens, contraste, teclado, foco e movimento reduzido. Projetos antigos so recebem
o padrao quando migrarem seus templates para a base LuftBase.
