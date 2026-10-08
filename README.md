# LuftBase

Plataforma corporativa para os sistemas web em Python da Luft (Flask + PostgreSQL + Vault).

O LuftBase entrega, com **uma unica inicializacao**, tudo o que um sistema da Luft precisa antes de escrever a primeira regra
de negocio: configuracao e segredos (Vault), conexoes com os bancos, login corporativo (LDAP), sessao compartilhada entre
sistemas (SSO), permissoes, auditoria, notificacoes e comunicados, temas, perfil do usuario, e-mail, servidor de producao e um
Painel de Controle para a equipe de TI. As aplicacoes consumidoras cuidam so do que e delas.

- Repositorio: <https://github.com/Widson64x/LuftBase> (publico)
- Versao atual: **0.1.0a98** (alpha) — veja o [CHANGELOG](CHANGELOG.md)
- Python 3.11 ou superior; mais de 740 testes automatizados

## Quem usa

| Sistema | Papel | Repositorio |
|---|---|---|
| **Luft-Workspace** (sistema 0) | portal central, Painel de Controle de todo o ecossistema | [Luft-Workspace](https://github.com/Widson64x/Luft-Workspace) |
| **Luft-ConnectAir** | planejamento aereo de cargas | [Luft-ConnectAir](https://github.com/Widson64x/Luft-ConnectAir) |
| **Luft-Integrador** | Ecobox, Reintegracao WMS e FASTLINE | [Luft-Integrador](https://github.com/Widson64x/Luft-Integrador) |

O **Luft-Control** sera o proximo a migrar. Os demais sistemas da Luft, construidos com outras tecnologias, nao fazem parte
deste padrao.

## O que a plataforma entrega

| Area | O que faz | Documento |
|---|---|---|
| Configuracao e Vault | `.env` minimo; segredos, bancos e e-mail vem do Vault por ambiente | [04](docs/04-CONFIGURACAO-E-VAULT.md), [18](docs/18-VARIAVEIS-DE-AMBIENTE.md) |
| Bancos | diretorio (SQL Server, so leitura), core e schema da aplicacao (PostgreSQL) | [05](docs/05-BANCO-E-SCHEMAS.md), [09](docs/09-PERSISTENCIA-E-MIGRACOES.md) |
| Identidade e sessao | LDAP, sessao unica no core, cookie compartilhado, logout global | [10](docs/10-IDENTIDADE-E-SESSAO.md) |
| Autorizacao | permissoes `MODULO.RECURSO.ACAO`, hierarquia, cache, fail-closed | [11](docs/11-AUTORIZACAO.md) |
| Auditoria | acesso, evento e antes/depois; painel analitico, "Ao vivo", controle de sessoes | [12](docs/12-AUDITORIA-E-OBSERVABILIDADE.md), [15](docs/15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md) |
| Comunicacao | notificacoes, comunicados, notas de atualizacao com conteudo rico | [13](docs/13-NOTIFICACOES-E-PUBLICACOES.md), [21](docs/21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md) |
| Interface | layout, temas claro/escuro, design system, perfil do usuario | [07](docs/07-DESIGN-SYSTEM-E-TEMAS.md), [16](docs/16-PERFIL-DO-USUARIO.md) |
| Painel de Controle | seguranca, sistemas, variaveis, servicos, integracoes, comunicacao | [14](docs/14-PAINEL-DE-CONTROLE.md) |
| Servidor | Waitress, prefixo de URL, IP real atras do nginx, fuso de Brasilia | [17](docs/17-SERVIDOR-REDE-E-FUSO.md) |
| Operacao | ambientes, deploy Windows/Linux, versionamento, solucao de problemas | [20](docs/20-OPERACAO-E-DEPLOY.md) |

## Como uma aplicacao usa o LuftBase

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
- Guia completo para criar uma aplicacao nova: [docs/19](docs/19-GUIA-DA-APLICACAO-SATELITE.md).

## Comece por aqui

1. [Indice da documentacao](docs/README.md)
2. [Roadmap](ROADMAP.md): marcos e o que falta
3. [CHANGELOG](CHANGELOG.md): o que mudou em cada versao
4. [Handoff](HANDOFF.md): estado operacional para continuidade
5. [AGENTS.md](AGENTS.md): regras para quem contribui (pessoas e agentes)

## Desenvolvimento local

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest        # a suite inteira e o portao de qualquer publicacao
```

Publicar uma versao: suba a versao em `pyproject.toml` e `src/luftbase/_versao.py`, registre no `CHANGELOG.md`, rode a suite,
crie a tag `v<versao>` e envie (`git push origin main v<versao>`). Cada aplicacao passa a usar a nova versao trocando o pin em
seu `requirements.txt` ([doc 20](docs/20-OPERACAO-E-DEPLOY.md)).

## Linha de comando

`luftbase` (ou `flask`) traz: `banco` (versao, validar, atualizar, historico, pendencias), `vault` (caminhos, verificar,
provisionamento PostgreSQL), `catalogo sincronizar`, `diagnostico` (configuracao, saude), `email testar`, `estrutura`
(verificar, criar), `tema` (listar, validar), `projeto` (criar, deploy), `servir` e `bootstrap`. Use `--help` em cada um.

## Licenca e contribuicao

Este repositorio **ainda nao tem arquivo de licenca**: defina a licenca (os demais repositorios do ecossistema trazem um
`LICENSE`) antes de divulgar ou reutilizar fora da Luft. Antes de contribuir, leia o [AGENTS.md](AGENTS.md) e o
[padrao de codigo](docs/06-PADROES-DE-CODIGO.md).
