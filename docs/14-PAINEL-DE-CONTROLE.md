# Painel de Controle

O Painel de Controle e a area administrativa que **todo sistema Luft herda do LuftBase**. Ele aparece em
`<sistema>/configuracoes/painel` (e `/admin/painel`, compativel). O que cada pessoa ve depende das permissoes dela:
uma aba sem permissao simplesmente nao aparece.

O Workspace enxerga o ecossistema inteiro; um sistema satelite (ConnectAir, Integrador...) enxerga **so a si mesmo**
(escopo fail-closed: um id de sistema fora do escopo e recusado).

## Abas

| Aba | Para que serve | Permissao que libera |
|---|---|---|
| Seguranca & Permissoes | conceder acessos, copiar permissoes, criar modulos e permissoes | `SEGURANCA.PERMISSOES.VISUALIZAR` |
| Aplicacoes & Ambiente | cadastrar sistemas, manutencao, variaveis de ambiente e servicos | `CONFIGURACOES.SISTEMAS.*`, `AMBIENTE.*` |
| Comunicacao | comunicados e notas de atualizacao | `CONTEUDO.COMUNICADOS.*`, `CONTEUDO.ATUALIZACOES.*` |
| Auditoria & Analise | acessos, desempenho, seguranca, ao vivo, controle de sessoes | `OBSERVABILIDADE.AUDITORIA.VISUALIZAR` ([doc 15](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md)) |
| Configuracoes Gerais | parametros declarados pela aplicacao (`ParametroAplicacao`) | `CONFIGURACOES.PAINEL.VISUALIZAR` |
| Integracoes | estado do Vault, bancos, e-mail, LDAP e versoes | `AMBIENTE.SERVICOS.VISUALIZAR` |

## Seguranca e permissoes

- **Gerenciador**: busca um grupo ou usuario, mostra a arvore de modulos/permissoes do sistema escolhido e salva as
  concessoes. Conceder um no concede tambem os filhos (ver [doc 11](11-AUTORIZACAO.md)).
- **Copiar permissoes** (espelhar), em tres passos, vendo antes o que sera copiado:
  1. escolher a **origem** (usuario ou grupo de referencia);
  2. marcar quais permissoes copiar (o resto e ignorado);
  3. escolher o **destino** e confirmar.
  Se o destino ainda nao tem cadastro em `core.tb_usuario`, o LuftBase o cria a partir do diretorio antes de gravar a
  regra (`garantir_usuario_do_core`), evitando erro de chave estrangeira. A copia fica na auditoria.
- **Limpar todas**: remove as regras individuais de uma pessoa (acao sensivel, com confirmacao).
- **Modulos e permissoes**: criar modulo, criar permissao e editar a estrutura. Aplicacoes satelite declaram as suas em
  `App/Catalogo.py`; o LuftBase **completa** o core a cada inicializacao, sem apagar nada ([doc 11](11-AUTORIZACAO.md) e
  [doc 19](19-GUIA-DA-APLICACAO-SATELITE.md)).

## Aplicacoes e ambiente

### Sistemas
Cadastro de cada sistema do ecossistema (`core.tb_sistema`): nome, descricao, icone, cor, link, `url_saude`, responsavel,
contato, categoria, ativo e **em manutencao**. O nome do sistema e a chave para achar o servico no servidor (abaixo).

### Manutencao
Alternar um sistema para "em manutencao" faz o middleware responder 503 nas rotas comuns; `/_luftbase/saude` e as rotas de
login e estaticos continuam respondendo. Quem tem `CONFIGURACOES.MANUTENCAO.IGNORAR` continua usando o sistema.

### Variaveis de ambiente
Mostra e edita **somente** chaves de uma **lista fechada** (allowlist) do `.env` de cada ambiente
(`infraestrutura/variaveis_ambiente.py`). Hoje:

| Chave | O que controla | Validacao |
|---|---|---|
| `LUFT_SESSAO_TTL_MINUTOS` | minutos sem atividade ate a sessao expirar | inteiro 1-10080 |
| `LUFT_LDAP_TIMEOUT_SEGUNDOS` | espera maxima do login corporativo | inteiro 1-60 |
| `LUFT_AUTORIZACAO_TTL_SEGUNDOS` | cache das decisoes de permissao | 5-3600 |
| `LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS` | intervalo para perceber mudancas | 1-60 |
| `LUFT_AUTORIZACAO_MAX_CHAVES` | chaves por consulta | 1-500 |
| `EMAIL_LINK_VALIDADE_DIAS` | validade dos links publicos enviados por e-mail | inteiro |
| `SQLSERVER_NEGOCIO_AMBIENTE` / `NEGOCIO_AMBIENTE` | de qual ambiente vem o banco de negocio | opcoes |
| `LUFT_AUDITORIA_DADOS_DESDE` | corte de data das analises da auditoria | ISO 8601 ou vazio |

