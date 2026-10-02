# Roadmap do LuftBase

Cada marco precisa atender seus criterios de aceite antes de ser marcado como concluido.

## M00 — Fundacao documental

- [x] Registrar a missao e os limites do produto.
- [x] Criar regras permanentes para agentes e contribuidores.
- [x] Registrar as decisoes iniciais de arquitetura.
- [x] Inventariar as repeticoes mais relevantes dos projetos atuais.
- [x] Definir a API publica desejada.

## M01 — Pacote e configuracao

- [x] Criar pacote instalavel com layout `src`.
- [x] Padronizar Python 3.11 ou superior.
- [x] Criar modelo tipado de configuracao da aplicacao.
- [x] Normalizar aliases de ambiente.
- [x] Validar o identificador tecnico da aplicacao.
- [x] Resolver caminhos SQL Server e PostgreSQL no Vault.
- [x] Registrar a extensao no Flask sem estado global compartilhado.
- [x] Definir carregamento seguro dos segredos sem conectar no import.
- [x] Adicionar validacao completa de configuracao de producao.

## M02 — Vault e conexoes

- [x] Criar cliente Vault com contratos testaveis.
- [x] Ler `esquema` na credencial PostgreSQL.
- [x] Validar schema e impedir identificadores reservados.
- [x] Criar conexoes distintas para diretorio, core e aplicacao.
- [x] Implementar pool, `pool_pre_ping` e descarte.
- [x] Criar unidade de trabalho e teardown automatico.
- [x] Implementar health check por dependencia.

## M03 — Persistencia do core

- [x] Criar uma unica base ORM para as tabelas compartilhadas.
- [x] Mapear as 13 tabelas migradas em `core`.
- [x] Adicionar preferencia de usuario e revisao de cache.
- [x] Incorporar migrations Alembic ao pacote.
- [x] Criar comandos `banco versao`, `banco validar` e `banco atualizar`.

## M04 — Identidade e sessao corporativa

- [x] Criar modelos fixos de usuario e grupo para o diretorio corporativo.
- [x] Criar `UsuarioAutenticado` canonico.
- [x] Implementar LDAP com TLS configuravel.
- [x] Implementar sessao compartilhada e revogavel em Redis.
- [x] Centralizar cookies, SSO, renovacao e logout global.

## M05 — Autorizacao

- [x] Consultar somente as chaves solicitadas.
- [x] Implementar cache por requisicao e Redis.
- [x] Implementar invalidacao por revisao.
- [x] Criar decorators e contexto Jinja em portugues.
- [x] Implementar politica fail-closed.

## M06 — Auditoria e observabilidade

- [x] Encadear acesso HTTP, detalhe de dominio e retrato antes/depois.
- [x] Remover singletons e listeners globais.
- [x] Sanitizar dados sensiveis.
- [x] Adicionar correlacao, metricas, health e readiness.
- [x] Incorporar Auditoria como aba global do Painel de Controle.
- [x] Analisar acessos por sistema, usuario e grupo com escopo fail-closed.
- [x] Separar visualizacao, exportacao e dados sensiveis por permissao.

## M07 — Notificacoes e publicacoes

- [x] Reestruturar repositorios, servicos e rotas.
- [x] Implementar consultas incrementais e cache.
- [x] Preparar entrega via Redis/SSE sem perder o PostgreSQL como fonte definitiva.

## M08 — Design system e temas

- [x] Tornar o design system obrigatorio no perfil web.
- [x] Separar tema de modo claro/escuro/system.
- [x] Criar tokens semanticos.
- [x] Criar registro e manifesto de temas.
- [x] Persistir preferencia do usuario.
- [x] Adicionar testes visuais e de acessibilidade.

## M09 — CLI e scaffolding

- [x] Criar comandos de projeto, banco, Vault, diagnostico e temas.
- [x] Gerar aplicacoes novas conforme o padrao LuftBase.
- [x] Validar o conteudo do wheel.

## M10 — Piloto Luft-Workspace

- [x] Integrar e iniciar a pre-versao `0.1.0a4` no Workspace em Windows.
- [x] Remover models e inicializacoes sistemicas locais.
- [x] Centralizar bootstrap exclusivamente por `LUFT_SISTEMA_ID` e preservar a identidade visual.
- [x] Concluir e adotar a nova autorizacao hierarquica e catalogo de modulos (0.1.0a16).
- [ ] Validar Windows e Linux.
- [ ] Medir desempenho e preparar rollback.

## M12 — Integracoes corporativas

- [x] Liberar e-mail SMTP a partir do Vault, opcional por ambiente e validado na inicializacao.
- [x] Modo teste por segredo, envio em lote e auditoria por mensagem.
- [x] Layout e componentes padrao de e-mail no pacote.
- [x] Catalogo declarativo de modulos e permissoes para aplicacoes satelites.
- [x] Publicacao sob prefixo (`SCRIPT_NAME`) e ponte de `flash` para toasts.
- [ ] Migrar o Luft-ConnectAir do LuftCore para o LuftBase (codigo migrado; falta homologar).

## M11 — Estabilizacao 1.0

- [ ] Publicar alpha, beta e release candidate.
- [ ] Congelar a API publica.
- [ ] Concluir documentacao operacional.
- [ ] Publicar `1.0.0` somente depois do piloto homologado.
