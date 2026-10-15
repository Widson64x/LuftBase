# Padroes de codigo e contribuicao

Regras para quem escreve codigo no **LuftBase**. (Quem escreve um *sistema* que usa o LuftBase segue o [guia da aplicacao satelite](19-GUIA-DA-APLICACAO-SATELITE.md)
e o [ADR-017](decisoes/ADR-017-PADRAO-DE-PROJETO-DAS-APLICACOES.md).) As regras inviolaveis ficam no [AGENTS.md](../AGENTS.md); aqui estao explicadas, com o dia a dia
de uma contribuicao.

## Linguagem

A API publica, os nomes internos, as docstrings e as mensagens sao em **portugues**. Identificadores Python **nao usam acentos**. Nomes
oficiais de tecnologias (Flask, Vault, PostgreSQL) nao sao traduzidos. **Nao mantenha aliases em ingles** na API nova.

## Estilo

- PEP 8 e formatacao **Ruff**; PEP 257 nas APIs publicas; **type hints obrigatorios**;
- funcoes pequenas, com **uma** responsabilidade observavel e um nome coerente com ela;
- objetos imutaveis para configuracao (`dataclass(frozen=True, slots=True)`);
- **protocolos** nas fronteiras externas e composicao em vez de heranca vazia;
- excecoes de dominio em vez de `Exception` generica; **nenhum `except: pass`** em caminho importante;
- **nenhum `**kwargs`** escondendo uma API publica;
- erros de configuracao **falham cedo** e dizem qual campo esta invalido.

## Comentarios

Comentarios explicam **por que** (uma decisao, uma invariante, um risco). Codigo autoexplicativo nao recebe narracao linha a linha.

## O que nunca fazer (regras do projeto)

| Nao faca | Por que |
|---|---|
| alterar dados ou estrutura do SQL Server | ele e fonte **somente leitura** do diretorio |
| usar usuario administrativo de banco no runtime | o runtime usa so a role do sistema |
| rodar migracao na inicializacao | migracao e comando explicito |
| fallback silencioso do PostgreSQL para o SQL Server | esconde falha e mistura fontes |
| ler variavel de ambiente fora de `luftbase.configuracao` | configuracao dispersa e impossivel de auditar |
| singleton global dependente de uma aplicacao Flask | quebra testes e varias aplicacoes no mesmo processo |
| registrar listener na classe global `sqlalchemy.orm.Session` | afeta todo o processo |
| usar uma sessao SQLAlchemy para dois bancos | cada banco tem a sua sessao |
| expor models sistemicos na API de inicializacao | o `core` pertence ao LuftBase |
| gravar token, senha, cookie ou cabecalho de autorizacao em log | vazamento |
| criar flag para desligar tokens, tema, CSS base, acessibilidade ou JS essencial | o perfil web obrigatorio nao e opcional |

## Portao de qualidade

Antes de concluir qualquer mudanca:

```powershell
python -m ruff check src tests
python -m ruff format --check src tests
python -m mypy src
python -m pytest
python -m build
```

- `ruff check` e `pytest` precisam passar; a CI roda ambos em **Windows e Linux** (Python 3.11 e 3.12) e confere que a tag e igual a versao
  ([doc 20](20-OPERACAO-E-DEPLOY.md)).
- `mypy` e `ruff format --check` ainda acusam **pendencias antigas** em arquivos que ja existiam; arquivos novos ou alterados devem nascer
  formatados e sem erro de tipo. Formate **so os arquivos que voce tocou** (`ruff format <arquivo>`): rodar o formatador no projeto inteiro
  gera um diff enorme e mistura mudancas.
- Nunca afirme que uma validacao passou sem rodar.

## Testes

- Cada **correcao de defeito** recebe um teste de regressao.
- Integracoes externas (Vault, LDAP, PostgreSQL, WSL) sao testadas por **contratos e adaptadores falsos**, nao por servidores reais: veja os
  testes de `cli/` como exemplo (fakes de Vault e de cursor, SQLite em memoria para o core).