Regras de seguranca: tokens, enderecos do Vault, identidade do sistema, cookies e LDAP **nunca** aparecem nem podem ser
alterados pela web; cada chave tem validador (valor invalido ou com quebra de linha e recusado antes de tocar no arquivo).
Ao salvar: preserva comentarios, ordem e quebra de linha, faz copia (`.env.bak`) e troca o arquivo de forma atomica.
**A aplicacao so le o `.env` ao iniciar**: depois de salvar, reinicie o servico.

### Servicos do servidor
Lista o estado do servico de cada sistema e permite **iniciar, parar e reiniciar**, sem acesso ao servidor
(`AMBIENTE.SERVICOS.VISUALIZAR` / `EXECUTAR`).

- O servico e achado pelo **nome do sistema** no catalogo, sem lista no `.env`:
  - Linux (systemd): minusculo + `.service` (`Luft-ConnectAir` -> `luft-connectair.service`);
  - Windows (servico/NSSM): o proprio nome (`Luft-ConnectAir`).
- So se opera sobre sistemas cadastrados (a rota valida o id contra o catalogo); o nome passa por lista de caracteres
  permitidos (`^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$`); comandos rodam **sem shell**, com lista de argumentos e limite de 20 s.
- Estados: `RUNNING`, `STOPPED`, `STARTING`, `NOT_FOUND`, `UNAVAILABLE`.
- No Linux a conta do servico precisa de permissao (sudo sem senha) para o `systemctl` dos servicos Luft; sem ela o estado
  aparece como indisponivel.
- Toda acao entra na auditoria com o nome de quem pediu.

## Configuracoes gerais

Parametros que a aplicacao declara com `ParametroAplicacao` aparecem aqui, com permissao propria. E o lugar onde, por
exemplo, o Integrador oferece a tela "Parametros das Integracoes" e o ConnectAir, o cadastro de companhias aereas.

## Integracoes (somente leitura)

Um cartao por dependencia: **PostgreSQL**, **SQL Server**, **Sessoes** (cache e sessao), **E-mail** (SMTP ou Gmail), **Login
corporativo** (LDAP), **Vault**, **LuftBase**, **Componentes** e **Aplicacao**. Cada um mostra:

- **de onde a configuracao vem** (caminho no Vault, sem valor secreto);
- **saude** (conecta ou nao, em quanto tempo);
- **versoes**: do LuftBase em cada sistema e dos componentes (Flask, SQLAlchemy, Alembic, Psycopg, pyodbc, oracledb,
  hvac, redis-py, ldap3, cryptography, Waitress).

Regra de ouro (`integracoes/diagnostico.py`): so os **nomes** dos campos de cada segredo sao mostrados; apenas uma lista
fixa de campos nao sensiveis (host, porta, banco, usuario, esquema, sslmode...) tem o valor exibido. O resto aparece como
"oculto". Ha ainda um **verificador de versao**: compara a versao instalada do LuftBase com a ultima tag no GitHub
(`Widson64x/LuftBase`, repositorio publico; `LUFT_GITHUB_TOKEN` e opcional) com cache.

## Comunicacao

Comunicados e notas de atualizacao ([doc 13](13-NOTIFICACOES-E-PUBLICACOES.md) e
[doc 21](21-CONTEUDO-RICO-E-NOTAS-DE-ATUALIZACAO.md)).

## Rotas (para quem integra)

Todas sob `/configuracoes` (e espelho em `/admin`), protegidas por login, permissao e, nas gravacoes, CSRF:
`GET /painel`, `POST /api/configuracoes/manutencao/alternar|lote`, `POST /api/configuracoes/sistema/atualizar|criar`,
`GET /api/configuracoes/ambiente/variaveis`, `POST .../variaveis/salvar`, `GET .../ambiente/servicos`,
`POST .../servicos/acao`, `GET /api/configuracoes/integracoes`, `GET .../integracoes/versao-luftbase`.
