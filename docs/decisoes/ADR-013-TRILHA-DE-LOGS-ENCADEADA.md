# ADR-013 — Trilha de logs encadeada e diagnostico local

Status: aceito em 2026-09-23.

## Contexto

O contrato anterior colocava o evento de dominio, os estados anterior/novo e o erro tecnico
em `tb_logdetalhe`. Ao mesmo tempo, a interface chamava o buffer local de log tecnico sem
distingui-lo do arquivo fisico. Isso tornava a finalidade das fontes ambigua e o vinculo com
a requisicao frequentemente ficava vazio, pois o acesso HTTP so era criado no
`after_request`.

## Decisao

- `tb_logacesso` e a raiz HTTP.
- `tb_logdetalhe` descreve uma acao, erro ou ocorrencia e guarda a identidade historica.
- `tb_logs` e filha obrigatoria de um detalhe e guarda somente o retrato antes/depois.
- O acesso liga detalhes pendentes pelo par `id_sistema + id_correlacao` na mesma transacao.
- O FK composto proibe vinculo entre sistemas diferentes.
- As tabelas usam cascata; detalhes sem HTTP continuam permitidos para tarefas internas.
- Arquivo fisico rotativo e raiz temporaria por processo sao fontes locais separadas do
  PostgreSQL.
- Fontes locais e payloads antes/depois exigem permissao de dados sensiveis.
- A revisao 0011 descarta os dados experimentais existentes por decisao explicita do piloto.

## Consequencias

A trilha pode ser percorrida sem repetir identidade e sem inferir relacoes por texto. As
alteracoes ficam analisaveis separadamente dos erros e a interface deixa claro quais dados
sao locais. Em contrapartida, uma investigacao que envolva varios hosts ainda exige consultar
cada instancia ate existir um agregador corporativo de logs.
