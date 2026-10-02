# Autorizacao Hierarquica e RBAC

## Formato Canonico das Chaves

Todas as chaves do LuftBase e das aplicacoes consumidoras seguem rigorosamente a estrutura:

`MODULO.RECURSO.ACAO`

Exemplos:
- `PLATAFORMA.SISTEMA.ADMINISTRAR`
- `PLATAFORMA.SISTEMA.ACESSAR`
- `INICIO.PAINEL.VISUALIZAR`
- `CONFIGURACOES.SISTEMAS.EDITAR`
- `SEGURANCA.PERMISSOES.CONCEDER`
- `OBSERVABILIDADE.AUDITORIA.VISUALIZAR`
- `CONTEUDO.COMUNICADOS.PUBLICAR`

O enum `PermissaoLuftBase` exporta as constantes padrao da plataforma, e `AcaoPermissao` lista as 28 acoes corporativas autorizadas.

## Arvore Hierarquica e Modulos

- Cada sistema (`tb_sistema`) organiza suas funcionalidades em modulos (`tb_modulo`).
- As permissoes (`tb_permissao`) vinculam-se a um modulo e podem possuir um no pai (`id_permissao_pai`) pertencente ao mesmo sistema.
- Conceder acesso a um no pai (por exemplo `SEGURANCA.MODULO.GERENCIAR` ou `PLATAFORMA.SISTEMA.ADMINISTRAR`) transmite a permissao para todos os nos descendentes na subarvore.
- A resolucao e calculada no PostgreSQL por uma **CTE recursiva** de alta performance limitada a 32 niveis, evitando loops e consultando unicamente os ancestrais das chaves requisitadas.

## Regras de Precedencia e Politica Fail-Closed

A decisao sobre cada permissao solicitada segue a seguinte ordem de avaliacao:

1. **Negar por padrao**: Permissao inexistente ou sem qualquer regra de concessao resulta em negacao.
2. **Permissao inativa**: Permissao com `ativo = false` resulta em negacao imediata.
3. **Ancestral inativo**: Qualquer ancestral na cadeia com `ativo = false` nega toda a subarvore.
4. **Precedencia do Usuario**: Regra direta vinculada ao usuario prevalece sobre qualquer regra de grupo.
5. **Menor distancia**: Dentro da mesma origem (usuario ou grupo), a regra mais proxima do no solicitado prevalece (regra direta na chave vence regra do pai).
6. **Heranca mestre**: Concessao no ancestral (`conceder = true`) e herdada por filhos e netos na ausencia de regra mais especifica.
7. **Bloqueio explicito**: Um filho pode receber `conceder = false` diretamente, bloqueando o acesso sem revogar a concessao do pai.
8. **Restauracao da heranca**: Remover o vinculo explicito faz a permissao voltar a herdar a decisao da arvore.
9. **Precedencia do escopo**: Chave cadastrada no sistema atual prevalece sobre a chave homonima cadastrada no escopo global (sistema 0).
10. **Protecao de ciclos**: Ciclos ou profundidade >= 32 resultam em negacao.
11. **Sistema 0**: Identifica o Hub Central e catalogo global, mas nunca constitui bypass automatico de autorizacao.

## Decorators e Jinja

```python
from luftbase import PermissaoLuftBase, exigir_permissao

@bp.get("/sistemas")
@exigir_permissao(PermissaoLuftBase.SISTEMAS_VISUALIZAR)
def listar_sistemas():
    ...
```

Nos templates Jinja:
```jinja2
{% if tem_permissao("CONFIGURACOES.SISTEMAS.CRIAR") %}
    <button class="btn btn-primary">Novo Sistema</button>
{% endif %}
```

Para multiplas chaves no menu ou cabeçalho, prefira `consultar_permissoes(chaves)` que avalia o lote em uma unica viagem ao cache ou PostgreSQL.

## Como uma Aplicacao Adiciona Novas Permissoes

1. A aplicacao define seus modulos e permissoes associados ao seu `LUFT_SISTEMA_ID` via script de seed ou pelo Gerenciador Web de Seguranca (`/seguranca/gerenciador`).
2. As chaves devem respeitar o regex `^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*){1,}$` e conter exatamente tres segmentos.
3. A acao final deve constar no enum `AcaoPermissao`.
4. As rotas devem ser decoradas com `@exigir_permissao("MEU_MODULO.RECURSO.ACAO")`.

## Caches e Invalidacao

- Camada 1: Cache por requisicao no contexto Flask (`g`), descartado ao final do request.
- Camada 2: Triggers em `tb_modulo`, `tb_permissao`, `tb_permissaogrupo` e `tb_permissaousuario` incrementam `core.tb_revisaocache` a cada mutacao. O cache distribuido Redis (quando ativo) descarta entradas de revisoes obsoletas.
- Quando Redis nao esta configurado (desenvolvimento ou piloto), o PostgreSQL Core responde diretamente as consultas com resolucao de CTE em poucos milissegundos.

## Migracoes

- **Nunca** executar migrações durante o startup do servidor web (`Wsgi.py` ou `app.run`).
- Para aplicar alteracoes estruturais e atualizar o catalogo de forma segura:
  ```powershell
  luftbase bootstrap --atualizar --ambiente desenvolvimento --banco luft_web
  ```
