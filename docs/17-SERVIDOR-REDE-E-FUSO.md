# Servidor, rede e fuso horario

Como uma aplicacao Luft sobe, como ela enxerga o usuario atras do nginx e por que todos os horarios sao de Brasilia.

## Pontos de entrada

Cada aplicacao tem dois arquivos curtos na raiz:

| Arquivo | Uso | O que chama |
|---|---|---|
| `Wsgi.py` | producao (servico do Windows ou systemd) | `luftbase.servidor.executar("App:CriarApp")` -> **Waitress** |
| `App.py` | desenvolvimento | `executar_desenvolvimento("App:CriarApp")` -> servidor do Flask com depurador |

Pela linha de comando: `luftbase servir App:CriarApp`.

O console e configurado **antes** de importar a aplicacao: as mensagens de inicializacao (Vault, sessoes, catalogo) saem
no mesmo formato em todos os sistemas. Cada requisicao vai somente para o log fisico (`Logs/luftbase.log`); o console mostra a
subida, avisos e erros.

### Variaveis do servidor (argumento > `LUFT_SERVIDOR_*` > variavel legada > padrao)

| O que | Variavel | Legada | Padrao |
|---|---|---|---|
| Endereco | `LUFT_SERVIDOR_HOST` | `HOST` | `127.0.0.1` |
| Porta | `LUFT_SERVIDOR_PORTA` | `PORT` | `8000` |
| Prefixo de URL | `LUFT_SERVIDOR_PREFIXO` | `ROUTE_PREFIX` | vazio (ex.: `/Luft-ConnectAir`) |
| Threads | `LUFT_SERVIDOR_THREADS` | - | `8` |
| Proxy confiavel | `LUFT_PROXY_CONFIAVEL` | - | `127.0.0.1` (`desligado` desativa) |

O servidor de desenvolvimento ignora o prefixo: ele responde na raiz.

## Prefixo (`ROUTE_PREFIX`)

Varios sistemas dividem o mesmo dominio. O nginx envia cada prefixo para uma porta:

```text
/                     -> Luft-Workspace   (porta 8000)
/Luft-ConnectAir/     -> Luft-ConnectAir  (porta 9003)
/Luft-Integrador/     -> Luft-Integrador  (porta 9005)
```

A aplicacao e publicada **sob o prefixo** (`SCRIPT_NAME`). Para isso:

- links e formularios usam `request.script_root`, nunca caminho fixo (um bug real: o `action` do formulario de login usava
  so `request.path` e mandava o login para `/login` na raiz; corrigido na 0.1.0a65);
- os estaticos da aplicacao ficam em `/Static` sob o prefixo;
- o cookie de sessao tem caminho `/` e nome unico, para valer em todos os sistemas.

## IP real do usuario atras do nginx

O Waitress 3 **apaga os cabecalhos `X-Forwarded-*`** quando nenhum proxy e declarado confiavel. Sem isso a aplicacao
via sempre `127.0.0.1`. O LuftBase passa ao Waitress:

```python
trusted_proxy="127.0.0.1", trusted_proxy_count=1,
trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host", "x-forwarded-port"},
clear_untrusted_proxy_headers=True
```

Regras importantes:

- so vale o IP **que o proprio nginx acrescentou** (o ultimo item do `X-Forwarded-For`). O primeiro item pode ter sido
  forjado pelo cliente e e ignorado (`proxy_add_x_forwarded_for` produz `"o que o cliente mandou, IP visto pelo nginx"`);
- depois disso `request.remote_addr` ja traz o IP real; por isso o codigo nunca le `X-Forwarded-For` direto;
- se o nginx esta em outra maquina, informe o IP dele em `LUFT_PROXY_CONFIAVEL`; sem nginx (acesso direto), use `desligado`;
- o nginx precisa enviar `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` e `X-Forwarded-Proto`.

Quando a aplicacao enxerga `127.0.0.1`, no Ao vivo da auditoria o IP aparece como "servidor local": e a propria maquina
(ou alguem testando no servidor), nao um endereco de usuario.

## Cookies e HTTP

- Em producao o cookie de sessao e `Secure`. Se o site ainda e servido em **HTTP**, o navegador descarta o cookie e todo POST
  falha com 403 (CSRF). A saida explicita e temporaria e `LUFT_PERMITIR_COOKIE_INSEGURO=true`; o LuftBase registra um aviso
  e `LUFT_SESSAO_COOKIE_SEGURO=true` ainda prevalece.
- `SameSite` padrao `Lax`. Nome (`luft_sessao`), caminho (`/`) e dominio sao configuraveis (`LUFT_SESSAO_COOKIE_*`).

## Fuso horario unico (Brasilia)

Servidores Windows usam o horario local e os Linux costumam rodar em UTC. `datetime.now()` devolve o horario **da maquina**,
entao o mesmo codigo gravava 14:55 num e 17:55 no outro. Solucao em tres camadas (`nucleo/tempo.py`):

1. `agora_local()` devolve o horario de `America/Sao_Paulo` (sem `tzinfo`, formato das colunas `timestamp`). Todo o LuftBase
   que grava ou mostra horario usa essa funcao.
2. `aplicar_fuso_do_processo()` poe o **processo** no mesmo fuso (`TZ` + `time.tzset()` no Linux), para o codigo das
   aplicacoes e os `%(asctime)s` dos logs concordarem. No Windows nada e alterado (o runtime C
   le `TZ=America/Sao_Paulo` como UTC, o que adiantava os logs em 3 h ate a 0.1.0a89). Se o sistema nao tem o pacote
   `tzdata`, o LuftBase avisa no log e os horarios gravados continuam corretos.
3. Os logs do LuftBase (arquivo fisico e console) usam `FormatadorDeLog`, cujo `%(asctime)s` e sempre o horario da
   plataforma, qualquer que seja o fuso da maquina; `de_timestamp()` converte epochs (ex.: data do arquivo). Logs
   proprios das aplicacoes devem usar `FormatadorDeLog` em vez de `logging.Formatter`.
4. Cada conexao PostgreSQL abre com `options=-c timezone=<fuso>`, entao `CURRENT_TIMESTAMP` e os defaults do banco tambem
   saem em Brasilia.

`LUFT_FUSO_HORARIO` troca o fuso (padrao `America/Sao_Paulo`). Registros gravados **antes** da 0.1.0a70 no Linux ficaram com
3 horas a mais; nao sao corrigidos automaticamente (use `LUFT_AUDITORIA_DADOS_DESDE` para as analises, veja o doc 15).

## Banco SQL Server e driver ODBC

O LuftBase pede `ODBC Driver 18 for SQL Server`. Se ele nao existir na maquina (erro `IM002`), `resolver_driver_odbc` escolhe
o melhor instalado, na ordem: 18, 17, 13, 11, `SQL Server Native Client 11.0`, `SQL Server` (legado, ultimo recurso: nao entende
os parametros de TLS modernos, que sao omitidos). O driver escolhido aparece no log.

Conexoes ao ERP sao **somente leitura** e usam a conexao nomeada do Vault (`SQLSERVER_CONEXAO`, padrao `consulta`).

## Pool de conexoes PostgreSQL

Cada fronteira (core e aplicacao) tem pool com `pool_pre_ping` (testa a conexao antes de usar), tamanho, reciclagem e timeout
configurados em `infraestrutura/banco`. Uma conexao ociosa e fechada pelo vigia; o ultimo teste intermitente desse vigia
foi estabilizado na 0.1.0a62.
