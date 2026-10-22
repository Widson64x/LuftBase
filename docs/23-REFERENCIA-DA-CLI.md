# Referencia da CLI

Todos os comandos do LuftBase, o que cada um faz, quando usar e o que ele **nunca** faz. O texto foi conferido contra o proprio
codigo; para a lista exata de opcoes de qualquer comando use `--help` (`python -m luftbase <grupo> <comando> --help`).

## Como executar

| Forma | Quando |
|---|---|
| `python -m luftbase <comando>` | sempre funciona; nao depende do `PATH` |
| `luftbase <comando>` | se a pasta `Scripts` do Python esta no `PATH` |
| `flask --app App:CriarApp <grupo> <comando>` | **dentro de um projeto**, para os comandos que precisam da aplicacao (veja abaixo) |

### Tres tipos de comando

| Tipo | O que precisa | Quais sao |
|---|---|---|
| **Autonomo** | nada: pergunta o que precisa no terminal; roda de **qualquer pasta** | `projeto`, `sistema`, `banco espelhar`, `banco comparar`, `banco atualizar-core`, `bootstrap`, `conceder-permissoes`, `vault postgresql ...`, `tema` |
| **Le o `.env`** | um `.env` na **pasta atual** (sem subir a aplicacao Flask) | `diagnostico configuracao`, `email testar`, `catalogo sincronizar`, `vault caminhos`, `vault verificar` |
| **Da aplicacao** | a aplicacao Flask: rode **na pasta do projeto** com `flask --app App:CriarApp` | `banco versao`, `historico`, `pendencias`, `validar`, `atualizar`, `registrar-base`, `tamanho-logs`, `retencao`; `diagnostico saude`; `alertas ...`; `estrutura ...` |

Se aparecer `Could not locate a Flask application`, voce rodou um comando "da aplicacao" fora de um projeto: entre na pasta do
projeto e use `flask --app App:CriarApp ...`.

### Como os comandos tratam segredos

- Token do Vault, senha de banco e afins sao **pedidos no terminal, sem eco**. Nunca por argumento de linha de comando, nunca em log.
- O **endereco do banco** de cada ambiente e descoberto no Vault; voce so informa usuario e senha.
- Comandos que gravam **mostram o destino** antes e pedem confirmacao (`--sim` pula a pergunta; nao use em ambiente compartilhado).
- Nenhum comando acima altera o **SQL Server**: ele e somente leitura para o LuftBase.

### Quem pode operar em qual ambiente

| Comando | desenvolvimento | homologacao | producao |
|---|---|---|---|
| `projeto novo`, `sistema externo` | sim | sim | **nao** (cadastre pelo Workspace) |
| `banco atualizar-core` | sim | nao (evolui pelo Workspace) | nao |
| `banco espelhar` | destino (sempre local) | origem | **nunca** |
| `banco comparar` | origem | origem ou destino | **so como destino** (le o catalogo e gera um arquivo) |

---

## Criar projetos e sistemas

### `projeto novo`
Cria um projeto **completo**: pasta no padrao Luft, sistema, schema, role, segredo no Vault e `.env`.

```powershell
python -m luftbase projeto novo Luft-Faturas --destino C:\Projetos\LUFT\Python\Luft-Faturas
```

| Opcao | Para que serve | Padrao |
|---|---|---|
| `NOME` | nome do sistema (se omitido, e perguntado) | - |
| `--ambiente` | `desenvolvimento` ou `homologacao` (producao e recusada) | `desenvolvimento` |
| `--destino` | onde criar a pasta | `./NOME` |
| `--schema` | schema do sistema | derivado do nome |
| `--porta` | porta HTTP local | `9000` |
| `--categoria` | tipo do sistema (veja [doc 24](24-SISTEMAS-E-CATALOGO.md)) | `APLICACAO` |
| `--descricao`, `--icone`, `--cor` | dados do card | icone `ph-bold ph-app-window`, cor `#2563eb` |
| `--grupo-acesso` | grupo que recebe a permissao de acesso | `6` (TI) |
| `--sistema-id` | ID manual (raro) | gerado pelo banco |
| `--env-referencia` | `.env` de outro sistema do mesmo ambiente; copia Vault, LDAP e sessao (nunca o ID) | - |
| `--usuario-banco` | usuario administrativo do banco | perguntado |
| `--banco-host/-porta/-nome` | sobrepoe o banco descoberto no Vault | - |
| `--somente-estrutura` | so a pasta; nao toca em banco nem Vault | desligado |
| `--forcar` | sobrescreve a pasta se ja existir | desligado |
| `--sim` | nao pede confirmacao | desligado |
| `--vault-url/-mount/-namespace` | onde fica o Vault | URL padrao da Luft, `secret`, `luft` |

