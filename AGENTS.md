# Instrucoes para agentes e contribuidores

Este arquivo e a primeira leitura obrigatoria antes de alterar o LuftBase.

## Missao

O LuftBase e a plataforma corporativa instalada nas aplicacoes Python da Luft. Ele deve
eliminar configuracoes e implementacoes repetidas de infraestrutura, identidade, sessao,
autorizacao, auditoria e interface, preservando nos projetos apenas regras de negocio.

## Regras inviolaveis

- Leia `ROADMAP.md`, `HANDOFF.md` e os documentos relacionados ao marco atual.
- Desenvolva exclusivamente dentro dos contratos nativos do LuftBase.
- Nunca altere dados ou estruturas do SQL Server. Ele e fonte somente de leitura para o
  diretorio corporativo.
- Nunca use usuario administrativo de banco no runtime de uma aplicacao.
- Nao exponha modelos sistemicos na API de inicializacao.
- Nao adicione flags para desabilitar elementos obrigatorios do perfil web, como tokens,
  tema, CSS base, acessibilidade e JavaScript essencial.
- Nao use uma sessao SQLAlchemy para bancos diferentes.
- Nao execute migrations automaticamente durante a inicializacao da aplicacao.
- Nao introduza fallback silencioso do PostgreSQL para o SQL Server.
- Nao leia variaveis de ambiente de forma dispersa. Toda configuracao passa pelo pacote
  `luftbase.configuracao`.
- Nao use singletons globais dependentes de uma aplicacao Flask.
- Nao registre listeners na classe global `sqlalchemy.orm.Session`.
- Nunca grave tokens, senhas, cookies ou cabecalhos de autorizacao em logs.

## Codigo

- A API publica, nomes internos, docstrings e mensagens devem ser escritos em portugues.
- Identificadores Python nao usam acentos.
- Siga PEP 8, PEP 257 e use type hints.
- Comentarios devem explicar motivos, invariantes ou riscos; nao repetir o que o codigo diz.
- Prefira composicao, protocolos e injecao interna de dependencias a herancas vazias.
- Nao mantenha aliases em ingles na nova API.
- Uma funcao deve ter uma responsabilidade observavel e um nome coerente com essa funcao.
- Nao use `**kwargs` para esconder uma API publica indefinida.
- Erros de configuracao devem falhar cedo e listar claramente o campo invalido.

## Qualidade obrigatoria

Antes de concluir um marco:

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
python -m pytest
python -m build
```

Se uma ferramenta ainda nao estiver instalada, registre isso no `HANDOFF.md`. Nunca afirme
que uma validacao passou sem executa-la.

## Documentacao e continuidade

- Toda decisao arquitetural relevante deve ser registrada em `docs/decisoes/`.
- Toda mudanca de API publica atualiza `docs/03-API-PUBLICA-DESEJADA.md`.
- Toda mudanca de configuracao atualiza `docs/04-CONFIGURACAO-E-VAULT.md`.
- Ao concluir ou interromper trabalho, atualize `HANDOFF.md` com estado, testes, riscos e o
  proximo passo exato.
- Marque itens no `ROADMAP.md` somente quando seus criterios de aceite estiverem atendidos.

## Compatibilidade

O LuftBase e a plataforma padrao para o ecossistema Luft. O Luft-Workspace atua como
consumidor de referencia dos novos contratos.

