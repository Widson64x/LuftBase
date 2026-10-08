# Variaveis de ambiente (referencia)

Todas as variaveis que o LuftBase le, com o padrao e o efeito. A aplicacao le o `.env` **uma vez, ao iniciar**: mudou, reinicie o
servico. Ordem de precedencia: `app.config` > variaveis do processo > arquivo `.env` ([doc 04](04-CONFIGURACAO-E-VAULT.md)).

Nunca coloque senhas de banco, de e-mail ou de LDAP no `.env`: elas ficam no **Vault**. O `.env` guarda so o necessario para
chegar ao Vault e para identificar o sistema.

## Identidade do sistema e Vault (obrigatorias)

| Variavel | Padrao | Efeito |
|---|---|---|
| `LUFT_AMBIENTE` | `desenvolvimento` | `desenvolvimento`, `homologacao` ou `producao`. Define o caminho dos segredos (`luft/<ambiente>/...`), o rigor da validacao e se o servidor de desenvolvimento usa depurador. |
| `LUFT_SISTEMA_ID` | - | Id numerico do sistema em `core.tb_sistema` (0 = Workspace). **E a unica identidade de bootstrap**: nome, icone e link vem do core; schema e role vem do segredo do sistema no Vault. |
| `LUFT_VAULT_ENDERECO` | - | URL do Vault (ex.: `http://vault:8200`). |
| `LUFT_VAULT_NAMESPACE` | `luft` | Raiz dos caminhos no Vault. |
| `LUFT_VAULT_TOKEN` | - | Token **protegido** (cifrado). |
| `LUFT_TOKEN_ACESSO` | - | Chave que revela o token acima. Tambem deriva a chave que cifra as senhas SFTP do Integrador (por ambiente, nao portavel). |
| `LUFT_VAULT_CONEXAO_DIRETORIO` | `user.services` | Nome da conexao SQL Server do **diretorio** (usuarios e grupos). |

## Login corporativo (LDAP) e sessao

| Variavel | Padrao | Efeito |
|---|---|---|
| `LUFT_LDAP_SERVIDOR` / `LUFT_LDAP_DOMINIO` | - | Servidor e dominio do Active Directory. |
| `LUFT_LDAP_TRANSPORTE` | `ldaps` | `ldaps` (porta 636) ou `starttls` (389). Texto puro nao existe. |
| `LUFT_LDAP_PORTA` | conforme o transporte | Porta do LDAP. |
| `LUFT_LDAP_TIMEOUT_SEGUNDOS` | `5` | Espera maxima do login (1-60). Editavel pelo painel. |
| `LUFT_SESSAO_TTL_MINUTOS` | `10` | Minutos **sem atividade** ate a sessao expirar (1-10080). Editavel pelo painel. |
| `LUFT_SESSAO_COOKIE_NOME` | `luft_sessao` | Nome do cookie (igual em todos os sistemas para haver SSO). |
| `LUFT_SESSAO_COOKIE_DOMINIO` | vazio | Dominio pai para compartilhar entre subdominios; vazio em desenvolvimento. |
| `LUFT_SESSAO_COOKIE_CAMINHO` | `/` | Caminho do cookie (deve comecar com `/`). |
| `LUFT_SESSAO_COOKIE_SAMESITE` | `Lax` | `Lax`, `Strict` ou `None` (so com cookie seguro). |
| `LUFT_SESSAO_COOKIE_SEGURO` | `false` | `true` forca `Secure` em qualquer ambiente. Em **producao** o cookie ja e `Secure` mesmo com `false`, salvo `LUFT_PERMITIR_COOKIE_INSEGURO=true`. |
| `LUFT_URL_PUBLICA` | vazio | Endereco publico da plataforma (ex.: `https://portal.luft.com.br`) usado nos links dos e-mails de acesso liberado. Vazio: usa o host da requisicao de quem libera o acesso. |
| `LUFT_PERMITIR_COOKIE_INSEGURO` | `false` | Em producao o cookie e `Secure`. Se o site ainda e HTTP, ponha `true` (excecao temporaria, avisada no log). |

## Autorizacao