**Antes de gravar**, confere se o core esta na revisao deste LuftBase; se nao estiver, para e manda rodar `banco atualizar-core`.
**Falhou no meio?** Nada fica gravado no banco nem no Vault; so a pasta ja foi criada (use `--forcar` ao repetir). O `--forcar`
**regrava os arquivos do esqueleto e o `.env`**: so use numa pasta em que ainda nao ha trabalho seu.

### `projeto criar`
Gera **so** os arquivos (mesma estrutura do `projeto novo`), sem Vault e sem banco. Util para quem ja tem o `LUFT_SISTEMA_ID`
(`--sistema-id`) ou vai cadastrar o sistema depois.

### `projeto deploy`
Gera artefatos **revisaveis** de deploy: `nginx.conf` (com suporte a eventos em tempo real), `nssm.ps1` (servico Windows) e um
README. Nao executa nada no servidor.

```powershell
python -m luftbase projeto deploy luft-faturas --nome "Luft Faturas" --destino deploy
```

### `sistema externo`
Cadastra uma **ferramenta que nao integra o LuftBase** (C#, executavel, sistema de terceiros): card e link, **sem** schema, role
nem segredo.

```powershell
python -m luftbase sistema externo Luft-Informa --tipo-acesso download --url-download /Luft-Workspace/atualizador
python -m luftbase sistema externo Portal.WebApp --tipo-acesso web --link https://portal.exemplo.com.br
```

| Opcao | Para que serve |
|---|---|
| `--tipo-acesso` | `web` abre o `--link`; `download` leva ao `--url-download`; `sem-acesso` so aparece no catalogo |
| `--link`, `--url-download` | destino do card |
| `--categoria`, `--descricao`, `--icone`, `--cor` | aparencia no catalogo |
| `--responsavel`, `--contato-suporte` | quem cuida e como pedir ajuda |
| `--grupo-acesso` | grupo que recebe a permissao de **ver o card** (padrao `6`) |
| `--ambiente` | `desenvolvimento` (padrao) ou `homologacao` |

O card aparece so para quem tem a permissao base do sistema; o LuftBase **nao** controla o login nem o banco da ferramenta.

---

## Banco local, comparacao e core

Veja o passo a passo e os cuidados em [banco local e promocao de estrutura](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md).

### `banco espelhar`
Copia o banco de **homologacao** para um PostgreSQL **na sua maquina** (somente leitura na origem). A copia e integral: leva
usuarios, sessoes e logs. Depois da copia, cria no Vault de **desenvolvimento** um segredo por sistema do core copiado.

```powershell
python -m luftbase banco espelhar --via-wsl --usuario-destino admin
python -m luftbase banco espelhar --somente-estrutura --recriar --usuario-destino admin   # banco limpo
```

| Opcao | Para que serve | Padrao |
|---|---|---|
| `--origem` | ambiente de onde copiar (`homologacao` ou `desenvolvimento`; producao e recusada) | `homologacao` |
| `--usuario-banco` | usuario administrativo **da origem** | perguntado |
| `--destino-host/-porta/-banco` | onde gravar; **so a propria maquina** (`localhost`, `127.0.0.1`, `::1`) | `localhost`, `5432`, nome da origem com `_dev` no lugar de `_hml` |
| `--usuario-destino` | usuario administrativo **do PostgreSQL local** | `postgres` |
| `--recriar` | apaga o banco local se existir (pede para digitar o nome) | desligado |
| `--somente-estrutura` | sem nenhum dado | desligado |
| `--via-wsl` | roda `pg_dump`/`pg_restore` dentro do WSL (instale `postgresql-client` la) | desligado |
| `--pg-bin` | pasta `bin` do PostgreSQL com `pg_dump` e `pg_restore` | procura no `PATH` |
| `--sem-vault` | nao cria segredos no Vault de desenvolvimento | desligado |
| `--substituir-segredos` | troca segredos de desenvolvimento que apontam para outro schema ou role | desligado |
| `--sobrescrever-senhas` | troca a senha das roles que **ja existem** localmente pela da origem | desligado (mantem a local) |
| `--configurar-env` | `.env` de um projeto a apontar para o espelho (`LUFT_BANCO_LOCAL_*`) | imprime as linhas |

### `banco comparar`
Compara a **estrutura** dos schemas entre dois ambientes e gera o SQL para igualar o destino. So le o catalogo, nunca dados.

```powershell
python -m luftbase banco comparar --schema faturas --origem desenvolvimento --destino homologacao
python -m luftbase banco comparar --schema faturas --origem homologacao --destino producao
```

| Opcao | Para que serve | Padrao |
|---|---|---|
| `--origem` | `desenvolvimento` ou `homologacao` | `desenvolvimento` |
| `--destino` | `homologacao` ou `producao` | `homologacao` |
| `--schema` | schema a comparar; repita para varios | todos da origem, exceto o core |
| `--usuario-origem/--usuario-destino` | usuarios do PostgreSQL de cada lado | perguntados |
| `--saida` | pasta dos arquivos `.sql` | pasta atual |

Saida: uma linha por diferenca, marcada **`+`** (o script resolve) ou **`!`** (exige revisao manual), e um arquivo
`estrutura_<schema>_<origem>_para_<destino>.sql` por schema com diferencas.

### `banco atualizar-core`
Leva o core do **desenvolvimento** a revisao deste LuftBase, sem subir uma aplicacao (aplica as migrations pendentes e
sincroniza o catalogo do Workspace). So `--ambiente desenvolvimento`.

### Evolucao e inspecao do core (comandos da aplicacao)

| Comando | O que faz |
|---|---|
| `banco versao` | revisao instalada e revisao entregue pelo pacote |
| `banco pendencias` | lista revisoes pendentes **sem aplicar** |
| `banco historico` | todas as revisoes do pacote |
| `banco validar` | detecta divergencias sem alterar nada (`--baseline-migrada` compara so as 13 tabelas iniciais) |
| `banco atualizar --confirmar ATUALIZAR_CORE` | aplica as migrations pendentes; **nunca** e chamado na inicializacao |
| `banco registrar-base --confirmar ADOTAR_CORE_EXISTENTE` | adota a revisao inicial num banco que ja existia (uma vez) |
| `banco tamanho-logs` | linhas e MB das tabelas de log, e o registro mais antigo |
| `banco retencao` | politica de retencao de logs, sessoes e alertas (veja abaixo) |

`banco retencao` **simula por padrao**. Para apagar de verdade: `--executar` com `--arquivar-em <pasta>` (grava CSV compactado
antes de apagar) ou `--sem-arquivo` (nao recomendado); `--lote` define as linhas por commit (padrao 1000). Os prazos vem de
`LUFT_RETENCAO_*_DIAS` ([doc 18](18-VARIAVEIS-DE-AMBIENTE.md)).

### Provisionamento inicial de um ambiente

| Comando | O que faz |
|---|---|
| `bootstrap` (ou `banco bootstrap`) | assistente interativo: banco, roles, Vault e core de um ambiente. `--atualizar` so atualiza o core e o catalogo |
| `conceder-permissoes` (ou `banco conceder-permissoes`) | aplica permissoes completas nas tabelas dos schemas `core` e das aplicacoes |

---

## Vault

### `vault caminhos` e `vault verificar`
`caminhos` mostra os caminhos canonicos do ambiente atual. `verificar [--conectar]` confere a configuracao dos segredos **sem
exibir senhas ou tokens**; com `--conectar` testa a conectividade.

### `vault postgresql ...` (provisionamento oficial)

| Comando | O que faz | Observacao |
|---|---|---|
| `auditar` | audita PostgreSQL e Vault **sem alterar** | seguro; use `--manifesto` |
| `provisionar` | cria segredos (nunca sobrescreve: CAS 0) e define senhas SCRAM | pede confirmacao digitada |
| `aplicar-senhas-do-vault` | reaplica no PostgreSQL as senhas que estao no Vault | recupera uma role fora de sincronia |
| `migrar-layout-sistemas` | copia credenciais legadas para `sistemas/{id}` | nao apaga nem revela |
| `clonar-ambiente` | clona segredos e roles de um ambiente para outro, com roles proprias no destino | **simula por padrao**; `--executar` aplica |
| `reprovisionar-sistema` | recria schema, role **do ambiente** e segredo de um sistema ja cadastrado | **simula por padrao**; producao nunca e tocada |
| `remover-sistemas` | apaga os segredos `sistemas/{id}` (todas as versoes) | nao mexe em roles, schemas nem core; pede confirmacao |

---

## Operacao da aplicacao

| Comando | O que faz |
|---|---|
| `servir [ALVO]` | (na pasta do projeto) serve a aplicacao com o Waitress (`--host`, `--porta`, `--prefixo`, `--threads`; padroes vem de `LUFT_SERVIDOR_*`, `HOST`, `PORT`, `ROUTE_PREFIX`) |
| `diagnostico configuracao` | valida e mostra a configuracao **sem revelar segredos** |
| `diagnostico saude` | checagem de saude das dependencias, sem dados sensiveis |
| `alertas avaliar` | roda **um** ciclo do avaliador de alertas (agende a cada minuto) |
| `alertas listar [--todos] [--limite N]` | lista alertas abertos (ou todos) |
| `email testar --para voce@empresa` | envia o e-mail de teste pelo segredo `integracoes/email` do ambiente |
| `email fila [--situacao pendentes\|enviados\|falhas\|todos]` | mostra a fila de e-mails: contagens e os ultimos itens (sobe o app Flask) |
| `email processar [--lote 50]` | entrega agora o que esta na fila (para agendar quando nenhum servidor roda o envio) |

## Catalogo, estrutura e temas

| Comando | O que faz |
|---|---|
| `catalogo sincronizar --catalogo modulo:OBJETO` | grava sistema, modulos e permissoes no core, **de forma aditiva** (`--grupo-administrador`, `--usuario-banco`) |
| `estrutura verificar` | lista a existencia e a politica de cada model registrado |
| `estrutura criar MODELO --confirmar CRIAR_ESTRUTURA` | cria um model de politica `GERENCIAR` com credencial autorizada para DDL |
| `tema listar` | familias visuais registradas |
| `tema validar ARQUIVO [--modos claro,escuro]` | valida um arquivo de tokens CSS ou manifesto JSON |

---

## Receitas

| Preciso... | Comando |
|---|---|
| criar o sistema "Luft-X" completo | `projeto novo Luft-X --destino <pasta>` |
| cadastrar uma ferramenta externa (executavel) | `sistema externo <Nome> --tipo-acesso download --url-download <url>` |
| ter um banco local igual ao de homologacao | `banco espelhar --via-wsl --usuario-destino admin` |
| ter um banco local **limpo** | `banco espelhar --somente-estrutura --recriar --usuario-destino admin` |
| colocar o core local em dia | `banco atualizar-core` |
| criar em homologacao as tabelas que fiz | `banco comparar --schema <s> --destino homologacao` |
| saber se a plataforma esta saudavel | `diagnostico saude` |
| aplicar migracao no core de um ambiente | no projeto: `flask --app App:CriarApp banco atualizar --confirmar ATUALIZAR_CORE` |
| ver o que falta no core | no projeto: `flask --app App:CriarApp banco pendencias` |
