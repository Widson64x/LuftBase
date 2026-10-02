# Inventario do LuftCore e dos consumidores

O LuftCore 0.4.x e os projetos atuais foram inspecionados apenas para identificar capacidades
uteis e repeticoes. Este documento nao autoriza copiar sua estrutura.

## Capacidades a preservar

- integracao Flask e application factory;
- respostas e mensagens padronizadas;
- decorators de permissao;
- auditoria de acesso e de dominio;
- notificacoes;
- publicacoes e notas de atualizacao;
- templates, macros e componentes aproveitaveis;
- acesso seguro ao Vault;
- repositorios, lotes e retentativa quando houver uso comprovado;
- painel de sistemas e manutencao;
- CLI como ponto de automacao.

## Problemas que nao devem ser transportados

- uma unica fabrica de sessao para identidade e tabelas sistemicas;
- models recebidos pela aplicacao consumidora;
- models fixados em `intec.dbo`;
- fachadas duplicadas em portugues e ingles;
- alias com grafia incorreta;
- herancas sem comportamento;
- `**kwargs` como mecanismo de compatibilidade indefinida;
- flags que permitem desativar o padrao visual;
- mapeamento manual do usuario em cada aplicacao;
- singleton global de auditoria;
- listener instalado na classe global `Session`;
- cache e mensagens somente em memoria por processo;
- `NullPool` obrigatorio para todos os bancos;
- sessao de logging sem fechamento garantido;
- LDAP simples sem TLS;
- leitura de variaveis de ambiente espalhada;
- poucos testes para uma superficie publica extensa.

## Repeticoes encontradas nos projetos

- `load_dotenv` em diversos modulos;
- normalizacao independente de ambiente;
- resolucao repetida de caminhos do Vault;
- criacao manual das engines e sessoes;
- configuracao repetida de cookies e SSO;
- aplicacao manual de `ProxyFix`;
- registro manual de seguranca e auditoria;
- registro manual de notificacoes e logging;
- ajuste manual de endpoints para `ROUTE_PREFIX`;
- teardown repetido;
- mapeamento repetido dos atributos do usuario;
- wrappers locais para respostas e auditoria.

Esses itens sao candidatos a responsabilidade direta da `PlataformaLuft`.

