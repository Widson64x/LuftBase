# ADR-015 — Catalogo declarativo de aplicacoes e publicacao sob prefixo

Status: aceito em 2026-09-30.

## Contexto

A migracao do Luft-ConnectAir (sistema 1) foi a primeira de uma aplicacao satelite. Tres
lacunas apareceram: o core so sabia sincronizar o catalogo do Workspace (sistema 0); o
ConnectAir e publicado em `/Luft-ConnectAir` e o login, os redirecionamentos e o JavaScript do
LuftBase usavam caminhos absolutos a partir de `/`; e as mensagens de `flask.flash`, usadas em
todas as telas de importacao, nao eram exibidas pelo layout.

## Decisao

- Cada aplicacao declara `CatalogoAplicacao` (sistema, modulos e arvore `MODULO.RECURSO.ACAO`)
  em Python. `luftbase catalogo sincronizar --catalogo modulo:OBJETO` grava de forma aditiva e
  idempotente; nada e removido e vinculos de grupos e usuarios sao preservados.
- A role da aplicacao nao cadastra sistemas. A sincronizacao usa `--usuario-banco` (usuario de
  migracao, senha pedida no terminal) no mesmo host e banco do core resolvidos pelo Vault.
- `ativo` e `em_manutencao` sao operacionais e nunca revertidos pela sincronizacao.
- O catalogo exige exatamente uma permissao de acesso e pais declarados antes dos filhos.
  Aplicacoes nao devem reutilizar chaves do sistema 0: pela regra de escopo, a chave local
  homonima prevaleceria sobre a global.
- Toda URL gerada pelo LuftBase usa `request.script_root`; o JS recebe `window.LUFT_RAIZ`.
- `/_luftbase/mensagens` entrega tambem as mensagens de `flash`, convertidas em toasts.
- `exigir_ajax` substitui o `require_ajax` do LuftCore.

## Consequencias

Novas aplicacoes entram no core sem SQL manual e sem tela, com o catalogo versionado junto do
codigo. Remover uma permissao do catalogo nao a apaga do core; a limpeza continua sendo uma
decisao administrativa explicita.
