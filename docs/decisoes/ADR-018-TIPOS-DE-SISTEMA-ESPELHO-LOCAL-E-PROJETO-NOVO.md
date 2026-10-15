# ADR-018 - Tipos de sistema, espelho local do banco e `projeto novo`

Status: aceita (0.1.0a109)

## Contexto

Nem todo item do catalogo e uma aplicacao Flask do LuftBase: ha ferramentas em C# (Portal.WebApp), executaveis
(Luft-Informa, entregue pelo atualizador) e sistemas de terceiros (Luft-Digital). Elas precisam de card e link, mas nao de
schema, role nem segredo no Vault. Alem disso, cada dev precisava de um banco proprio e de um jeito unico de criar projetos.

## Decisao

1. `core.tb_sistema` ganha `integra_luftbase` (padrao true), `tipo_acesso` (`WEB`, `DOWNLOAD`, `SEM_ACESSO`; padrao `WEB`) e
   `url_download` (migracao aditiva `20261015_0016`). Regras (CHECK e validador unico): download exige URL; sistema
   integrado e sempre `WEB`; sistema externo nao tem schema, role nem segredo. `categoria` continua sendo so agrupamento visual.
2. `luftbase sistema externo` e o modal do Painel cadastram sistemas externos (sistema + modulo PLATAFORMA + permissao base
   que controla quem ve o card), sem provisionar nada.
3. `luftbase projeto novo` cria a pasta no padrao ADR-017 e, com credencial de operador pedida no terminal, cadastra sistema,
   schema, role (senha aleatoria) e segredo no Vault, e escreve o `.env`. So `desenvolvimento` e `homologacao`; producao
   continua pelo Workspace. O cadastro (`infraestrutura/cadastro_sistema.py`) e transacional: se o core nao confirma, o
   segredo do Vault e removido.
4. `luftbase banco espelhar` copia o banco de homologacao (integral, a pedido) para o PostgreSQL da propria maquina, por
   `pg_dump | pg_restore` sem arquivo em disco. Roles `luft_*` nao administrativas vao com o verificador SCRAM, entao as
   credenciais do Vault valem no espelho. Destino so loopback; origem nunca producao; senhas por variavel de ambiente.
5. Como o Vault e compartilhado, a aplicacao usa o espelho via `LUFT_BANCO_LOCAL_HOST`/`LUFT_BANCO_LOCAL_PORTA`
   (`ConfiguracaoBancoLocal`): troca so host e porta, aceita apenas loopback e e recusada em producao.

6. Fluxo de promocao de estrutura: o dev cria o sistema e as tabelas em desenvolvimento (banco limpo, `espelhar
   --somente-estrutura` quando precisar recriar), cadastra o sistema em homologacao pelo Workspace (que cria schema e role)
   e roda `luftbase banco comparar --schema <schema>`. O comando le so o catalogo dos dois ambientes e gera um `.sql` de
   criacao (sem `DROP`, sem alterar tipo/nulidade/padrao, transacional, repetivel) que o dev executa em homologacao e,
   se funcionar, em producao. O core nao entra: evolui por Alembic e so tem a revisao comparada.

7. Promocao das colunas de `tb_sistema` sem esperar o deploy do Workspace: `tools/sql/20261015_tb_sistema_tipo_de_integracao.sql`,
   repetivel e transacional, equivale a migracao `0016`, que por sua vez tolera o script ja aplicado.
8. O espelho concede as roles `luft_<schema>_dev_app` locais acesso ao core e ao schema restaurado, para a aplicacao rodar em
   `desenvolvimento` sobre o banco copiado.

9. O espelho tambem cria, no Vault de `desenvolvimento`, role e segredo por sistema do core copiado (`espelho_vault.py`), pois
   o core copiado traz os sistemas de homologacao e sem o segredo nenhuma aplicacao sobe em desenvolvimento. So escreve em
   `desenvolvimento`; conflito nunca e sobrescrito sem `--substituir-segredos`.

10. `categoria` passou de 3 para 7 valores (APLICACAO, API, SERVICO, FERRAMENTA, RELATORIO, INTEGRACAO, HUB), definidos em um
    unico modulo (`categorias_sistema.py`). Continua sendo so agrupamento visual; o comportamento vem de `integra_luftbase` e
    `tipo_acesso`. Migracao `20261015_0017` e script `tools/sql/20261015_tb_sistema_categorias.sql`.

## Consequencias

- Consumidores do catalogo (hub do Workspace) devem usar `url_download` para `DOWNLOAD` e nao abrir nada para `SEM_ACESSO`.
- A copia integral leva usuarios, sessoes e logs de homologacao para a maquina do dev.
- Pendente: tipo "API" (hoje um sistema integrado sem interface), cards do hub com os novos campos, e ensaio real contra
  PostgreSQL/Vault (os testes usam fakes e SQLite).
