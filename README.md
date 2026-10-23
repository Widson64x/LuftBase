# LuftBase

Plataforma corporativa para os sistemas web em Python da Luft (Flask + PostgreSQL + Vault).

O LuftBase entrega, com **uma unica inicializacao**, tudo o que um sistema da Luft precisa antes de escrever a primeira regra de
negocio: configuracao e segredos (Vault), conexoes com os bancos, login corporativo (LDAP), sessao compartilhada entre sistemas (SSO),
permissoes, auditoria, notificacoes e comunicados, temas, perfil do usuario, e-mail, servidor de producao e um Painel de Controle para a
equipe de TI. As aplicacoes cuidam so do que e delas.

- Repositorio: <https://github.com/Widson64x/LuftBase> (publico)
- Versao atual: **0.1.0a129** (alpha), com mais de 1000 testes automatizados; o que mudou em cada versao esta no [CHANGELOG](CHANGELOG.md)
- Python 3.11 ou superior

## Em 5 minutos

**Quero criar um sistema novo.** Um comando cria a pasta no padrao Luft **e** registra o sistema no banco e no Vault do ambiente de
desenvolvimento:

```powershell
python -m venv .venv ; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"                                   # instala o LuftBase (nesta pasta)
python -m luftbase projeto novo Luft-Faturas --destino C:\Projetos\LUFT\Python\Luft-Faturas
```

O comando pede o token do Vault e a credencial administrativa do banco (sem eco; nunca gravados), cria o schema, a role e o segredo, e
escreve o `.env`. Depois e completar os tokens no `.env` e rodar `python App.py`. O caminho inteiro, ate producao, esta no
**[Guia rapido do desenvolvedor](docs/22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md)**.

**Quero entender como uma aplicacao usa o LuftBase:**

```python
# App/__init__.py (resumo; o padrao completo esta no ADR-017)
from flask import Flask
from luftbase import PlataformaLuft
from App.Catalogo import CATALOGO, PARAMETROS
from App.Routes import RegistrarRotas


def CriarApp():
    app = Flask(__name__)
    PlataformaLuft(catalogo=CATALOGO, parametros=PARAMETROS).inicializar(app)  # le o .env e o Vault uma vez
    RegistrarRotas(app)
    return app
```

```python
# Em qualquer servico ou rota, depois de inicializado:
from luftbase import obter_luftbase, exigir_permissao

@bp.post("/algo")
@exigir_permissao("MEUSISTEMA.ALGO.EDITAR")          # 401, 403 ou 503 sem conceder em caso de falha
def algo():
    with obter_luftbase().bancos.aplicacao.unidade_trabalho() as sessao:   # commit no sucesso, rollback no erro
        ...
```

- Importar `luftbase` **nao faz rede**; Vault e bancos so sao acessados em `inicializar()`.
- O unico bootstrap de identidade no `.env` e `LUFT_SISTEMA_ID`; nome, icone e demais dados vem de `core.tb_sistema`.
- `GET /_luftbase/saude` informa a saude de cada dependencia, sem expor URL, usuario ou senha.

## Quem usa

