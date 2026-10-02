# API publica desejada

## Inicializacao

```python
from luftbase import PlataformaLuft

plataforma = PlataformaLuft()
plataforma.inicializar(app)
```

O `.env` e lido centralmente durante a inicializacao. Configuracoes fornecidas diretamente
em `app.config` possuem precedencia sobre o arquivo e sobre variaveis do processo.

## Rotas

```python
from flask import jsonify
from luftbase import PermissaoLuftBase, exigir_permissao


@bp.get("/relatorio")
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def visualizar_relatorio():
    return jsonify(itens=[])
```

O decorator ja esta disponivel. Usuario anonimo recebe 401, negacao comprovada recebe 403 e
indisponibilidade que impeca comprovar a permissao recebe 503.

Para varias chaves, consulte em lote:

```python
from flask_login import current_user
from luftbase import PermissaoLuftBase, obter_luftbase

decisoes = obter_luftbase().autorizacao.consultar(
    current_user,
    [
        PermissaoLuftBase.AUDITORIA_VISUALIZAR,
        PermissaoLuftBase.AUDITORIA_EXPORTAR,
    ],
)
```

## Servicos

```python
from luftbase import NovaNotificacao, obter_luftbase

plataforma = obter_luftbase()
plataforma.notificacoes.criar(
    NovaNotificacao(titulo="Processo concluido", mensagem="O arquivo foi processado.")
)
```

Notificacoes e publicacoes nao recebem models da aplicacao. Os contratos `NovaNotificacao`,
`NovaPublicacao`, enums e itens de nota de atualizacao sao exportados por `luftbase`. Os
servicos ficam em `obter_luftbase().notificacoes` e `obter_luftbase().publicacoes`.

Temas adicionais sao registrados antes da primeira requisicao, sem flags de injecao:

```python
from luftbase import ManifestoTema, obter_luftbase

obter_luftbase().temas.registro.registrar(
    ManifestoTema("operacoes", "Operacoes", "1.0.0", "/static/operacoes.css")
)
```

Identidade ja esta disponivel no estado atual:

```python
from luftbase import obter_luftbase
from luftbase.identidade import encerrar_sessao_global, iniciar_sessao_usuario

usuario = obter_luftbase().autenticacao.autenticar(login, senha)
if usuario is not None:
    iniciar_sessao_usuario(usuario)

# Em uma rota de logout:
encerrar_sessao_global()
```

Auditoria de dominio e correlacao tambem estao disponiveis:

```python
from luftbase import (
    SeveridadeAuditoria,
    obter_id_correlacao,
    registrar_evento_auditoria,
)

id_detalhe = registrar_evento_auditoria(
    acao="ATUALIZAR",
    recurso="BUDGET",
    id_recurso=str(budget.id),
    descricao="Budget atualizado.",
    dados_anteriores=antes,
    dados_novos=depois,
    severidade=SeveridadeAuditoria.MEDIA,
)
id_correlacao = obter_id_correlacao()
```

O retorno identifica `core.tb_logdetalhe`. Quando existem `dados_anteriores` ou
`dados_novos`, o LuftBase cria `core.tb_logs` na mesma transacao. Em contexto HTTP, o detalhe
e associado automaticamente a `core.tb_logacesso` pela correlacao e pelo sistema.

Rotas operacionais instaladas automaticamente:

- `GET /_luftbase/saude` e `GET /_luftbase/prontidao`: dependencias sanitizadas;
- `GET /_luftbase/metricas`: contadores locais de baixa cardinalidade;
- `GET /_luftbase/notificacoes` e `GET /_luftbase/publicacoes`: feeds limitados;
- `PUT /_luftbase/notificacoes/<id>/leitura` e
  `PUT /_luftbase/publicacoes/<id>/leitura`: recibos idempotentes;
- `GET /_luftbase/notificacoes/eventos` e `GET /_luftbase/publicacoes/eventos`: SSE com
  retomada por `Last-Event-ID`;
- `GET` e `PUT /_luftbase/interface/preferencia`: preferencia visual compartilhada.

## Catalogo da aplicacao

```python
from luftbase import CatalogoAplicacao, DefinicaoModulo, PermissaoAplicacao, SistemaAplicacao

CATALOGO = CatalogoAplicacao(
    sistema=SistemaAplicacao(nome="Luft-ConnectAir", descricao="...", link="/Luft-ConnectAir/"),
    modulos=(DefinicaoModulo("PLANEJAMENTO", "Planejamento", "...", "ph-globe", 10), ...),
    permissoes=(
        PermissaoAplicacao("CONNECTAIR.SISTEMA.ADMINISTRAR", "Tudo.", sensivel=True),
        PermissaoAplicacao("CONNECTAIR.SISTEMA.ACESSAR", "Acesso.",
                           pai="CONNECTAIR.SISTEMA.ADMINISTRAR", acesso_sistema=True),
        ...
    ),
)
```

```python
estado = PlataformaLuft(catalogo=CATALOGO).inicializar(app)
```

