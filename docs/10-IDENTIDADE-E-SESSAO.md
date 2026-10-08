# Identidade e sessao

Este documento descreve, passo a passo, como uma pessoa entra, como a sessao dela vive e como ela sai.
Tudo aqui reflete o codigo atual (`src/luftbase/identidade`).

## Visao em uma figura

```text
 navegador                 aplicacao Flask (LuftBase)                         bancos
 ---------                 ------------------------------                     ------
 POST /login  ───────────► ServicoAutenticacao.autenticar()
                              1. LDAP valida a senha ──────────────────────► Active Directory
                              2. Diretorio devolve usuario e grupo ────────► SQL Server (somente leitura)
                              3. core.tb_usuario e criado/atualizado ──────► PostgreSQL (core)
                           iniciar_sessao_usuario()
                              4. sessao nova (id aleatorio) ───────────────► core.tb_sessao  (status ATIVA)
 cookie luft_sessao ◄───── 5. cookie assinado com o id da sessao
 GET /qualquer-sistema ──► 6. cookie -> id -> dados da sessao ─────────────► core.tb_sessao (renova a validade)
```

## Os tres bancos da identidade

| Papel | Onde | O que guarda | Escrita? |
|---|---|---|---|
| Diretorio corporativo | SQL Server (`bancos.diretorio`) | usuario, e-mail, grupo (Luftinforma) | nunca: so leitura |
| Core | PostgreSQL schema `core` | `tb_usuario`, `tb_sessao`, `tb_sessao_evento`, permissoes, preferencias | sim |
| Aplicacao | PostgreSQL schema do sistema | dados de negocio do sistema | sim |

O modelo ORM do diretorio nunca herda de `BaseLuft`: o Alembic jamais tenta criar ou alterar tabelas no SQL Server.

## Login, passo a passo

`ServicoAutenticacao.autenticar(login, senha)`:

1. Recusa login ou senha vazios.
2. Se o login contem `@`, procura o usuario no diretorio pelo e-mail e usa o login real encontrado.
3. Pede ao LDAP para validar o par login/senha (`ldaps` na porta 636 ou `starttls` na 389; texto puro nao existe).
   Credencial errada devolve `None`; indisponibilidade do LDAP vira erro controlado, sem repetir servidor, login ou senha.
4. Carrega o retrato do usuario no diretorio (`UsuarioAutenticado`: id, login, nome, e-mail, grupo).
5. **Confere o bloqueio** (`core.tb_usuario.bloqueado`). Com a senha correta e a pessoa bloqueada, levanta
   `ErroUsuarioBloqueado`: a tela de entrada responde **403** com "Seu acesso esta bloqueado. Procure um administrador."
   (o motivo interno nao aparece) e a auditoria registra `LOGIN_BLOQUEADO`. A regra e **fail-closed**: se o banco falhar
   ao conferir, vira `ErroAutenticacao` (503, "indisponivel"), nunca entrada liberada. Senha errada continua sendo so
   "usuario ou senha invalidos", sem revelar o bloqueio.
6. Sincroniza com o core: `garantir_usuario_do_diretorio` cria ou atualiza a linha em `core.tb_usuario`
   (nome, e-mail, grupo) e devolve foto, cargo, telefone, tema e idioma que a pessoa ja tinha configurado.
   Se essa sincronizacao falhar, o erro e registrado e o login **continua** (a pessoa entra com os dados do diretorio).

## Sessao compartilhada (SSO)

Todas as aplicacoes da Luft guardam a sessao no **mesmo banco** (`core.tb_sessao`) e usam o **mesmo cookie**
(`luft_sessao`, nome configuravel). Por isso entrar em um sistema deixa a pessoa autenticada nos outros.

- O navegador recebe so um identificador aleatorio, assinado (`TimestampSigner`, SHA-256).
  Cookie adulterado ou vencido inicia uma sessao anonima.
- Os dados da sessao ficam no banco como JSON (nunca `pickle`).
- `iniciar_sessao_usuario()` **rotaciona** o identificador depois do login (evita fixacao de sessao).
- O `user_loader` restaura o usuario a partir da propria sessao: nao consulta SQL Server nem PostgreSQL a cada requisicao.

### Estados e validade

`core.tb_sessao.status`:

| Status | Quando |
|---|---|
| `ATIVA` | recem criada ou renovada por atividade |
| `FINALIZADA` | a pessoa saiu (logout) ou o identificador foi rotacionado |
| `EXPIRADA` | passou do prazo sem atividade (detectado na proxima leitura) |
| `REVOGADA` | um administrador (ou "desconectar outras sessoes") encerrou |

- **Validade**: `LUFT_SESSAO_TTL_MINUTOS` (padrao **10** minutos sem atividade; aceita de 1 a 10080). Cada requisicao
  autenticada renova `ultima_atividade` e `expira_em`.
- **Eventos**: cada mudanca gera uma linha em `core.tb_sessao_evento` com `tipo_evento` em
  `INICIO`, `RENOVACAO`, `LOGOUT`, `TIMEOUT` ou `REVOGACAO`, com IP e navegador.
