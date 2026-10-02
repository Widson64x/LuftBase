# Configuracao e Vault

## Variaveis canonicas

```dotenv
LUFT_AMBIENTE=desenvolvimento
LUFT_SISTEMA_ID=0
LUFT_VAULT_ENDERECO=http://vault:8200
LUFT_VAULT_NAMESPACE=luft
LUFT_VAULT_TOKEN=valor_protegido
LUFT_TOKEN_ACESSO=segredo_da_aplicacao
LUFT_LDAP_SERVIDOR=ad.exemplo.interno
LUFT_LDAP_DOMINIO=DOMINIO
LUFT_LDAP_TRANSPORTE=ldaps
LUFT_SESSAO_COOKIE_NOME=luft_sessao
LUFT_SESSAO_COOKIE_DOMINIO=.exemplo.com.br
LUFT_SESSAO_COOKIE_SAMESITE=Lax
LUFT_SESSAO_TTL_MINUTOS=480
LUFT_AUTORIZACAO_TTL_SEGUNDOS=300
LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS=5
LUFT_AUTORIZACAO_MAX_CHAVES=100
```

`LUFT_SISTEMA_ID` e a unica identidade de bootstrap no `.env`. Nome e demais metadados
visuais sao lidos de `core.tb_sistema` pela chave primaria numerica. O identificador textual,
o schema e a role pertencem ao segredo desse sistema no Vault.

## Caminhos derivados

```text
luft/{ambiente}/sqlserver
luft/{ambiente}/bancos/postgresql/conexoes/{alias}
luft/{ambiente}/bancos/postgresql/sistemas/{sistema_id}
luft/{ambiente}/redis/sessoes
luft/{ambiente}/integracoes/email
luft/{ambiente}/bancos/sqlserver/conexoes/{conexao}
```

Nao devem existir variaveis com o caminho completo para esses segredos.

## Precedencia

```text
app.config
    -> variaveis do processo
        -> arquivo .env do diretorio atual
```

O arquivo e lido pelo LuftBase durante a inicializacao, sem chamadas `load_dotenv()` nos
projetos consumidores e sem alterar globalmente variaveis que ja existem no processo.

## Payload PostgreSQL Composto

A estrutura separa a conexao de banco compartilhada das credenciais e esquema de cada aplicacao:

1. Conexao compartilhada
   (`luft/{ambiente}/bancos/postgresql/conexoes/luft-web`):

```json
{
  "tipo_banco": "postgresql",
  "host": "servidor",
  "porta": "5432",
  "nome_banco": "luft_web",
  "sslmode": "prefer"
}
```

2. Credencial canonica do sistema
   (`luft/{ambiente}/bancos/postgresql/sistemas/{sistema_id}`):

```json
{
  "conexao": "luft-web",
  "esquema": "workspace",
  "identificador": "luft-workspace",
  "sistema_id": 0,
  "usuario": "luft_workspace_app",
  "senha": "<segredo>"
}
```

O bootstrap carrega o segredo pelo `LUFT_SISTEMA_ID`, confere se o `sistema_id` do payload e
identico ao solicitado, resolve a conexao apontada e compoe a credencial runtime. O mesmo ID
e usado nas FKs de permissoes, logs, notificacoes e publicacoes.
Tokens e senhas nunca aparecem em `repr`, logs, health checks ou mensagens HTTP.
O campo `esquema` e obrigatorio, usa `snake_case` minusculo e nao pode ser `core`, `public`,
`information_schema` nem comecar por `pg_`.

## Conexoes SQL Server nomeadas

O SQL Server nao tem a divisao por sistema do PostgreSQL, entao cada uso tem uma conexao
propria em `luft/{ambiente}/bancos/sqlserver/conexoes/{conexao}`:

- `user.services` (ou `LUFT_VAULT_CONEXAO_DIRETORIO`): diretorio de usuarios e grupos. O
  `nome_banco` deve ser o banco que contem `usuario` e `usuariogrupo` (hoje `luftinforma`).
- `consulta`: leitura do ERP pelas aplicacoes (o banco `intec`).

O caminho antigo `luft/{ambiente}/sqlserver` so e lido como reserva, com aviso, quando a
conexao nomeada do diretorio nao existe. `porta` e a do SQL Server (1433 por padrao).

## Payload SQL Server

```json
{
  "host": "servidor",
  "nome_banco": "intec",
  "porta": "1433",
  "senha": "segredo",
  "tipo_banco": "sqlserver",
  "usuario": "luft_consulta_app"
}
```

A role SQL Server deve possuir somente os privilegios de consulta necessarios. O LuftBase
tambem impede `commit` pela fronteira de diretorio, mas essa protecao em codigo nao substitui
a permissao `SELECT` no servidor.

## Payload Redis

Todas as aplicacoes leem `luft/{ambiente}/redis/sessoes`:

