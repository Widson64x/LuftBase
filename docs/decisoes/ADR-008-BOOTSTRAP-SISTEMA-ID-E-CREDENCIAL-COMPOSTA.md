# ADR-008 — Resolucao de metadados via tb_sistema e credencial PostgreSQL composta

Status: substituido pelo ADR-009 em 2026-09-17.

## Contexto

As aplicacoes consumidoras repetiam variaveis de ambiente como `LUFT_APLICACAO_NOME` no `.env`,
alem de dependerem de um caminho monolitico no Vault (`luft/{ambiente}/postgresql/{aplicacao_id}`)
que duplicava host, porta e banco para cada aplicacao. Alem disso, os metadados oficiais do
sistema (nome, descricao, manutencao, icone, link e status ativo) ja residem na tabela
`core.tb_sistema`, gerando duplicidade e risco de divergencia entre o arquivo de configuracao
e o catalogo corporativo.

Para evitar ciclos de dependencia e aproveitar a arvore de segredos ja provisionada no Vault,
a aplicacao continua fornecendo seu identificador tecnico (`LUFT_APLICACAO_ID`) e seu ID
(`LUFT_SISTEMA_ID`) no `.env`, eliminando apenas as propriedades descritivas redundantes.

## Decisao

- `LUFT_APLICACAO_ID` permanece no `.env` como identificador tecnico estavel da aplicacao.
- `LUFT_SISTEMA_ID` permanece no `.env` como identificador numerico corporativo.
- `LUFT_APLICACAO_NOME` e eliminado do `.env` e carregado de `core.tb_sistema`.
- A versao da aplicacao e definida pelo artefato (`app.config["LUFT_APLICACAO_VERSAO"] = __version__`)
  e nao e gravada como verdade definitiva em `tb_sistema`.
- A estrutura de segredos do PostgreSQL no Vault separa conexao compartilhada de credenciais de aplicacao:
  - Conexao compartilhada: `{namespace}/{ambiente}/bancos/postgresql/conexoes/{alias}` (host, porta, banco, sslmode);
  - Credencial da aplicacao: `{namespace}/{ambiente}/bancos/postgresql/aplicacoes/{aplicacao_id}` (conexao, esquema, usuario, senha).
- O bootstrap le o segredo da aplicacao, depois o segredo da conexao referenciada e compoe a credencial.
- Com a conexao PostgreSQL estabelecida, o LuftBase consulta `core.tb_sistema` por `id_sistema` e enriquece a identidade:
  nome, descricao, ativo, em_manutencao, icone e link.
- O framework falha imediatamente se o sistema nao existir, estiver inativo ou houver inconsistencia.
- As variaveis de conveniencia `LUFT_APLICACAO_ID`, `LUFT_APLICACAO_NOME`, `LUFT_AMBIENTE` e `LUFT_SISTEMA_ID`
  continuam preenchidas em `app.config` para consumo por rotas, templates e extensoes.

## Consequencias

O `.env` das aplicacoes fica limpo sem metadados descritivos duplicados. Mudancas de servidor de banco
ocorrem em um unico segredo compartilhado (`conexoes/luft-web`). O framework garante que aplicacoes
inativas nao iniciem e centraliza os metadados de exibicao no catalogo oficial do core.
