# Persistencia e migrations

## Base ORM

`BaseLuft` e a unica base declarativa das tabelas mantidas pelo framework. Os modelos ficam
em `luftbase.persistencia.core` e usam sempre o schema fisico `core`. Projetos consumidores
nao fornecem models de permissao, auditoria, notificacao ou publicacao na inicializacao.

As 13 tabelas da baseline preservam o contrato migrado. Evolucoes posteriores pertencem ao
LuftBase e podem substituir estruturas ainda experimentais por revisoes Alembic explicitas.

As referencias a usuario e grupo do Luftinforma sao apenas identificadores logicos. Nao ha FK
entre bancos diferentes.

## Revisoes

```text
20260915_0001  baseline das 13 tabelas migradas
       |
20260915_0002  tb_preferenciausuario e tb_revisaocache
       |
20260916_0003  revisao e triggers de autorizacao
       |
20260916_0004  correlacao e indices de observabilidade
       |
20260916_0005  indices para cursores de conteudo
       |
20260917_0006  identidade transitoria de aplicacao
       |
20260917_0007  remove identificador paralelo; sistema_id vira identidade unica
       |
20260918_0008  auditoria detalhada e sessoes no core
       |
20260922_0009  modulos e autorizacao hierarquica
       |
20260922_0010  retrato de grupo e indices analiticos de auditoria
       |
20260923_0011  recria a trilha como tb_logacesso -> tb_logdetalhe -> tb_logs
```

A baseline permite reconstruir um `core` vazio. No banco que recebeu a migracao manual, ela
deve ser adotada, nao executada. As revisoes posteriores sao aplicadas em ordem e criam
somente estruturas novas ou alteracoes explicitamente documentadas. A revisao 0011 e uma
excecao destrutiva, aceita porque os logs do piloto em desenvolvimento eram descartaveis.

## Fluxo para o banco ja migrado

Use uma identidade temporaria de migracao com os privilegios DDL estritamente necessarios.
A conta normal da aplicacao deve continuar sem `CREATE`, `ALTER` ou `DROP`.

```powershell
flask banco validar --baseline-migrada
flask banco registrar-base --confirmar ADOTAR_CORE_EXISTENTE
flask banco versao
flask banco atualizar --confirmar ATUALIZAR_CORE
flask banco validar
```

O primeiro comando e somente leitura. `registrar-base` recusa a operacao se encontrar qualquer
divergencia ou uma revisao ja registrada. `atualizar` aplica somente revisoes posteriores a
baseline. Nenhum desses comandos aponta ou escreve no SQL Server.

## Banco novo

Em um PostgreSQL vazio, `flask banco atualizar --confirmar ATUALIZAR_CORE` executa a baseline
e depois as evolucoes ate o head. O operador deve confirmar previamente que a conexao aponta
para o banco correto e que existe backup/rollback operacional.

## Proibicoes

- nao chamar Alembic dentro de `PlataformaLuft.inicializar()`;
- nao usar `BaseLuft.metadata.create_all()` como mecanismo de producao;
- nao editar uma revisao que ja tenha sido aplicada;
- nao usar conta `admin`, `postgres` ou `sa` no runtime;
- nao registrar a baseline sem executar a validacao;
- nao usar downgrade destrutivo como rotina de rollback de producao.
