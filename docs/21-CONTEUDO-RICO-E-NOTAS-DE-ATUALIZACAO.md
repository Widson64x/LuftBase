# Conteudo rico: comunicados e notas de atualizacao

O corpo de um comunicado ou de uma nota de atualizacao aceita **markdown seguro** (titulos, listas, imagens, destaques e
cards). Este documento explica o formato, as garantias de seguranca e como publicar uma nota global (o caso do lancamento do
LuftBase). O fluxo de criacao, publicacao e notificacao esta no [doc 13](13-NOTIFICACOES-E-PUBLICACOES.md).

Codigo: `conteudo/markdown_seguro.py` (renderizador), `web/publicacoes.py` (rota de leitura),
`interface/static/css/publicacoes.css` (aparencia), `conteudo/changelog_plataforma.py` (nota de lancamento).

## Sintaxe suportada

```text
# Titulo      ## Subtitulo      ### Terceiro nivel     (viram h2, h3 e h4: o h1 e o titulo da publicacao)
Paragrafo com **negrito**, *italico*, `codigo` e [link](https://exemplo.com).
- item de lista        1. item numerado        > citacao        ---  (linha)
![texto alternativo](https://exemplo.com/imagem.png)
![banner](luftbase:img/changelog/banner.png)
```

Blocos especiais:

```text
:::sucesso
Texto do destaque. Tipos: info, sucesso, alerta, perigo.
:::

:::cards
### Titulo do card
Texto do card
### Outro card
Texto
:::
```

## Seguranca (por que e seguro aceitar texto de um administrador)

- **Todo texto e escapado antes de virar HTML**; so as construcoes acima geram marcacao. `<script>`, atributos e HTML cru
  aparecem como texto.
- **Links**: so `http://` e `https://` (abrem em nova aba com `noopener noreferrer`). `javascript:` nao vira link.
- **Imagens**: so `https://...` ou `luftbase:caminho` (arquivos estaticos do proprio LuftBase, sem `..` e so com caracteres
  de caminho). `http://`, `javascript:` e outros esquemas viram texto inocuo.
- Os marcadores internos usados na conversao nao podem ser forjados por quem digita (o caractere nulo e removido).

Esses pontos tem testes (`tests/test_changelog_plataforma.py`).

## Imagens do LuftBase (`luftbase:`)

`luftbase:img/changelog/banner.png` aponta para `interface/static/img/changelog/banner.png` do pacote, resolvido pelo
prefixo da aplicacao (`url_for('luftbase.static', ...)`). Para a nota de lancamento, as imagens sao geradas por
`tools/gerar_imagens_changelog.py` (Chrome sem interface), que desenha ilustracoes e **maquetes de tela com dados ficticios**.

> **Cuidado ao remover imagens**: uma nota ja publicada no banco guarda o texto antigo. Apagar uma imagem citada por ela deixa
> um quadrado quebrado na tela. Por isso um teste confere que toda imagem citada no texto atual existe, e o script de
> publicacao **corrige o texto** da nota ja publicada (veja abaixo) antes de qualquer remocao.

## Nota de lancamento global

`conteudo/changelog_plataforma.py` guarda o texto ("Uma base nova para o Workspace, o ConnectAir e o Integrador") e a funcao
`publicar_changelog_plataforma(servico, versao=..., notificar=True, publicar=True)`:

- cria a nota como **atualizacao global** (sistema 0, audiencia geral), prioridade alta, fixada, com notificacao;
- e **idempotente**: se a nota ja existe publicada (mesmo com o titulo de uma versao anterior do texto), corrige titulo, resumo
  e texto **sem notificar de novo** (`ServicoPublicacoes.corrigir_texto`);
- se houver copias duplicadas, mantem a mais nova e **arquiva** as outras;
- com `publicar=False` deixa so o rascunho.

O Workspace expoe isso em `scripts/PublicarChangelogPlataforma.py`:

```text
pip install -r requirements.txt                              # garanta o LuftBase atual (o script mostra a versao)
python scripts/PublicarChangelogPlataforma.py                # simula (nao grava)
python scripts/PublicarChangelogPlataforma.py --executar     # cria/atualiza, publica e notifica
python scripts/PublicarChangelogPlataforma.py --executar --rascunho --versao 2.0 --sem-notificar
```

Rode primeiro em **homologacao**; depois, com o mesmo `.env` de producao, la.

## Escrevendo uma nota para o usuario final

- Fale do que a pessoa **ve e faz** (login unico, perfil, avisos), nao de infraestrutura (cofre, auditoria, servicos).
- Nao generalize: cite so os sistemas realmente migrados; os de outras tecnologias seguem como estao.
- Maquetes devem ser avisadas como ilustracao com dados ficticios.
