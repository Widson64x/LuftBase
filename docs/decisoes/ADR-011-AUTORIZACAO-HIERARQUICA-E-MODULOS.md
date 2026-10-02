# ADR-011 — Autorização Hierárquica, Catálogo de Módulos e Estratégia de Sessões

Status: aceito em 2026-09-22.

## Contexto

O modelo de autorização do ecossistema Luft dependia de categorias informais, chaves dispersas sem padrão estrito e campos legados como `id_permissao_base` em `core.tb_sistema`. Esse acoplamento impedia a delegação estruturada de permissões e a composição em cascata (onde conceder acesso administrativo a um módulo ou recurso concede automaticamente ações filhas, a menos que haja bloqueio explícito).

Além disso, era necessário consolidar a estratégia de sessões corporativas e cache entre PostgreSQL e Redis, garantindo que o sistema piloto opere com alta confiabilidade mesmo sem Redis local.

## Decisões

### 1. Formato Canônico das Chaves
Todas as novas permissões corporativas adotam obrigatoriamente a estrutura com exatamente três segmentos em caixa alta:

`MODULO.RECURSO.ACAO`

Exemplos:
- `PLATAFORMA.SISTEMA.ADMINISTRAR`
- `PLATAFORMA.SISTEMA.ACESSAR`
- `INICIO.PAINEL.VISUALIZAR`
- `CONFIGURACOES.SISTEMAS.EDITAR`
- `SEGURANCA.PERMISSOES.CONCEDER`
- `OBSERVABILIDADE.AUDITORIA.VISUALIZAR`
- `CONTEUDO.COMUNICADOS.PUBLICAR`

### 2. Módulos Funcionais e Árvore de Permissões
- A tabela `core.tb_modulo` organiza funcionalmente os recursos pertencentes a cada sistema (`id_sistema`).
- A tabela `core.tb_permissao` introduz `id_modulo`, `id_permissao_pai`, `recurso`, `acao`, `sensivel` e `eh_acesso_sistema`.
- A herança é modelada via autorreferência `id_permissao_pai -> id_permissao` vinculada ao mesmo `id_sistema`.
- O catálogo inicial do Workspace provisiona 9 módulos padrão e 49 permissões canônicas em ordem topológica livre de ciclos.

### 3. Ações Canônicas
As únicas ações aceitas no catálogo corporativo são definidas em `AcaoPermissao`:
`ACESSAR`, `ADMINISTRAR`, `APROVAR`, `ARQUIVAR`, `ATIVAR`, `BAIXAR`, `CANCELAR`, `CONCEDER`, `CONFIGURAR`, `CRIAR`, `DESATIVAR`, `EDITAR`, `ENVIAR`, `EXECUTAR`, `EXCLUIR`, `EXPORTAR`, `GERENCIAR`, `IGNORAR`, `IMPORTAR`, `IMPRIMIR`, `LISTAR`, `PROCESSAR`, `PUBLICAR`, `REJEITAR`, `REPROCESSAR`, `REVOGAR`, `SINCRONIZAR`, `VISUALIZAR`.

### 4. Regras de Precedência e Resolução (Fail-Closed)
A avaliação hierárquica por CTE recursiva segue estritamente as regras:
1. **Negar por padrão**: ausência de regra ou erro resulta em negação.
2. **Permissão inativa nega**: se a permissão solicitada estiver com `ativo = false`, nega.
3. **Ancestral inativo nega**: se qualquer nó pai/ancestral estiver inativo, nega toda a subárvore.
4. **Usuário sobrepõe Grupo**: regras diretas para o usuário prevalecem sobre regras do grupo, independente da distância na árvore.
5. **Menor distância vence**: dentro da mesma origem (usuário ou grupo), a regra mais próxima do nó consultado prevalece (distância 0 vence distância 1).
6. **Herança mestre**: uma concessão no pai (`conceder = true`) é herdada automaticamente por filhos e netos.
7. **Bloqueio explícito**: um nó filho pode receber `conceder = false`, bloqueando o acesso sem alterar o pai.
8. **Restauração da herança**: a remoção da regra explícita faz o nó voltar a herdar da árvore.
9. **Escopo do sistema**: chave definida no sistema atual prevalece sobre chave homônima no escopo global (sistema 0).
10. **Proteção contra ciclos**: profundidade máxima de 32 níveis; excesso ou ciclo resulta em negação segura.
11. **Sistema 0**: representa o Hub Central e o escopo global de catálogo, nunca constituindo bypass automático de segurança.

### 5. Decisão Arquitetural sobre Sessões e Redis
- **PostgreSQL é a fonte definitiva**: o schema `core` do PostgreSQL armazena as sessões corporativas de forma persistente e auditável.
- **Redis é opcional no piloto**: a aplicação opera em desenvolvimento e no piloto exclusivamente com o PostgreSQL como backend de sessões e autorização.
- **Redis em Produção**: recomendado para ambientes com múltiplas instâncias distribuídas para suportar revogação instantânea via pub/sub e cache de alto rendimento.
- **Namespace único corporativo**: em produção, deve-se usar um serviço Redis compartilhado por ambiente com separação por chave/prefixo (`luft:{ambiente}:...`), e não instâncias isoladas por aplicação.
- **SQLite proibido em produção**: nunca utilizar SQLite como fallback quando o PostgreSQL Core estiver acessível.

### 6. Migrações e Operações de Banco
- As migrações Alembic **nunca** rodam durante a inicialização web (`Wsgi.py` ou Flask startup).
- Atualizações de estrutura e catálogo em produção ou desenvolvimento utilizam o comando controlado:
  `luftbase bootstrap --atualizar`
- Esse comando valida o banco conectado com `current_database()`, exige confirmação explícita no formato `ATUALIZAR-{AMBIENTE}-{BANCO}`, não toca no Vault, não altera senhas e aplica migrações e sincronização de catálogo de forma estritamente aditiva.

## Consequências

O controle de acesso torna-se declarativo, previsível, auditável e granular. As aplicações filhas herdam os módulos e permissões da plataforma LuftBase e podem estender seus próprios módulos no seu respectivo `id_sistema`. O piloto no Workspace simplifica a gestão de grupos e usuários e desacopla a aplicação de infraestrutura de cache adicional.
