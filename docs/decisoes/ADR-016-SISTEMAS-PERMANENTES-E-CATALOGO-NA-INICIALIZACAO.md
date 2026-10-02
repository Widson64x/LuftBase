# ADR-016 — Sistemas permanentes e catalogo conferido na inicializacao

Status: aceito em 2026-09-30. Complementa a ADR-015.

## Contexto

Excluir um sistema exigiria apagar cadastro, permissoes, logs, schema, role e segredo no
Vault, com risco de perda de dados e de referencias quebradas na auditoria. Ao mesmo tempo,
o fluxo desejado para um sistema novo e: cadastrar no Luft-Workspace, copiar o ID gerado para
`LUFT_SISTEMA_ID` e subir a aplicacao, que deve completar sozinha seus modulos e permissoes.

## Decisao

- Sistemas nunca sao excluidos. Cadastro, schema, role, segredo e dados existem para sempre.
- Um sistema pode ser **descontinuado** (`tb_sistema.ativo = false`). Toda requisicao recebe
  a pagina `luftbase/pages/descontinuado.html` (HTTP 410; JSON 410 para APIs), sem bypass;
  apenas saude e logout respondem. A reativacao e feita pelo Workspace.
- A permissao `CONFIGURACOES.SISTEMAS.EXCLUIR` foi substituida por
  `CONFIGURACOES.SISTEMAS.DESATIVAR`, exigida sempre que `Ativo` muda na edicao do sistema.
- `PlataformaLuft(catalogo=CATALOGO)`: na inicializacao o LuftBase calcula as pendencias do
  catalogo da aplicacao em relacao ao core e, somente se houver, grava modulos e permissoes.
  Nao grava `tb_sistema` (pertence ao Workspace) e falha com mensagem clara se o sistema nao
  existir. O sistema 0 continua usando o catalogo do proprio LuftBase via bootstrap.
- Isso e escrita de dados (DML) com a role da aplicacao, nao DDL nem migration; a regra de
  nao executar migrations na inicializacao continua valendo.
- Permissoes podem declarar `modulo_codigo` para ficar no modulo `PLATAFORMA` que o
  Workspace cria junto com o sistema.

- O cadastro pela tela pode provisionar banco e Vault com credenciais de operador informadas
  no modal e descartadas ao fim da requisicao; o runtime do Workspace continua sem conta
  administrativa e sem token de escrita no Vault.

## Consequencias

Subir uma aplicacao nova basta para o core refletir o `Catalogo.py` dela. Remover uma chave
do catalogo nao a apaga do core. A role da aplicacao precisa de SELECT, INSERT e UPDATE em
`core.tb_modulo` e `core.tb_permissao`, o que o bootstrap ja concede.
