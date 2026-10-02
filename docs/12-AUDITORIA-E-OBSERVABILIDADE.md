# Auditoria e observabilidade

## Duas trilhas, cinco fontes

O LuftBase nao trata auditoria relacional e diagnostico de processo como a mesma coisa.

```text
TRILHA ESTRUTURADA (PostgreSQL)
tb_logacesso                 uma requisicao e sua resposta HTTP
└── tb_logdetalhe            acao, erro ou ocorrencia daquela requisicao
    └── tb_logs              retrato imutavel dos dados antes e depois

DIAGNOSTICO LOCAL (filesystem do processo)
Logs/luftbase.log            log fisico rotativo, sanitizado e abrangente
Logs/temp/*.temp.log         raiz temporaria JSONL de cada processo
```

As tres tabelas possuem finalidades diferentes e nunca repetem o mesmo payload. A identidade
historica do usuario e do grupo fica no detalhe. `tb_logs` herda essa identidade pelo vinculo
com o pai, evitando copias divergentes.

## Integridade da cadeia

`tb_logdetalhe.id_logacesso` e opcional somente para tarefas internas ou assicronas que nao
nasceram de HTTP. Durante uma requisicao, o detalhe e registrado antes do `after_request` e
recebe o mesmo `id_correlacao`. Ao persistir o acesso, o repositorio associa, na mesma
transacao, todos os detalhes pendentes daquela correlacao e daquele sistema.

O FK composto impede ligar um detalhe ao acesso de outro sistema. As exclusoes seguem a
cadeia `acesso -> detalhes -> alteracoes` com `ON DELETE CASCADE`. Excluir um sistema tambem
remove sua trilha. Identificadores de usuario e grupo nao possuem FK porque continuam vindo
do SQL Server somente leitura.

## Acesso HTTP

O hook grava a regra da rota, metodo, status, duracao, identidade, grupo, IP, permissao
exigida, decisao e query string sanitizada. Corpo e cabecalhos nao sao capturados. Rotas de
saude, prontidao e metricas nao geram acesso.

Toda requisicao recebe `X-Correlation-ID`. Um valor do cliente so e reutilizado se respeitar
o formato limitado; caso contrario, a plataforma gera um identificador aleatorio.

## Detalhes e alteracoes

O servico de negocio registra deliberadamente o detalhe. Quando informa dados anteriores ou
novos, o repositorio cria tambem uma linha em `tb_logs`, na mesma transacao:

```python
from luftbase import SeveridadeAuditoria, registrar_evento_auditoria

id_detalhe = registrar_evento_auditoria(
    acao="APROVAR",
    recurso="BUDGET",
    id_recurso="2026-001",
    descricao="Budget aprovado.",
    dados_anteriores={"status": "PENDENTE"},
    dados_novos={"status": "APROVADO"},
    severidade=SeveridadeAuditoria.ALTA,
)
```

`tb_logdetalhe` guarda o que ocorreu e sua severidade. `tb_logs` guarda o tipo da mudanca,
os caminhos alterados e os estados sanitizados anterior/novo. O repositorio classifica cada
retrato como `CRIACAO`, `ALTERACAO`, `EXCLUSAO` ou `SUBSTITUICAO`.

Nao existem listeners globais do SQLAlchemy: leituras, rollbacks e manutencoes internas do
ORM nao viram auditoria por acidente.

## Logs fisicos e raiz temporaria

O arquivo fisico possui rotacao diaria e retencao local de 30 arquivos. A leitura do painel
aceita somente nomes descobertos dentro do diretorio configurado, limita cada consulta a 500
linhas e le no maximo os 2 MiB finais; caminhos arbitrarios sao rejeitados.

A raiz temporaria mantem os ultimos mil registros em memoria e escreve o mesmo fluxo
sanitizado em `Logs/temp/luftbase-{pid}.temp.log`. Cada processo tem seu arquivo. Arquivos
temporarios inativos com mais de dois dias sao removidos na inicializacao. Essa fonte serve
para diagnostico imediato, nao como historico autoritativo.

Erros internos do LuftBase tambem chegam a essas duas fontes por `LoggerTecnico`. Mensagens
de excecao, senha, token, cookie e cabecalho de autorizacao nunca sao gravados em claro.

## Painel analitico

**Auditoria & Analise** e uma aba global do Painel de Controle, separada de Configuracoes
Gerais. Ela apresenta:

- KPIs, serie temporal e rankings de rotas, usuarios, grupos e sistemas;
- filtros com periodo maximo de 90 dias;
- abas Acessos HTTP, Detalhes, Alteracoes, Raiz temporaria e Arquivos fisicos;
- drawer que percorre toda a cadeia e mostra antes/depois quando autorizado;
- exportacao CSV das tres fontes estruturadas, com no maximo cinco mil linhas e protecao
  contra formulas de planilha.

As fontes locais mostram somente a instancia da aplicacao aberta. O sistema `0` consolida
as tabelas de todos os sistemas, mas nao consegue ler arquivos que estejam em outro host ou
processo sem uma futura centralizacao externa.

## Permissoes

```text
OBSERVABILIDADE.GERENCIAR
|-- OBSERVABILIDADE.AUDITORIA.VISUALIZAR
|-- OBSERVABILIDADE.AUDITORIA.EXPORTAR
`-- OBSERVABILIDADE.DADOS_SENSIVEIS.VISUALIZAR
```

Visualizacao comum nao revela parametros, traceback, estados anterior/novo nem fontes
locais. Raiz temporaria e arquivos fisicos exigem simultaneamente as permissoes de auditoria
e dados sensiveis. A exportacao nunca inclui os estados anterior/novo.

## Contrato HTTP interno

```text
GET /configuracoes/api/auditoria/resumo
GET /configuracoes/api/auditoria/acessos
GET /configuracoes/api/auditoria/detalhes
GET /configuracoes/api/auditoria/alteracoes
GET /configuracoes/api/auditoria/detalhes/{acesso|detalhe|alteracao}/{id}
GET /configuracoes/api/auditoria/temporarios
GET /configuracoes/api/auditoria/fisicos?arquivo={nome}
GET /configuracoes/api/auditoria/exportar?tipo={acesso|detalhe|alteracao}
```

## Operacao

A revisao `20260923_0011` e deliberadamente destrutiva: descarta `tb_logacesso` e
`tb_logdetalhe` experimentais e recria as tres tabelas vazias. Ela so deve ser aplicada em
ambientes cuja trilha anterior tenha sido declarada descartavel. Migrations nunca rodam no
startup da aplicacao.

Antes do uso real em producao ainda devem ser definidos retencao do PostgreSQL,
particionamento por data, arquivamento e centralizacao dos arquivos fisicos de multiplas
instancias.
