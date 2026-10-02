# Banco e schemas

## PostgreSQL

O banco corporativo e `luft_web`.

```text
core       -> tabelas compartilhadas do LuftBase
workspace  -> tabelas particulares do Luft-Workspace
control    -> tabelas particulares do Luft-Control
integrador -> tabelas particulares do Luft-Integrador
```

`public` nao recebe tabelas de aplicacao e nao concede `CREATE` a usuarios de runtime.

## Propriedade e acesso

- uma role sem login e proprietaria das estruturas;
- um migrador separado executa DDL;
- cada aplicacao possui login proprio;
- todas as aplicacoes recebem privilegios operacionais minimos no `core`;
- somente aplicacoes administrativas recebem privilegios de administracao;
- a aplicacao acessa somente seu schema particular.

## Models

Models do `core` pertencem ao LuftBase e nao sao parametros publicos. Models de negocio
pertencem aos projetos. O schema particular sera aplicado por `schema_translate_map`, depois
da validacao do campo `esquema` vindo do Vault.

## Evolucao

Esta e a ultima migracao manual das tabelas sistemicas para fora do SQL Server, mas nao a
ultima evolucao do banco. O schema `core` sera versionado por Alembic e mudancas seguirao a
estrategia expandir, migrar consumidores e somente depois contrair.

## Fronteiras disponiveis

| Fronteira | Banco | Escrita pelo LuftBase | Schema |
| --- | --- | --- | --- |
| `bancos.diretorio` | SQL Server `intec` | nunca | origem corporativa |
| `bancos.core` | PostgreSQL `luft_web` | sim | `core` |
| `bancos.aplicacao` | PostgreSQL `luft_web` | sim | recebido do Vault |

Core e aplicacao sao objetos e sessoes separados, mas compartilham um unico pool PostgreSQL.
Isso evita dobrar conexoes contra o mesmo servidor. O schema particular e aplicado por
`schema_translate_map`; modelos de negocio devem declarar o schema logico
`luft_aplicacao`. SQL textual nao e reescrito por esse mecanismo e deve ser evitado para
acesso a tabelas da aplicacao.

## Transacoes

```python
bancos = obter_luftbase().bancos

with bancos.core.leitura() as sessao:
    resultado = sessao.execute(...)

with bancos.aplicacao.unidade_trabalho() as sessao:
    sessao.add(entidade)
```

A unidade de trabalho confirma somente ao sair sem erro. Excecoes provocam rollback. Sessoes
residuais sao removidas no teardown do contexto Flask. Engines usam pool limitado,
`pool_pre_ping`, reciclagem e timeout; descarte de pools e uma operacao explicita de ciclo de
vida, nunca executada a cada requisicao.
