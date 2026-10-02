# Design system e temas

No perfil web, tokens, CSS base, acessibilidade e JavaScript essencial sao obrigatorios. Nao
existem flags `injetar_tema`, `injetar_global`, `injetar_animacoes` ou `injetar_js`.

## Uso pela aplicacao

Templates da aplicacao estendem a base instalada pelo pacote:

```jinja2
{% extends "luftbase/base.html" %}
{% from "luftbase/componentes.html" import alerta, botao, campo, cartao %}

{% block titulo %}Dashboard{% endblock %}
{% block conteudo %}
  {% call cartao("Resumo operacional") %}
    {{ alerta("Dados atualizados.") }}
    {{ botao("Atualizar") }}
  {% endcall %}
{% endblock %}
```

A base inclui folha estrutural, folha do tema ativo, JavaScript essencial, link para pular ao
conteudo, landmarks, regiao `aria-live` e seletor de aparencia. A aplicacao adiciona apenas
seus estilos no bloco `estilos`, usando a camada CSS `aplicacao`.

## Conceitos

- familia de tema: identidade visual, como `luft` ou uma futura familia de operacoes;
- modo: `CLARO`, `ESCURO` ou `SISTEMA`;
- tokens semanticos: fundo, superficie, texto, borda, destaque, foco e estados;
- manifesto: identificador, nome, versao, URL local e modos suportados.

O modo `SISTEMA` acompanha `prefers-color-scheme`; ele nao e uma terceira paleta. Componentes
nao dependem de cores literais da marca. Eles usam tokens `--luft-cor-*`, por isso uma nova
familia nao exige alterar HTML, componentes ou JavaScript.

## Preferencia

`tb_preferenciausuario` no schema `core` e a fonte definitiva. A primeira renderizacao da
sessao carrega a preferencia e guarda um retrato JSON na sessao Redis compartilhada. A rota
`PUT /_luftbase/interface/preferencia` persiste a alteracao e atualiza esse retrato.

A escrita exige usuario autenticado e `X-CSRF-Token`, publicado pela base na meta tag
`luft-csrf-token`. A rota GET permite consultar a preferencia atual. Nenhuma preferencia fica
dependente somente de `localStorage`.

## Extensibilidade

Depois de inicializar a plataforma e antes de servir requisicoes, registre um manifesto:

```python
from luftbase import ManifestoTema, obter_luftbase

obter_luftbase().temas.registro.registrar(
    ManifestoTema(
        identificador="operacoes",
        nome="Operacoes",
        versao="1.0.0",
        url_css="/static/temas/operacoes.css",
    )
)
```

A URL deve ser local, o identificador deve ser um slug e toda familia precisa oferecer os
modos claro e escuro. Tema ausente ou removido cai explicitamente em `luft`, preservando o
modo do usuario. O arquivo externo continua responsavel por definir todos os tokens
semanticos e deve passar os mesmos testes de contraste e acessibilidade.

## Componentes iniciais

`luftbase/componentes.html` fornece macros de botao, cartao, alerta, campo e distintivo. Os
campos ligam rotulo, ajuda, obrigatoriedade e controle; alertas usam papeis adequados. Novos
componentes devem manter navegacao por teclado, foco visivel, HTML semantico e suporte a
`prefers-reduced-motion`.

## E-mail

E-mails nao recebem CSS, tokens nem JavaScript do perfil web: clientes como Outlook e Gmail
exigem tabelas e estilo inline. Por isso o layout de e-mail tem cores fixas da marca.

- `luftbase/email/base.html`: cabecalho com logo embutido (`cid:luftbase-logo`), faixa de
  modo teste automatica, area de conteudo e rodape com o nome do sistema. Blocos: `previa`,
  `titulo_cabecalho`, `faixa`, `conteudo`, `rodape_extra`.
- `luftbase/email/componentes.html`: `faixa(texto, tipo)` (`sucesso`, `aviso`, `perigo`,
  `info`), `titulo(texto, rotulo)`, `paragrafo(texto)` ou `{% call %}`, `tabela_resumo(linhas)`,
  `botao(url, texto)` com VML para Outlook, `nota(texto)` e `divisor()`.
- O `ServicoEmail` injeta `luft_email` (`sistema`, `ambiente`, `modo_teste`,
  `destinatarios_reais`, `cid_logo`, `gerado_em`, `ano`) e so anexa o logo se o HTML o usar.

```jinja
{% extends "luftbase/email/base.html" %}
{% import "luftbase/email/componentes.html" as ui_email %}

{% block faixa %}{{ ui_email.faixa("Planejamento disponivel para expedicao") }}{% endblock %}
{% block conteudo %}
  {{ ui_email.titulo(filial_titulo, rotulo="Filial expedidora") }}
  {{ ui_email.tabela_resumo([("Planejamentos", planejamentos), ("CTCs", ctcs)]) }}
  {{ ui_email.nota("A planilha segue anexada.") }}
{% endblock %}
{% block rodape_extra %}Em caso de duvidas, fale com a Torre de Controle.{% endblock %}
```

## Politica de assets

- nenhum CDN e necessario para o perfil base;
- os assets pertencem ao wheel e sao servidos em `/_luftbase/static`;
- o template nao contem JavaScript inline;
- CSS particular nao redefine tokens para corrigir um componente isolado;
- imagens, fontes e icones opcionais precisam de origem compativel com a CSP da aplicacao;
- a aplicacao deve versionar temas externos e registra-los antes da primeira requisicao.