```json
{
  "host": "servidor",
  "porta": "6379",
  "banco": "0",
  "usuario": "svc_sessoes",
  "senha": "segredo",
  "tls": "true",
  "chave_assinatura_sessao": "segredo-com-no-minimo-32-caracteres"
}
```

`usuario` e opcional. A chave de assinatura deve ser igual entre as aplicacoes do mesmo
ambiente. O cliente usa conexao tardia, timeouts e TLS conforme o segredo. Nenhum dado de
conexao Redis ou chave de assinatura fica no `.env`.

### Estrategia de Sessoes e Cache (PostgreSQL e Redis)

- **PostgreSQL como fonte persistente**: O PostgreSQL Core e o backend definitivo e duravel de sessoes e autorizacao.
- **Redis opcional no piloto**: No ambiente de desenvolvimento e no piloto, a aplicacao funciona plenamente sem Redis, utilizando o armazenamento PostgreSQL.
- **Producao distribuida**: O Redis e recomendado em homologacao e producao multi-instancia para revogacao instantanea de sessoes, pub/sub e cache de autorizacao.
- **Namespace unico por ambiente**: Em producao, adota-se uma unica instancia/servico Redis por ambiente segregada por namespaces de chaves, evitando provisionar instancias separadas por projeto.
- **Proibicao de SQLite em producao**: Nunca utilizar arquivos SQLite locais como solucao de fallback em ambientes produtivos quando o banco PostgreSQL Core estiver disponivel.

## Payload de e-mail

Todas as aplicacoes do ambiente leem `luft/{ambiente}/integracoes/email`:

```json
{
  "host": "smtp.gmail.com",
  "porta": "587",
  "seguranca": "starttls",
  "usuario": "conta@luftlogistics.com",
  "senha": "<senha de app>",
  "remetente": "conta@luftlogistics.com",
  "nome_remetente": "Luft Logistics",
  "redirecionar_para": ""
}
```

- `seguranca`: `starttls` (porta 587) ou `ssl` (porta 465). Canal sem TLS nao e aceito.
- `remetente` e opcional; ausente, usa `usuario`.
- `nome_remetente` e opcional e so e usado quando o sistema nao tem nome em `core.tb_sistema`.
- `redirecionar_para` liga o modo teste: texto separado por `;`/`,` ou lista JSON. Vazio envia
  aos destinatarios reais. Use-o nos segredos de desenvolvimento e homologacao.
- `tipo` e opcional e, se informado, deve ser `smtp`.
- No Gmail, `senha` e uma senha de app da conta, nunca a senha de login.

O segredo e opcional: sem ele a aplicacao sobe e o envio fica indisponivel. Com ele, qualquer
campo invalido interrompe a inicializacao. `luftbase vault verificar --conectar` informa
`email_status` e `luftbase email testar --para <endereco>` envia uma mensagem real de teste.

## LDAP e cookie

Servidor, dominio, transporte, porta e timeout LDAP nao sao segredos e ficam na configuracao
central. Somente `ldaps` e `starttls` sao aceitos. Senhas de usuarios existem apenas durante
a tentativa de autenticacao e nunca sao persistidas.

O cookie contem somente um identificador aleatorio assinado. `HttpOnly` e sempre ligado;
`Secure` e forcado em producao. Para compartilhar a sessao entre subdominios, configure o
mesmo nome e um dominio pai em todas as aplicacoes. Em desenvolvimento local, deixe o dominio
vazio. `SameSite=None` so e aceito com cookie seguro.

## Cache de autorizacao

`LUFT_AUTORIZACAO_TTL_SEGUNDOS` controla por quanto tempo um lote de decisoes fica no Redis.
`LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS` limita a janela em que uma revisao antiga pode ser
reutilizada antes de conferir o PostgreSQL. `LUFT_AUTORIZACAO_MAX_CHAVES` protege consultas em
lote excessivas. Esses valores nao sao segredos; host e credenciais continuam somente no
Vault.

## Token do Vault

`LUFT_VAULT_TOKEN` contem o token protegido. `LUFT_TOKEN_ACESSO` contem a chave fornecida
pelo ambiente para revela-lo. A derivacao Fernet permanece compativel com o LuftCore para
permitir migracao gradual, mas nenhuma chave compartilhada fica escondida no wheel.

O cliente HVAC e criado sem rede. Autenticacao e leitura ocorrem somente dentro de
`PlataformaLuft.inicializar()`. O resultado da autenticacao e reutilizado durante as leituras
daquela inicializacao.

## Contas de runtime

`admin`, `postgres` e `sa` sao rejeitados por padrao. O segredo de cada aplicacao deve usar
uma conta de servico dedicada, por exemplo `luft_workspace_app`, com acesso ao proprio schema
e aos objetos operacionais necessarios do `core`. Contas de migracao e propriedade ficam
separadas da aplicacao.
