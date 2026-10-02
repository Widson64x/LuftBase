# ADR-009 — Sistema ID como bootstrap unico

Status: aceito em 2026-09-17. Restabelecido como decisao definitiva; substitui o ADR-010.

## Contexto

Manter `LUFT_APLICACAO_ID` e `LUFT_SISTEMA_ID` no `.env` criava duas identidades para o
mesmo consumidor e permitia combinacoes inconsistentes. A conexao compartilhada ja evita
duplicar host, porta e banco; faltava remover tambem a repeticao do slug nas aplicacoes.

## Decisao

- `LUFT_SISTEMA_ID` e a unica identidade de bootstrap mantida pela aplicacao.
- O runtime le `{namespace}/{ambiente}/bancos/postgresql/sistemas/{sistema_id}`.
- Esse segredo contem `identificador`, `sistema_id`, `conexao`, `esquema`, `usuario` e `senha`.
- O LuftBase recusa o segredo se seu `sistema_id` divergir do ID solicitado.
- Host, porta, banco, tipo e `sslmode` ficam somente em `conexoes/{alias}`.
- Nome, descricao, status, manutencao, icone e link ficam em `core.tb_sistema`.
- A versao continua pertencendo ao artefato da aplicacao, nao ao catalogo nem ao Vault.
- `aplicacoes/{slug}` e aceito apenas como estrutura de transicao para criar, com CAS 0,
  a associacao canonica `sistemas/{id}`.

## Consequencias

Uma mudanca de servidor exige alterar um segredo de conexao por ambiente, mesmo com centenas
de schemas. Cada aplicacao mantem apenas o ID numerico em configuracao. O custo e exigir uma
associacao explicita no Vault antes de instalar esta versao; o runtime nao tenta adivinhar slug,
usuario ou schema e falha de forma segura quando a associacao nao existe.