- **Visitantes**: a tela de login tambem precisa de uma sessao (guarda o token anti-CSRF). Essas sessoes tem
  `codigo_usuario` vazio e **nao** contam como pessoa conectada nem como login em nenhum painel.

### O que e gravado a cada requisicao

`ArmazenamentoSessoesPostgreSQL.salvar()` (chamado pela interface de sessao ao final da resposta):

- **IP**: `request.remote_addr`. Atras do nginx ele e o IP real do usuario, desde que o proxy seja confiavel
  (veja [17-SERVIDOR-REDE-E-FUSO.md](17-SERVIDOR-REDE-E-FUSO.md)). O cabecalho `X-Forwarded-For` cru nunca e lido
  diretamente, porque o primeiro item pode ser forjado pelo cliente.
- **Navegador**: cabecalho `User-Agent` (ate 500 caracteres). Le-se o cabecalho direto: `bool(request.user_agent)`
  e sempre falso no Werkzeug e escondia o navegador antes da versao 0.1.0a74.
- **Usuario**: so liga a sessao a uma pessoa quando a sessao tem `status ATIVA` e um usuario reconhecido.
  Uma sessao ja finalizada **nunca** volta a ficar ativa (regra criada para corrigir "online fantasma" depois do logout).
- Se a pessoa fez login agora (sessao nova), incrementa `total_logins` e preenche `ultimo_ip`/`ultimo_user_agent`.

### Presenca online

`core.tb_usuario.status_online` e atualizado por um batimento da interface. A atualizacao so vale se existir uma sessao
`ATIVA` daquele usuario com aquele identificador: um batimento que chega depois do logout nao marca ninguem como online.

## Logout

`encerrar_sessao_global()`:

1. marca a sessao como `FINALIZADA` (evento `LOGOUT`), zera `status_online` e `id_sessao_atual` da pessoa;
2. limpa a sessao do Flask e **ordena ao Flask-Login que apague o cookie "lembrar"** (`_remember = "clear"`);
3. `descartar_cookie_lembrar` roda antes de cada requisicao para o cookie `remember_token` nao recriar a sessao.

Como a sessao e compartilhada, sair de um sistema sai de todos.

## Controle administrativo

- **Bloquear o login de uma pessoa**: no Gerenciador de Permissoes (`/seguranca/gerenciador`), no modo Usuario, o botao
  "Bloquear acesso" (permissao `SEGURANCA.USUARIOS.DESATIVAR`) pede o motivo, grava `bloqueado` e `motivo_bloqueio`,
  **derruba todas as sessoes ativas** da pessoa (motivo `BLOQUEIO_ADMIN`) e audita `USUARIO_BLOQUEADO`. "Desbloquear
  acesso" devolve o direito de entrar. Ninguem bloqueia o proprio acesso. Rotas: `POST /seguranca/api/usuarios/bloquear`,
  `POST /seguranca/api/usuarios/desbloquear`, `GET /seguranca/api/usuarios/<id>/bloqueio`.
- **Aviso na tela de entrada**: quando a sessao e derrubada por um administrador (`REVOGADA_ADMIN` ou `BLOQUEIO_ADMIN`),
  a proxima visita da pessoa cai no login com "Sua sessao foi encerrada por um administrador. Entre novamente." (ou a
  mensagem de bloqueio), uma unica vez. Sai de `ArmazenamentoSessoesPostgreSQL.motivo_encerramento`, consultado so quando
  o cookie e valido mas a sessao nao esta mais ativa; se a consulta falhar, apenas nao avisa.
- A pessoa pode **desconectar as outras sessoes** no proprio perfil ([16-PERFIL-DO-USUARIO.md](16-PERFIL-DO-USUARIO.md)).
- Quem tem `SEGURANCA.SESSOES.REVOGAR` pode encerrar uma sessao, desconectar uma pessoa ou todos
  ([15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md)).
- `ArmazenamentoSessoesPostgreSQL.revogar_sessao(id, motivo)` e o caminho de revogacao: muda o status para `REVOGADA`,
  apaga os dados da sessao, grava o evento `REVOGACAO` e atualiza a presenca da pessoa.

## Redis

O Redis e opcional e **nao guarda sessao** quando o PostgreSQL e o armazenamento ativo (o caso padrao nos ambientes
atuais). Ele serve de cache de autorizacao e de sinalizador de conteudo (notificacoes e publicacoes). Sem Redis, a
plataforma usa um armazenamento em memoria para esses dois usos e registra no log
`Sessoes no PostgreSQL (core); Redis nao configurado em ...`.

## Seguranca resumida

- Senha nunca e gravada nem registrada.
- Cookie com `Secure` obrigatorio em producao (a excecao precisa de `LUFT_PERMITIR_COOKIE_INSEGURO=true`, explicita e avisada no log).
- `SameSite` padrao `Lax`; nome, caminho e dominio configuraveis.
- Toda mutacao HTTP exige o token CSRF da sessao (`X-CSRF-Token`).