| Sistema | Papel | Repositorio |
|---|---|---|
| **Luft-Workspace** (sistema 0) | portal central e Painel de Controle de todo o ecossistema | [Luft-Workspace](https://github.com/Widson64x/Luft-Workspace) |
| **Luft-ConnectAir** | planejamento aereo de cargas | [Luft-ConnectAir](https://github.com/Widson64x/Luft-ConnectAir) |
| **Luft-Integrador** | Ecobox, Reintegracao WMS e FASTLINE | [Luft-Integrador](https://github.com/Widson64x/Luft-Integrador) |
| **Luft-Control** | DRE, Budget e Razao | [Luft-Control](https://github.com/Widson64x/Luft-Control) |
| **Luft-Docs** | documentacao viva dos sistemas, com versoes, aprovacao e assistente de IA | [Luft-Docs](https://github.com/Widson64x/Luft-Docs) |

Ferramentas feitas com outras tecnologias (C#, executaveis, sistemas de terceiros) **nao usam** o LuftBase, mas podem aparecer no catalogo
como **sistemas externos**, com card e link ([doc 24](docs/24-SISTEMAS-E-CATALOGO.md)).

## O que a plataforma entrega

| Area | O que faz | Documento |
|---|---|---|
| Configuracao e Vault | `.env` minimo; segredos, bancos e e-mail vem do Vault por ambiente | [04](docs/04-CONFIGURACAO-E-VAULT.md), [18](docs/18-VARIAVEIS-DE-AMBIENTE.md) |
| Bancos | diretorio (SQL Server, so leitura), core e schema da aplicacao (PostgreSQL) | [05](docs/05-BANCO-E-SCHEMAS.md), [09](docs/09-PERSISTENCIA-E-MIGRACOES.md) |
| Identidade e sessao | LDAP, sessao unica no core, cookie compartilhado, logout global | [10](docs/10-IDENTIDADE-E-SESSAO.md) |
| Autorizacao | permissoes `MODULO.RECURSO.ACAO`, hierarquia, cache, fail-closed | [11](docs/11-AUTORIZACAO.md) |
| Auditoria | acesso, evento e antes/depois; painel analitico, "Ao vivo", controle de sessoes | [12](docs/12-AUDITORIA-E-OBSERVABILIDADE.md), [15](docs/15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md) |
| Comunicacao | notificacoes, comunicados, notas de atualizacao com conteudo rico | [13](docs/13-NOTIFICACOES-E-PUBLICACOES.md), [21](docs/21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md) |
| Interface | layout, temas claro/escuro, design system, seletor de icones, perfil | [07](docs/07-DESIGN-SYSTEM-E-TEMAS.md), [16](docs/16-PERFIL-DO-USUARIO.md) |
| Catalogo de sistemas | cadastro, categorias, sistemas externos | [24](docs/24-SISTEMAS-E-CATALOGO.md) |
| Painel de Controle | seguranca, sistemas, variaveis, servicos, integracoes, comunicacao | [14](docs/14-PAINEL-DE-CONTROLE.md) |
| Ferramentas do desenvolvedor | CLI, projeto novo, banco local, comparacao de estrutura | [22](docs/22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md), [23](docs/23-REFERENCIA-DA-CLI.md), [25](docs/25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md) |
| Servidor | Waitress, prefixo de URL, IP real atras do nginx, fuso de Brasilia | [17](docs/17-SERVIDOR-REDE-E-FUSO.md) |
| Operacao | ambientes, deploy Windows/Linux, versionamento, solucao de problemas | [20](docs/20-OPERACAO-E-DEPLOY.md), [26](docs/26-SOLUCAO-DE-PROBLEMAS.md) |

## Por onde comecar na documentacao

| Voce e... | Leia |
|---|---|
| quem vai **criar ou manter um sistema** | [22 Guia rapido](docs/22-GUIA-RAPIDO-DO-DESENVOLVEDOR.md), [19 Aplicacao satelite](docs/19-GUIA-DA-APLICACAO-SATELITE.md), [23 CLI](docs/23-REFERENCIA-DA-CLI.md) |
| quem **administra** acessos e sistemas | [14 Painel de Controle](docs/14-PAINEL-DE-CONTROLE.md), [11 Autorizacao](docs/11-AUTORIZACAO.md), [24 Catalogo](docs/24-SISTEMAS-E-CATALOGO.md) |
| quem cuida do **servidor e do deploy** | [20 Operacao](docs/20-OPERACAO-E-DEPLOY.md), [17 Servidor](docs/17-SERVIDOR-REDE-E-FUSO.md), [26 Problemas](docs/26-SOLUCAO-DE-PROBLEMAS.md) |
| quem quer o **panorama** | [01 Visao](docs/01-VISAO-DO-PRODUTO.md), [02 Arquitetura](docs/02-ARQUITETURA.md), [27 Glossario](docs/27-GLOSSARIO.md) |
| quem vai **contribuir com o LuftBase** | [AGENTS.md](AGENTS.md), [06 Padroes e contribuicao](docs/06-PADROES-DE-CODIGO.md) |

O [indice completo](docs/README.md) lista os 28 documentos e as 18 decisoes de arquitetura. Estado do projeto: [Roadmap](ROADMAP.md) (marcos e o que
falta), [CHANGELOG](CHANGELOG.md) e [Handoff](HANDOFF.md) (continuidade entre pessoas e agentes).

## Linha de comando

```powershell
python -m luftbase --help        # ou apenas: luftbase --help
```

| Grupo | Para que serve |
|---|---|
| `projeto` | `novo` (pasta + sistema + schema + Vault + `.env`), `criar` (so arquivos), `deploy` (artefatos nginx e NSSM) |
| `sistema` | `externo`: cadastra ferramenta que nao usa o LuftBase |
| `banco` | `espelhar`, `comparar`, `atualizar-core`; e, na aplicacao: `versao`, `pendencias`, `validar`, `atualizar`, `historico`, `retencao`, `tamanho-logs` |
| `vault` | `caminhos`, `verificar` e `postgresql ...` (auditar, provisionar, clonar ambiente, reprovisionar sistema) |
| `catalogo` | `sincronizar` modulos e permissoes de uma aplicacao |
| `diagnostico` | `configuracao` e `saude`, sem revelar segredos |
| `alertas`, `email`, `estrutura`, `tema` | alertas ao desenvolvedor, teste de e-mail, verificacao de tabelas, validacao de temas |
| `servir`, `bootstrap` | servidor Waitress e provisionamento inicial de ambiente |

Todos os comandos, opcoes e cuidados: **[referencia da CLI](docs/23-REFERENCIA-DA-CLI.md)**.

## Desenvolvimento do LuftBase

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest        # a suite inteira e o portao de qualquer publicacao
```

Portao de qualidade completo (ruff, mypy, pytest, build) e receitas para adicionar comando, migracao e versao:
[doc 06](docs/06-PADROES-DE-CODIGO.md). Publicar uma versao: suba a versao em `pyproject.toml` e `src/luftbase/_versao.py`, registre no
`CHANGELOG.md`, rode a suite, crie a tag `v<versao>` e envie (`git push origin main v<versao>`). Cada aplicacao passa a usar a nova versao
trocando o pin em seu `requirements.txt` ([doc 20](docs/20-OPERACAO-E-DEPLOY.md)).

## Licenca e contribuicao

Este repositorio **ainda nao tem arquivo de licenca**: defina a licenca (os demais repositorios do ecossistema trazem um `LICENSE`)
antes de divulgar ou reutilizar fora da Luft. Antes de contribuir, leia o [AGENTS.md](AGENTS.md) e o
[padrao de codigo](docs/06-PADROES-DE-CODIGO.md).
