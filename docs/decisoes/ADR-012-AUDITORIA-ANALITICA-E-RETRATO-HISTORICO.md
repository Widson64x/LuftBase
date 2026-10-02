# ADR-012 — Auditoria analitica e retrato historico de identidade

Status: aceito em 2026-09-23.

O desenho fisico das tabelas foi ampliado pela ADR-013. As decisoes de escopo, retrato
historico e autorizacao deste documento permanecem validas.

## Contexto

Os registros de acesso e eventos ja existiam, mas nao havia uma experiencia integrada para
investigar volume, falhas, negacoes e comportamento por sistema, usuario ou grupo. Consultar
o grupo atual no SQL Server durante cada analise apagaria a realidade historica e criaria
dependencia operacional de um banco estritamente somente leitura.

## Decisao

- Auditoria analitica pertence ao LuftBase e aparece como aba global do Painel de Controle.
- Configuracoes Gerais fica reservada a parametros particulares do sistema atual.
- `tb_logacesso` e `tb_logdetalhe` guardam `codigo_grupo` e `nome_grupo` como retrato do
  instante do evento, sem FK entre bancos; `tb_logs` herda o retrato do detalhe pai.
- A trilha persistente no PostgreSQL e autoritativa; o buffer tecnico e apenas diagnostico
  local e volatil.
- Consultas sao limitadas, paginadas e filtradas pelo `LUFT_SISTEMA_ID` no SQL.
- Sistema `0` permite consolidacao global, nunca bypass de autorizacao.
- Visualizacao, exportacao e dados sensiveis sao capacidades independentes.
- Exportacoes nao incluem payloads sensiveis e neutralizam formulas de planilha.
- A interface limita consultas a 90 dias e exportacoes a cinco mil linhas.

## Consequencias

A analise de grupos continua correta mesmo quando o usuario troca de grupo. O painel nao
precisa consultar o SQL Server e pode operar com indices do PostgreSQL. Em contrapartida,
retencao, particionamento e arquivamento deverao ser definidos antes de volumes de producao
exigirem manutencao automatica.
