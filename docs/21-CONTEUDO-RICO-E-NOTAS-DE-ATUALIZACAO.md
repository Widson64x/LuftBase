# Conteudo rico: comunicados e notas de atualizacao

O corpo de um comunicado ou de uma nota de atualizacao e escrito no **editor visual** do Painel de Controle (como um e-mail:
titulos, tamanhos, cores, listas, tabelas, imagens e destaques) e gravado como **HTML sanitizado**. Publicacoes antigas e as
criadas por codigo (como a nota de lancamento) usam **markdown seguro**. Este documento explica os dois formatos, as garantias
de seguranca e como publicar uma nota global (o caso do lancamento do LuftBase). O fluxo de criacao, publicacao e notificacao esta no [doc 13](13-NOTIFICACOES-E-PUBLICACOES.md).

Codigo: `conteudo/html_seguro.py` (sanitizador do editor), `conteudo/formatacao.py` (une os formatos e gera o resumo),
`interface/static/js/editor_rico.js` (editor), `conteudo/markdown_seguro.py` (renderizador markdown), `web/publicacoes.py` (rotas),
`interface/static/css/publicacoes.css` (aparencia), `conteudo/changelog_plataforma.py` (nota de lancamento).

## Editor visual (formato HTML)

No painel (Comunicados ou Changelog > Novo), o campo **Mensagem** tem uma barra com: desfazer/refazer; estilo (paragrafo, titulo,
subtitulo, secao); tamanho (12, 15, 20, 28 e 40 px); negrito, italico, sublinhado e tachado; cor do texto e marca-texto;
alinhamento; listas, citacao e linha divisoria; destaques (informacao, sucesso, alerta, perigo); link (Ctrl+K); imagem; tabela;
limpar formatacao. Ao clicar numa imagem aparecem largura (25 a 100%), descricao (acessibilidade) e remover; dentro de uma tabela,
adicionar ou remover linha e coluna. Colar de e-mail ou Word mantem so o que o editor sabe representar, e colar ou arrastar uma
imagem envia o arquivo. A aba **Pre-visualizar** chama `POST /publicacoes/api/previa` e mostra o resultado ja sanitizado.

- **Formato**: `tb_publicacao.formato_conteudo` = `HTML` (editor) ou `MARKDOWN` (padrao, conteudo antigo). Abrir uma publicacao
markdown no editor a converte; ao salvar vira HTML. `NovaPublicacao(formato="HTML")` sanitiza o texto na criacao.
- **Imagens**: enviadas por `POST /publicacoes/api/imagens` (multipart, campo `arquivo`, so com permissao de criar ou editar). O tipo e
decidido pelos primeiros bytes (PNG, JPEG, GIF, WebP; SVG e recusado), limite de 5 MB. Ficam em `core.tb_publicacaoimagem` e, no
texto, como `luftimg:<id>`, independente do prefixo da aplicacao; o link real e resolvido na exibicao. A imagem nasce solta e e
vinculada a publicacao quando ela e salva (uma imagem ja vinculada a outra publicacao nao e reaproveitada).
- **Resumo**: se o autor nao escrever, o LuftBase gera um texto sem marcacao (ate 280 caracteres) a partir da mensagem; ele e a
mensagem da notificacao e o texto das listas.

## Sintaxe suportada (markdown)

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

### HTML do editor

O navegador nunca e confiavel: o servidor sanitiza ao salvar (`NovaPublicacao`), na pre-visualizacao e **de novo ao exibir**.

- So passam as tags `p div span br hr h2 h3 h4 strong em u s sub sup ul ol li blockquote a img code table thead tbody tr th td`
(`b`, `i`, `strike`, `h1`, `h5` e `h6` sao convertidas). `script`, `style`, `iframe`, `object`, `svg` e similares somem com o conteudo; as demais tags perdem a marcacao e o texto fica.
- Atributos de evento (`onclick`...) nunca passam. `a` so com `http://`, `https://` ou `mailto:` (nova aba, `noopener noreferrer`).
- `style` aceita so cor, cor de fundo, tamanho da letra (8 a 72 px), alinhamento, negrito, italico, decoracao e largura (so em imagem e tabela); nada de `url(...)` nem `position`. `class` so nos destaques `pub-callout`, `pub-info`, `pub-sucesso`, `pub-alerta`, `pub-perigo`.
- `img`: so imagem interna (`luftimg:`), estatica do LuftBase (`luftbase:img/...`) ou `https://`.
- A rota de imagem responde com `X-Content-Type-Options: nosniff` e CSP `sandbox`, e so entrega a quem pode ver a publicacao.

Testes: `tests/test_conteudo_rico.py` e `tests/test_repositorio_conteudo_rico.py`.

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