Na inicializacao o LuftBase confere o catalogo no core do `LUFT_SISTEMA_ID` e cria o que
faltar; o sistema precisa ter sido cadastrado antes pelo Workspace. A CLI continua disponivel
para sincronizar sem subir a aplicacao (e para conceder a raiz a um grupo):

```powershell
luftbase catalogo sincronizar --catalogo Catalogo:CATALOGO --grupo-administrador 6
```

Sistemas nunca sao excluidos; `ativo = false` exibe a pagina de sistema descontinuado.

Views de API usam `@exigir_ajax` (404 sem `X-Requested-With` ou JSON). Mensagens de
`flash(texto, categoria)` aparecem como toasts; prefira `enfileirar_toast` em codigo novo.

## Parametros da aplicacao

```python
from luftbase import ParametroAplicacao

PARAMETROS = (
    ParametroAplicacao(
        titulo="Indice de Prioridade",
        descricao="Preferencia de cada companhia aerea nas roteirizacoes.",
        endpoint="Parametros.gerenciarCias",
        icone="ph-bold ph-airplane-tilt",
        permissao="PARAMETROS.CIAS_AEREAS.VISUALIZAR",
    ),
)
PlataformaLuft(catalogo=CATALOGO, parametros=PARAMETROS).inicializar(app)
```

Cada item vira um cartao em Painel de Controle > Configuracoes Gerais. A aplicacao nao cria
menu nem tela-indice propria para isso; a rota apontada continua sendo da aplicacao.

## E-mail

A conta SMTP vem do Vault (`integracoes/email`); a aplicacao so informa destino e conteudo.

```python
from luftbase import Anexo, enviar_email, obter_luftbase

resultado = enviar_email(
    ["filial@luftlogistics.com"],
    "Planejamento aereo - SAO",
    template="Email/PlanejamentoFilial.html",   # estende luftbase/email/base.html
    contexto={"filial_titulo": "SAO - Sao Paulo", "ctcs": 12},
    anexos=[Anexo("Planejamento.xlsx", conteudo, "application/vnd.ms-excel")],
)
if not resultado.sucesso:
    mensagem_erro(resultado.erro)

servico = obter_luftbase().email
servico.configurado, servico.modo_teste, servico.destinos_teste
envios = [servico.preparar(destino, assunto, template=..., contexto=...) for ...]
resultados = servico.enviar_lote(envios)            # uma unica sessao SMTP
```

- `enviar`/`preparar` aceitam `template` **ou** `html`, alem de `texto`, `copia`,
  `copia_oculta`, `responder_para`, `imagens` e `nome_remetente`.
- Sem `texto`, a parte `text/plain` e gerada a partir do HTML.
- `ResultadoEnvio` traz `sucesso`, `erro`, `destinatarios`, `destinatarios_originais`,
  `redirecionado` e `recusados`, e `como_dict()` para respostas JSON.
- Falha de entrega nunca levanta excecao; `EmailNaoConfigurado` e `ErroEmail` indicam uso
  indevido ou ambiente sem o segredo.
- Todo envio e auditado como `EMAIL_ENVIADO`/`EMAIL_FALHA`.

Templates de e-mail sao descritos em `docs/07-DESIGN-SYSTEM-E-TEMAS.md`.

## Banco particular

```python
with plataforma.bancos.aplicacao.unidade_trabalho() as sessao:
    sessao.add(entidade)
```

Inicializacao, bancos, identidade, sessao, autorizacao, observabilidade, notificacoes,
publicacoes, interface, CLI e scaffolding ja estao implementados.

## CLI e scaffolding

```powershell
luftbase projeto criar luft-pedidos --nome "Luft Pedidos"
luftbase diagnostico configuracao
luftbase banco versao
luftbase banco historico
luftbase tema listar
luftbase estrutura verificar
luftbase email testar --para voce@luftlogistics.com
```

A CLI pode ser executada diretamente como `luftbase` ou pelos comandos integrados do Flask (`flask banco`, `flask diagnostico`, etc.).

Models particulares declaram sua politica sem conceder autoridade implicita ao startup:

```python
from luftbase import DefinicaoModelo, PlataformaLuft, PoliticaEstrutura


class Pedido(Base):
    __tablename__ = "tb_pedido"
    __politica_estrutura__ = PoliticaEstrutura.GERENCIAR


plataforma = PlataformaLuft(modelos=[DefinicaoModelo.de_modelo(Pedido)])
```

`VALIDAR` apenas inspeciona, `GERENCIAR` aceita criacao por CLI confirmada e
`EXTERNA_SOMENTE_LEITURA` e obrigatoria para models do SQL Server. O `Wsgi.py` nunca executa
DDL nem abre prompt interativo.

## Itens proibidos na inicializacao

- models sistemicos;
- fabrica manual de sessao do core;
- mapeador de usuario;
- flags de injecao dos assets obrigatorios;
- registro manual de auditoria, notificacoes ou publicacoes.