- Modulos criticos (seguranca, sessao, Vault, banco) exigem cobertura dos **caminhos de erro**, nao so do fluxo feliz.
- O que so da para provar contra o servico real (PostgreSQL, Vault) vai para o **ensaio em homologacao** e e dito como tal no HANDOFF.

## Receitas

### Adicionar um comando de CLI

1. Crie (ou edite) o modulo em `src/luftbase/cli/` e registre o grupo em `cli/__init__.py` (os dois lugares: `cli.add_command` e `registrar_comandos`).
2. Peca segredos **no terminal, sem eco**; nunca por argumento. Mostre o destino antes de gravar e peca confirmacao (`--sim` para pular).
3. Converta falhas esperadas em `click.ClickException` com uma mensagem que diga o que fazer (sem traceback).
4. Teste com `CliRunner` e fakes; atualize [`test_cli_banco.py`](../tests/test_cli_banco.py) se o grupo `banco` ganhou comando.
5. Documente em [23-REFERENCIA-DA-CLI.md](23-REFERENCIA-DA-CLI.md).

### Adicionar uma migracao do `core`

1. Arquivo em `src/luftbase/migracoes/versoes/AAAAMMDD_NNNN_descricao.py`, com `revision` e `down_revision` encadeados.
2. **Aditiva**: criar tabela ou coluna. Nada de `drop_*`, `rename_*` ou `alter_column` ([`test_migracoes_aditivas.py`](../tests/test_migracoes_aditivas.py)
   barra isso nas migracoes novas). Se for preciso remover algo, em duas versoes.
3. Prefira DDL **repetivel** (`IF NOT EXISTS`) quando o mesmo ajuste puder ser aplicado antes por script SQL (veja `tools/sql/`).
4. Atualize o modelo em `persistencia/core/`, o teste de historico ([`test_migracoes.py`](../tests/test_migracoes.py)) e, se houver `CHECK` novo, o teste de nomes
   de constraints.
5. Se o banco de homologacao/producao precisar da mudanca antes do deploy, escreva o script em `tools/sql/` (carimbando a revisao so se o core
   estiver na anterior) e registre a ordem no [doc 25](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md).

### Publicar uma versao

1. Rode o portao de qualidade.
2. Suba a versao em `pyproject.toml` **e** `src/luftbase/_versao.py` (iguais), no padrao `0.1.0aNN`.
3. Registre em `CHANGELOG.md` com o titulo **exatamente igual** a versao e a data real.
4. Atualize a documentacao tocada (tabela abaixo), commite, crie a tag `v<versao>` e envie. Passo a passo e promocao em [doc 20](20-OPERACAO-E-DEPLOY.md).

## Documentacao: o que atualizar quando

| Mudou... | Atualize |
|---|---|
| API publica (`luftbase.__all__`) | [03-API-PUBLICA-DESEJADA.md](03-API-PUBLICA-DESEJADA.md) |
| comando de CLI | [23-REFERENCIA-DA-CLI.md](23-REFERENCIA-DA-CLI.md) |
| variavel de ambiente ou configuracao | [18](18-VARIAVEIS-DE-AMBIENTE.md) e [04](04-CONFIGURACAO-E-VAULT.md) |
| tabela, coluna ou schema | [05](05-BANCO-E-SCHEMAS.md) e [09](09-PERSISTENCIA-E-MIGRACOES.md) |
| catalogo de sistemas, categorias | [24](24-SISTEMAS-E-CATALOGO.md) |
| decisao arquitetural relevante | um novo ADR em [`decisoes/`](decisoes/) |
| qualquer entrega | `CHANGELOG.md` (e `HANDOFF.md` ao encerrar ou interromper) |
| item do roadmap concluido | `ROADMAP.md`, **so** quando os criterios de aceite foram atendidos |

Regras de escrita: descreva o que o codigo **faz** (conferido), nao o que se lembra; comportamento que surpreende ou lacuna conhecida vai **dito**; contagens
so se verificadas na hora; links relativos entre documentos; documentos do LuftBase em ASCII (sem acentos), como os existentes.