| Variavel | Padrao | Efeito |
|---|---|---|
| `LUFT_AUTORIZACAO_TTL_SEGUNDOS` | `300` | Quanto tempo um lote de decisoes de permissao fica em cache (5-3600). |
| `LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS` | `5` | Janela em que uma revisao antiga pode ser reutilizada antes de conferir o banco (1-60). |
| `LUFT_AUTORIZACAO_MAX_CHAVES` | `100` | Maximo de chaves por consulta em lote (1-500). |

## Servidor e rede ([doc 17](17-SERVIDOR-REDE-E-FUSO.md))

| Variavel | Padrao | Efeito |
|---|---|---|
| `LUFT_SERVIDOR_HOST` (`HOST`) | `127.0.0.1` | Endereco de escuta. |
| `LUFT_SERVIDOR_PORTA` (`PORT`) | `8000` | Porta. Precisa bater com a porta que o nginx usa para o sistema. |
| `LUFT_SERVIDOR_PREFIXO` (`ROUTE_PREFIX`) | vazio | Prefixo de URL (ex.: `/Luft-ConnectAir`). |
| `LUFT_SERVIDOR_THREADS` | `8` | Threads do Waitress. |
| `LUFT_PROXY_CONFIAVEL` | `127.0.0.1` | IP do nginx autorizado a informar o IP real; `desligado` desativa. |
| `LUFT_FUSO_HORARIO` | `America/Sao_Paulo` | Fuso unico do processo, dos logs e das conexoes PostgreSQL. |
| `LUFT_URL_WORKSPACE` | `/` | Para onde a "casinha" do caminho de navegacao leva. |
| `LUFT_LOG_DIR` | `Logs` | Pasta dos logs fisicos (`luftbase.log`, `temp/`). |

## Bancos de negocio

| Variavel | Padrao | Efeito |
|---|---|---|
| `SQLSERVER_CONEXAO` | `consulta` | Nome da conexao SQL Server (ERP/TMS) no Vault, usada por ConnectAir e Integrador. So leitura. |
| `SQLSERVER_NEGOCIO_AMBIENTE` / `NEGOCIO_AMBIENTE` | ambiente da plataforma | De qual ambiente vem o banco de negocio (ex.: homologacao usando o ERP de producao em leitura). |

## E-mail e links publicos

| Variavel | Padrao | Efeito |
|---|---|---|
| `EMAIL_LINK_VALIDADE_DIAS` | `7` | Validade (1-60) dos links publicos enviados por e-mail (ConnectAir). |
| `URL_BASE_SISTEMA` | - | Endereco externo do sistema, usado nos links dos e-mails; sem ela usa o endereco da requisicao. |

A conta SMTP, o modo teste e os destinatarios de teste ficam no Vault (`luft/<ambiente>/integracoes/email`).

## Auditoria e diagnostico

| Variavel | Padrao | Efeito |
|---|---|---|
| `LUFT_AUDITORIA_DADOS_DESDE` | vazio | Instante ISO 8601 (ex.: `2026-10-06T17:00`) antes do qual a Auditoria ignora os dados ([doc 15](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md)). |
| `LUFT_BASE_REPOSITORIO` | `Widson64x/LuftBase` | Repositorio consultado pelo verificador de versao. |
| `LUFT_GITHUB_TOKEN` | vazio | Token opcional para o verificador de versao (o repositorio e publico). |

## Quais dessas o painel pode editar

So uma lista fechada, nunca segredos: `LUFT_SESSAO_TTL_MINUTOS`, `LUFT_LDAP_TIMEOUT_SEGUNDOS`, `LUFT_AUTORIZACAO_*`,
`EMAIL_LINK_VALIDADE_DIAS`, `SQLSERVER_NEGOCIO_AMBIENTE`/`NEGOCIO_AMBIENTE` e `LUFT_AUDITORIA_DADOS_DESDE`
([doc 14](14-PAINEL-DE-CONTROLE.md)).

## Variaveis proprias das aplicacoes

Cada sistema documenta as suas: ConnectAir (`DB_CONNECT_LOGS`, `EMAIL_LINK_VALIDADE_DIAS`, `URL_BASE_SISTEMA`) e Integrador
(`ECOBOX_SAIDA`, reserva ate o destino ser cadastrado no banco). Veja os repositorios
[Luft-ConnectAir](https://github.com/Widson64x/Luft-ConnectAir) e [Luft-Integrador](https://github.com/Widson64x/Luft-Integrador).
