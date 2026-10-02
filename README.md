# LuftBase

Plataforma corporativa para as aplicacoes Python da Luft.

O LuftBase esta sendo construido para que uma aplicacao receba, com uma unica inicializacao,
os padroes compartilhados de configuracao, Vault, bancos, identidade, sessao, autorizacao,
auditoria, observabilidade e interface. Os projetos consumidores devem concentrar-se em suas
regras de negocio.

## Estado atual

O projeto esta em alpha (`0.1.0a4`) e os marcos M00 a M09 estao concluidos: fundacao,
configuracao, Vault, conexoes, persistencia ORM, migrations, identidade, sessao,
autorizacao, auditoria, observabilidade, conteudo, design system, CLI/scaffolding
e preparacao do piloto M10 do Luft-Workspace. O unico bootstrap de identidade no `.env`
e `LUFT_SISTEMA_ID`; o mesmo identificador numerico governa Vault, banco,
autorizacao e conteudo. O identificador textual fica apenas no segredo do sistema.

Consulte:

- [Roadmap](ROADMAP.md)
- [Handoff](HANDOFF.md)
- [Documentacao](docs/README.md)
- [Instrucoes para contribuidores e agentes](AGENTS.md)

## API pretendida

```python
from flask import Flask
from luftbase import PlataformaLuft

plataforma = PlataformaLuft()


def criar_app() -> Flask:
    app = Flask(__name__)
    plataforma.inicializar(app)
    return app
```

A plataforma le o `.env` e o ambiente do processo uma unica vez durante a inicializacao.
Valores definidos diretamente em `app.config` possuem precedencia e facilitam testes.
Vault e bancos so sao acessados quando `inicializar()` e chamado; importar `luftbase` nao
realiza rede. Depois da inicializacao, as fronteiras ficam disponiveis no estado:

```python
from luftbase import obter_luftbase


def executar_servico() -> None:
    bancos = obter_luftbase().bancos

    with bancos.diretorio.leitura() as sessao:
        sessao.execute(...)  # SQL Server corporativo, sempre sem commit.

    with bancos.aplicacao.unidade_trabalho() as sessao:
        sessao.add(...)  # Commit no sucesso e rollback no erro.
```

`GET /_luftbase/saude` informa a disponibilidade de cada fronteira e do Redis sem publicar
URL, usuario, senha ou mensagem interna do driver.

Nao farao parte da inicializacao publica:

```text
user_model
group_model
permissao_model
permissao_grupo_model
permissao_usuario_model
log_acesso_model
gerenciador_usuario
injetar_tema
injetar_global
injetar_animacoes
injetar_js
```

## Desenvolvimento local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```
