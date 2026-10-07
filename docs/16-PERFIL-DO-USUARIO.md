# Perfil do usuario

O perfil e uma gaveta ("drawer") que abre ao clicar no nome da pessoa (botao `btn-perfil-usuario`, na barra lateral de
qualquer sistema). Ela e herdada do LuftBase: `interface/templates/luftbase/perfil/drawer.html`, `static/js/perfil.js`,
`static/css/perfil.css`. Os dados ficam em `core.tb_usuario` e valem para **todos os sistemas** (a pessoa muda a foto uma vez).

## Abas

### Dados e contatos
- Nome, telefone, celular, cargo, departamento e unidade/filial (editaveis); **login e codigo do usuario sao imutaveis**.
- Gravar: `POST /_luftbase/perfil` (JSON, com CSRF). Campos desconhecidos sao ignorados.

### Aparencia e tema
- Tema (`luft`, `luft-esg`, ...) e modo (`CLARO`, `ESCURO`, `SISTEMA`). Valores fora do registro de temas sao recusados (400).
- O campo **Idioma** existe no modelo (`idioma`, padrao `pt-BR`), mas o seletor esta **comentado no template** (a
  interface so tem portugues hoje); o envio so inclui `idioma` se o campo existir na tela.
- Alterar so o modo: `PUT /_luftbase/interface/preferencia`.

### Sessoes e seguranca
- **Resumo**: status atual, total de logins, ultimo acesso e IP registrado. O "total de logins" soma 1 a cada **login novo**
  (nao a cada renovacao da sessao). O IP e o real do usuario (veja o [doc 17](17-SERVIDOR-REDE-E-FUSO.md)).
- **Dispositivos conectados** (`GET /_luftbase/perfil/sessoes`): sessoes `ATIVA` da pessoa, cada uma com **navegador e SO**
  (ex.: "Chrome 126 em Windows"), IP, ultima atividade e o selo "Esta sessao". O navegador vem de
  `identidade/agente_usuario.py`.
- **Desconectar outras sessoes** (`POST /_luftbase/perfil/sessoes/revogar-outras`): encerra todas as outras sessoes
  ativas da pessoa, menos a atual.
- **Historico de acessos** (`GET /_luftbase/perfil/sessoes/historico`): os **5 ultimos** acessos (ativos e encerrados)
  com IP, navegador, inicio, fim e **motivo do encerramento** (saiu da conta, expirou por inatividade, sessao renovada,
  encerrada a forca).

## Foto de perfil

- Abrir: clicar na camera sobre o avatar abre o **editor**: recorte circular, arrastar, zoom (100%-300%, roda do mouse),
  girar, centralizar, setas do teclado (Shift move mais), arrastar um arquivo para a janela.
- Formatos aceitos: PNG, JPEG e WebP, **ate 8 MB no navegador**; o editor exporta **256 x 256 px em WebP** (PNG se o
  navegador nao gerar WebP). O servidor aceita corpo JSON com `data:image/...` ou arquivo multipart de **ate 4 MB**.
- **Remover foto** pede confirmacao no proprio botao (sem janela do navegador).
- Rotas: `POST /_luftbase/perfil/foto`, `DELETE /_luftbase/perfil/foto`. A imagem fica em `core.tb_usuario.foto_perfil`
  (data URI) e e copiada para a sessao da pessoa.

## Avatar padrao

Em qualquer lugar que mostre uma pessoa, use o **mesmo avatar do botao de perfil** (classes `luft-avatar`,
`luft-avatar-img`, `luft-avatar-initials`, `luft-status-dot`): a foto, ou as iniciais da **primeira e da ultima palavra do
nome**, com o ponto de online. Foi assim que a lista "Quem esta conectado" da auditoria passou a ser montada.

## Presenca ("Online")

O ponto verde e o selo "Online" refletem `core.tb_usuario.status_online`, que so e verdadeiro enquanto existir uma sessao
`ATIVA` da pessoa. Ao sair, a pessoa deixa de aparecer como online imediatamente ([doc 10](10-IDENTIDADE-E-SESSAO.md)).

## Para quem desenvolve

- O drawer e movido para o `<body>` por JavaScript quando o editor de foto abre (o drawer usa `transform`, que prenderia o
  `position: fixed` do modal).
- Toda gravacao exige o token `X-CSRF-Token` (meta `luft-csrf-token`).
- Nenhuma resposta devolve senha ou token. A lista de dispositivos da **propria pessoa** inclui o identificador da sessao
  (a tela mostra uma versao abreviada); ja o painel administrativo da auditoria usa so uma referencia (hash).
