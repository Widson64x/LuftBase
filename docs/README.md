# Documentacao do LuftBase

Esta pasta tem **27 documentos** e **18 decisoes de arquitetura**. Voce nao precisa ler tudo: escolha pelo que esta fazendo.

## Por onde comecar

| Eu quero... | Leia, nesta ordem |
|---|---|
| **criar um sistema novo** do zero ate producao | [22 Guia rapido](22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md) -> [19 Aplicacao satelite](19-GUIA-DA-APLICACAO-SATELITE.md) -> [20 Operacao e deploy](20-OPERACAO-E-DEPLOY.md) |
| **ter um banco meu** copiado de homologacao e levar minhas tabelas para frente | [25 Banco local e promocao](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md) -> [23 CLI](23-REFERENCIA-DA-CLI.md) |
| **cadastrar** um sistema (inclusive um executavel ou uma ferramenta em C#) | [24 Sistemas e catalogo](24-SISTEMAS-E-CATALOGO.md) -> [14 Painel de Controle](14-PAINEL-DE-CONTROLE.md) |
| entender **login, sessao e permissao** | [10 Identidade e sessao](10-IDENTIDADE-E-SESSAO.md) -> [11 Autorizacao](11-AUTORIZACAO.md) -> [15 Controle de sessoes](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md) |
| cuidar do **servidor, deploy e incidentes** | [20 Operacao e deploy](20-OPERACAO-E-DEPLOY.md) -> [17 Servidor e rede](17-SERVIDOR-REDE-E-FUSO.md) -> [26 Solucao de problemas](26-SOLUCAO-DE-PROBLEMAS.md) |
| **aprender fazendo** (tela, API, permissao, tabela, teste) e **migrar um sistema legado** | [28 Tutorial pratico](28-TUTORIAL-PRATICO-DO-DESENVOLVEDOR.md) -> [19 Aplicacao satelite](19-GUIA-DA-APLICACAO-SATELITE.md) |
| **resolver um erro** agora | [26 Solucao de problemas](26-SOLUCAO-DE-PROBLEMAS.md) (procure pela mensagem) |
| ter o **panorama** do produto | [01 Visao](01-VISAO-DO-PRODUTO.md) -> [02 Arquitetura](02-ARQUITETURA.md) -> [27 Glossario](27-GLOSSARIO.md) |
| **contribuir** com o LuftBase | [AGENTS.md](../AGENTS.md) -> [06 Padroes e contribuicao](06-PADROES-DE-CODIGO.md) |

Palavra desconhecida? [Glossario](27-GLOSSARIO.md).

## Guias do dia a dia (como fazer)

| # | Documento | Para que serve |
|---|---|---|
| 28 | [Tutorial pratico do desenvolvedor](28-TUTORIAL-PRATICO-DO-DESENVOLVEDOR.md) | aprender fazendo: um sistema de exemplo completo (catalogo, tabela, rota, API, teste) e o roteiro de migracao de um sistema legado |
| 22 | [Guia rapido do desenvolvedor](22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md) | o caminho completo: preparar a maquina, `projeto novo`, `.env`, subir, cadastrar em homologacao, levar tabelas, publicar |
| 19 | [Guia da aplicacao satelite](19-GUIA-DA-APLICACAO-SATELITE.md) | o que o LuftBase entrega, o que a aplicacao escreve, permissoes, bancos e armadilhas |
| 25 | [Banco local e promocao de estrutura](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md) | `banco espelhar`, `atualizar-core`, `comparar`, scripts SQL do core |
| 24 | [Sistemas e catalogo](24-SISTEMAS-E-CATALOGO.md) | tipos (integrado, externo web, download), categorias, o que um cadastro cria |
| 20 | [Operacao e deploy](20-OPERACAO-E-DEPLOY.md) | ambientes, fluxo de uma mudanca, workflow de deploy, rollback, checklist, rotina |
| 26 | [Solucao de problemas](26-SOLUCAO-DE-PROBLEMAS.md) | erros reais com mensagem, causa e correcao |

## Referencia

| # | Documento | Para que serve |
|---|---|---|
| 23 | [Referencia da CLI](23-REFERENCIA-DA-CLI.md) | todos os comandos `luftbase`, opcoes e cuidados |
| 03 | [API publica](03-API-PUBLICA-DESEJADA.md) | tudo o que se importa de `luftbase` e como usar |
| 18 | [Variaveis de ambiente](18-VARIAVEIS-DE-AMBIENTE.md) | cada variavel, valor padrao e efeito |
| 04 | [Configuracao e Vault](04-CONFIGURACAO-E-VAULT.md) | o `.env` minimo, caminhos e formato dos segredos |
| 27 | [Glossario](27-GLOSSARIO.md) | os termos usados na documentacao e na CLI |

## A plataforma, por assunto

| # | Documento | Assunto |
|---|---|---|
| 01 | [Visao do produto](01-VISAO-DO-PRODUTO.md) | para que serve, para quem, o que e e o que nao e do LuftBase |
| 02 | [Arquitetura](02-ARQUITETURA.md) | camadas, inicializacao, caminho de uma requisicao, onde cada dado mora |
| 05 | [Banco e schemas](05-BANCO-E-SCHEMAS.md) | PostgreSQL por ambiente, schemas, tabelas do `core`, roles |
| 09 | [Persistencia e migrations](09-PERSISTENCIA-E-MIGRACOES.md) | modelos do core e historico das revisoes do Alembic |
| 10 | [Identidade e sessao](10-IDENTIDADE-E-SESSAO.md) | LDAP, sessao no PostgreSQL, cookie compartilhado, logout global |
| 11 | [Autorizacao](11-AUTORIZACAO.md) | permissoes em arvore, heranca, cache, decisao que nega na duvida |
| 12 | [Auditoria e observabilidade](12-AUDITORIA-E-OBSERVABILIDADE.md) | trilha de acesso, evento e antes/depois, metricas, logs |
| 15 | [Auditoria analitica e controle de sessoes](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md) | paineis analiticos, "Ao vivo", derrubar sessoes |
| 13 | [Notificacoes e publicacoes](13-NOTIFICACOES-E-PUBLICACOES.md) | avisos, comunicados, tempo real |
| 21 | [Conteudo rico e notas de atualizacao](21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md) | Markdown seguro e notas de versao |
| 14 | [Painel de Controle](14-PAINEL-DE-CONTROLE.md) | abas, sistemas, variaveis, servicos, integracoes |
| 16 | [Perfil do usuario](16-PERFIL-DO-USUARIO.md) | tela de perfil, preferencias, sessoes da pessoa |
| 07 | [Design system e temas](07-DESIGN-SYSTEM-E-TEMAS.md) | layout, temas, componentes, seletor de icones |
| 17 | [Servidor, rede e fuso horario](17-SERVIDOR-REDE-E-FUSO.md) | Waitress, prefixo de URL, IP real, fuso de Brasilia |
| 06 | [Padroes de codigo e contribuicao](06-PADROES-DE-CODIGO.md) | regras de codigo, portao de qualidade, receitas |
| 08 | [Inventario do LuftCore](08-INVENTARIO-LUFTCORE.md) | *historico*: o que se observou no sistema antigo |

## Decisoes arquiteturais (ADR)

Cada decisao conta o contexto, o que foi decidido e as consequencias. Leia quando quiser saber **por que** algo e do jeito que e.

| ADR | Tema |
|---|---|
| [001](decisoes/ADR-001-NOVO-PRODUTO.md) | criar o LuftBase como produto novo (repositorio e pacote novos; o LuftCore fica para rollback) |
| [002](decisoes/ADR-002-API-UNICA.md) | uma extensao e uma API publica em portugues, sem aliases |
| [003](decisoes/ADR-003-SCHEMAS.md) | schema `core` fixo e schema particular dinamico (vem do segredo no Vault) |
| [004](decisoes/ADR-004-EVOLUCAO-GRADUAL.md) | evolucao gradual (piloto no Workspace) e migrations explicitas |
| [005](decisoes/ADR-005-CREDENCIAIS-E-CONEXOES.md) | credenciais e conexoes: Vault KV v2, tokens protegidos, pools sem excesso |
| [006](decisoes/ADR-006-CONTEUDO-INCREMENTAL.md) | notificacoes e publicacoes incrementais, com o PostgreSQL como fonte definitiva |
| [007](decisoes/ADR-007-TEMAS-E-PREFERENCIAS.md) | familia de tema separada do modo visual (claro, escuro, sistema) |
| [008](decisoes/ADR-008-BOOTSTRAP-SISTEMA-ID-E-CREDENCIAL-COMPOSTA.md) | bootstrap com credencial composta *(substituido)* |
| [009](decisoes/ADR-009-SISTEMA-ID-COMO-BOOTSTRAP-UNICO.md) | `LUFT_SISTEMA_ID` como bootstrap unico |
| [010](decisoes/ADR-010-APLICACAO-ID-E-VAULT-V2.md) | aplicacao ID e layout Vault v2 *(rejeitado; substituido pelo ADR-009)* |
| [011](decisoes/ADR-011-AUTORIZACAO-HIERARQUICA-E-MODULOS.md) | autorizacao hierarquica e modulos |
| [012](decisoes/ADR-012-AUDITORIA-ANALITICA-E-RETRATO-HISTORICO.md) | auditoria analitica e retrato historico |
| [013](decisoes/ADR-013-TRILHA-DE-LOGS-ENCADEADA.md) | trilha de logs encadeada e diagnostico local |
| [014](decisoes/ADR-014-INTEGRACAO-DE-EMAIL.md) | integracao de e-mail |
| [015](decisoes/ADR-015-CATALOGO-DE-APLICACOES-E-PREFIXO.md) | catalogo declarativo de aplicacoes e publicacao sob prefixo de URL |
| [016](decisoes/ADR-016-SISTEMAS-PERMANENTES-E-CATALOGO-NA-INICIALIZACAO.md) | sistemas permanentes e catalogo na inicializacao |
| [017](decisoes/ADR-017-PADRAO-DE-PROJETO-DAS-APLICACOES.md) | padrao de projeto das aplicacoes |
| [018](decisoes/ADR-018-TIPOS-DE-SISTEMA-ESPELHO-LOCAL-E-PROJETO-NOVO.md) | tipos de sistema, espelho local, `projeto novo` e promocao de estrutura |

## Acompanhamento do projeto

- [Roadmap](../ROADMAP.md): marcos, o que esta feito e o que falta.
- [CHANGELOG](../CHANGELOG.md): o que mudou em cada versao.
- [Handoff](../HANDOFF.md): estado operacional e o proximo passo exato, para passar o trabalho entre pessoas e agentes.
- [AGENTS.md](../AGENTS.md): regras de quem contribui (pessoas e agentes).

## Como estes documentos sao escritos

- Descrevem o que o codigo **faz**, conferido; comportamento que surpreende ou lacuna conhecida vem **dito**.
- Escritos em portugues **sem acentos** (como o codigo), com diagramas em Mermaid (o GitHub os desenha).
- Comandos em blocos de codigo, prontos para copiar; **nunca** ha senha, token ou segredo real nos exemplos.
- Mudou comportamento? Atualize o documento no mesmo commit (tabela "o que atualizar quando" no [doc 06](06-PADROES-DE-CODIGO.md#documentacao-o-que-atualizar-quando)).
