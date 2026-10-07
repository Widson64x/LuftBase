# Documentacao do LuftBase

## Comece por aqui

1. [Visao do produto](01-VISAO-DO-PRODUTO.md)
2. [Arquitetura](02-ARQUITETURA.md)
3. [API publica desejada](03-API-PUBLICA-DESEJADA.md)
4. [Configuracao e Vault](04-CONFIGURACAO-E-VAULT.md)
5. [Banco e schemas](05-BANCO-E-SCHEMAS.md)
6. [Padroes de codigo](06-PADROES-DE-CODIGO.md)
7. [Design system e temas](07-DESIGN-SYSTEM-E-TEMAS.md)
8. [Inventario do LuftCore](08-INVENTARIO-LUFTCORE.md)
9. [Persistencia e migrations](09-PERSISTENCIA-E-MIGRACOES.md)
10. [Identidade e sessao](10-IDENTIDADE-E-SESSAO.md)
11. [Autorizacao](11-AUTORIZACAO.md)
12. [Auditoria e observabilidade](12-AUDITORIA-E-OBSERVABILIDADE.md)
13. [Notificacoes e publicacoes](13-NOTIFICACOES-E-PUBLICACOES.md)
14. [Painel de Controle](14-PAINEL-DE-CONTROLE.md)
15. [Auditoria analitica, "Ao vivo" e controle de sessoes](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md)
16. [Perfil do usuario](16-PERFIL-DO-USUARIO.md)
17. [Servidor, rede e fuso horario](17-SERVIDOR-REDE-E-FUSO.md)
18. [Variaveis de ambiente (referencia)](18-VARIAVEIS-DE-AMBIENTE.md)
19. [Guia da aplicacao satelite](19-GUIA-DA-APLICACAO-SATELITE.md)
20. [Operacao e deploy](20-OPERACAO-E-DEPLOY.md)
21. [Conteudo rico e notas de atualizacao](21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md)

### Por onde comecar, conforme o seu papel

- **Vou criar ou manter um sistema Luft**: 19, 11, 04, 18 e o ADR-017.
- **Cuido do servidor ou do deploy**: 20, 17, 18, 14.
- **Preciso entender login, sessao e permissao**: 10, 11, 15.
- **Investigo um problema**: 15 (auditoria), 20 (quando algo da errado), 12.
- **Quero o panorama**: 01, 02 e o [README](../README.md).

## Decisoes arquiteturais

- [ADR-001: novo produto](decisoes/ADR-001-NOVO-PRODUTO.md)
- [ADR-002: API unica](decisoes/ADR-002-API-UNICA.md)
- [ADR-003: schemas](decisoes/ADR-003-SCHEMAS.md)
- [ADR-004: evolucao gradual](decisoes/ADR-004-EVOLUCAO-GRADUAL.md)
- [ADR-005: credenciais e conexoes](decisoes/ADR-005-CREDENCIAIS-E-CONEXOES.md)
- [ADR-006: conteudo incremental](decisoes/ADR-006-CONTEUDO-INCREMENTAL.md)
- [ADR-007: temas e preferencias](decisoes/ADR-007-TEMAS-E-PREFERENCIAS.md)
- [ADR-008: bootstrap inicial composto (substituido)](decisoes/ADR-008-BOOTSTRAP-SISTEMA-ID-E-CREDENCIAL-COMPOSTA.md)
- [ADR-009: sistema ID como bootstrap unico](decisoes/ADR-009-SISTEMA-ID-COMO-BOOTSTRAP-UNICO.md)
- [ADR-011: autorizacao hierarquica e modulos](decisoes/ADR-011-AUTORIZACAO-HIERARQUICA-E-MODULOS.md)
- [ADR-012: auditoria analitica e retrato historico](decisoes/ADR-012-AUDITORIA-ANALITICA-E-RETRATO-HISTORICO.md)
- [ADR-013: trilha de logs encadeada e diagnostico local](decisoes/ADR-013-TRILHA-DE-LOGS-ENCADEADA.md)
- [ADR-014: integracao de e-mail](decisoes/ADR-014-INTEGRACAO-DE-EMAIL.md)
- [ADR-015: catalogo de aplicacoes e prefixo](decisoes/ADR-015-CATALOGO-DE-APLICACOES-E-PREFIXO.md)
- [ADR-016: sistemas permanentes e catalogo na inicializacao](decisoes/ADR-016-SISTEMAS-PERMANENTES-E-CATALOGO-NA-INICIALIZACAO.md)
- [ADR-017: padrao de projeto das aplicacoes](decisoes/ADR-017-PADRAO-DE-PROJETO-DAS-APLICACOES.md)

O [Roadmap](../ROADMAP.md) controla marcos. O [Handoff](../HANDOFF.md) registra o estado
operacional para continuidade entre pessoas e agentes.
