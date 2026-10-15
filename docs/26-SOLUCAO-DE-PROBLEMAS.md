# Solucao de problemas

Procure pela **mensagem** que apareceu. Cada item traz a causa e o que fazer. Problemas de servidor, deploy e rede da aplicacao em
funcionamento estao na secao "Quando algo da errado" do [doc 20](20-OPERACAO-E-DEPLOY.md).

> **Antes de pedir ajuda**, junte: o comando exato, a saida completa e a versao (`python -m luftbase --version`). **Nunca** cole
> senha, token do Vault ou cookie. Os comandos do LuftBase nao imprimem segredos, entao a saida e segura para compartilhar.

## Indice

- [Instalacao e execucao](#instalacao-e-execucao)
- [Vault](#vault)
- [Criar projeto e sistema](#criar-projeto-e-sistema)
- [Espelho do banco](#espelho-do-banco)
- [Core desatualizado](#core-desatualizado)
- [Comparar estrutura](#comparar-estrutura)
- [Painel de Controle](#painel-de-controle)
- [Aplicacao nao sobe ou nao enxerga o banco](#aplicacao-nao-sobe-ou-nao-enxerga-o-banco)

---

## Instalacao e execucao

### `O termo 'luftbase' nao e reconhecido`
A pasta `Scripts` do Python nao esta no `PATH`. Use `python -m luftbase <comando>`, que funciona sempre, ou ative o ambiente
virtual (`.\.venv\Scripts\Activate.ps1`), que poe o executavel no `PATH`.

### `Error: Could not locate a Flask application`
Voce rodou um comando que **precisa da aplicacao** (`banco versao|atualizar|pendencias|validar|retencao`, `diagnostico saude`,
`alertas`, `estrutura`) fora de um projeto. Entre na pasta do projeto e use:

```powershell
flask --app App:CriarApp banco pendencias
```

Os comandos `projeto`, `sistema`, `banco espelhar|comparar|atualizar-core` e `vault postgresql` **nao** precisam disso
([referencia da CLI](23-REFERENCIA-DA-CLI.md#tres-tipos-de-comando)).

### `Aborted!` no meio de um pedido
Voce apertou Ctrl+C ou respondeu "n" a uma confirmacao. Nada foi gravado depois desse ponto. Rode o comando de novo.

---

## Vault

### `Nao foi possivel descobrir o banco do ambiente '<amb>' no Vault (sistemas/0: InvalidPath; conexoes/: ...)`
O comando le dois lugares: `sistemas/0` (para achar a conexao compartilhada) e, como alternativa, a pasta `conexoes/`. Falhou nos dois:

- o **token** nao tem permissao de leitura nesse caminho (ou esta expirado);
- o **segredo nao existe** nesse ambiente (veja o proximo item);
- a pasta `conexoes/` tem **mais de um** segredo, e o comando nao adivinha qual usar.

Saidas: use outro token, confira o caminho no Vault, ou informe o banco na mao com `--banco-host`, `--banco-porta` e `--banco-nome`.

### `SegredoNaoEncontrado: O segredo solicitado nao existe no caminho '.../sistemas/<id>'`
Uma aplicacao (ou o Workspace) subiu num ambiente em que **nao ha segredo do sistema** no Vault. Acontece depois de espelhar um banco,
de recriar um ambiente ou de alguem apagar o segredo. Veja no Vault se ele foi apagado (aba **Version History** do segredo; da para
desfazer a exclusao) e, se nao existir de fato:

| Situacao | Como criar |
|---|---|
| ambiente de desenvolvimento, depois de espelhar | `banco espelhar` cria o segredo de cada sistema do core copiado |
| sistema que ja existe no core, em qualquer ambiente | `vault postgresql reprovisionar-sistema --ambiente <amb> --sistema-id <id> --nome <nome> --esquema <schema>` (simula; `--executar` aplica) |
| sistema novo | `projeto novo` (desenvolvimento) ou o Painel de Controle |

### `O Vault ja tem 'sistemas/<id>'. Nada foi gravado`
Sobrou um segredo de um sistema que nao existe mais no core (por exemplo, depois de recriar o banco). Remova o segredo orfao e repita:

```powershell
python -m luftbase vault postgresql remover-sistemas --ambiente desenvolvimento --sistema-id <id>
```

Esse comando apaga so o segredo (todas as versoes); nao mexe em roles, schemas nem no core.

---

## Criar projeto e sistema

### `O diretorio '<pasta>' ja existe e nao esta vazio. Use --forcar`
A pasta foi criada por uma tentativa anterior. Com `--forcar` o comando **regrava os arquivos do esqueleto** (`App/__init__.py`,
`App/Catalogo.py`, `App/Conexoes.py`, `App.py`, `Wsgi.py`...) **e o `.env`** (que volta com os tokens em branco). Arquivos que o esqueleto nao
gera (suas rotas, modelos e servicos novos) nao sao apagados.

> **So use `--forcar` numa pasta em que voce ainda nao desenvolveu nada.** Se ja editou `App/Catalogo.py` ou outro arquivo do esqueleto,
> faca copia antes, ou use `projeto criar --forcar` em uma pasta temporaria e traga so o que precisa.

### `O core esta na revisao X e este LuftBase espera Y`
O banco do ambiente esta com o `core` desatualizado em relacao a este LuftBase (comum em banco copiado de homologacao).
Veja [core desatualizado](#core-desatualizado). Nada foi gravado.

### `column "integra_luftbase" of relation "tb_sistema" does not exist`
Mesma causa, em versoes que ainda nao faziam a checagem acima: o core nao tem as colunas novas. Rode `banco atualizar-core`
(desenvolvimento) ou aplique o script de `tools/sql/` (homologacao e producao).

### Falhou no meio de `projeto novo`
Nada fica gravado no banco nem no Vault (se o segredo chegou ao Vault e o core nao confirmou, ele e removido). A pasta ja existe: repita o
comando com `--forcar`.

---

## Espelho do banco

### `Ferramenta 'pg_dump' nao encontrada`
O Windows nao tem o cliente do PostgreSQL. Escolha uma:

- instale o PostgreSQL (traz `pg_dump` e `pg_restore`) e, se estiverem fora do `PATH`, use `--pg-bin "C:\Program Files\PostgreSQL\17\bin"`;
- se o seu banco local roda no **WSL/Docker**, instale o cliente la e use `--via-wsl`.

### `pg_dump/pg_restore nao encontrados no WSL`
`--via-wsl` roda no WSL **desta maquina** (a distribuicao padrao). Instale o cliente nela, pelo PowerShell:

```powershell
wsl.exe -e sudo apt install -y postgresql-client
```

> Instalar em **outro** terminal Linux (outra maquina, outra distribuicao) nao adianta: confira com `wsl.exe -e which pg_dump`.

### `Nao foi possivel conectar em localhost:5432 como '<usuario>': usuario ou senha recusados`
Falha no **banco local** (destino), antes de qualquer copia. O usuario precisa ser o administrador do seu PostgreSQL. Em container Docker
e o `POSTGRES_USER` (nem sempre `postgres`). Para descobrir **so o usuario**, sem imprimir a senha:

```powershell
wsl.exe -e docker inspect <container> --format "{{range .Config.Env}}{{println .}}{{end}}" | Select-String POSTGRES_USER
```

### `O PostgreSQL recusou o usuario ou a senha administrativa (<servidor>)` ou `password authentication failed`
Falha no banco de **homologacao** (origem). Os pedidos dizem de qual servidor e cada senha: use no pedido "Senha de ... em
`<servidor>`" a senha **do servidor mostrado**, nao a do seu banco local. O usuario precisa conseguir ler `pg_authid` (superusuario)
para copiar as roles.

### `O banco local '<nome>' ja existe. Use --recriar`
Proposital: o comando nao apaga nada sem pedir. Com `--recriar` ele **apaga o banco local** e copia de novo; pede para voce digitar o nome do
banco para confirmar. Se a confirmacao nao bater, ele responde `Confirmacao recusada; nada foi alterado.`

### `pg_restore falhou ... unrecognized configuration parameter "transaction_timeout"`
O `pg_dump` e mais novo que o servidor local e emite um parametro que o servidor antigo nao conhece. Nas versoes atuais isso vira apenas um
**aviso** (sem efeito nos dados). Se ainda falhar, atualize o LuftBase. Qualquer **outro** erro do `pg_restore` continua sendo falha.

### `Roles que ja existiam localmente mantiveram a senha local`
Informativo. Para proteger o seu acesso, o espelho **nao troca** a senha de uma role que ja existe no seu banco. Se voce queria a senha da
origem, rode de novo com `--sobrescrever-senhas`. Se voce **perdeu** o acesso a uma role porque uma versao anterior a trocou, entre com o
administrador do banco local e redefina: `ALTER ROLE <nome> PASSWORD '...'`.

### `Roles de desenvolvimento sem schema no banco copiado`
Informativo: existem roles `luft_<schema>_dev_app` locais cujo schema nao veio no dump (por exemplo, um sistema que so existia no seu banco
antigo). Nenhum acesso foi concedido a elas; se o sistema ainda existe, recadastre-o.

### `aviso=a conexao '<alias>' do Vault aponta para o banco '<X>', nao para '<Y>'`
O espelho foi criado em `<Y>`, mas o Vault de desenvolvimento manda as aplicacoes para `<X>`. Ajuste `nome_banco` no segredo da conexao ou use
`LUFT_BANCO_LOCAL_NOME` no `.env` ([doc 25](25-BANCO-LOCAL-E-PROMOCAO-DE-ESTRUTURA.md#depois-do-espelho-o-vault-de-desenvolvimento)).

---

## Core desatualizado

Sintomas: "o core esta na revisao X e este LuftBase espera Y", `column ... does not exist`, ou erros em telas novas do Painel.

| Ambiente | Correcao |
|---|---|
| Desenvolvimento (banco local) | `python -m luftbase banco atualizar-core` (use o administrador do banco **local**) |
| Homologacao e producao | aplicar o script de `tools/sql/` **e/ou** `flask --app App:CriarApp banco atualizar --confirmar ATUALIZAR_CORE` no Workspace; veja [doc 20](20-OPERACAO-E-DEPLOY.md) |

Para ver o que falta sem alterar nada: `flask --app App:CriarApp banco pendencias`.

---

## Comparar estrutura

### `A role '<role>' nao existe em <ambiente>: o script nao concede acesso`
O sistema ainda nao foi cadastrado no Painel do ambiente de destino, entao a role do sistema nao existe la. Cadastre o sistema (isso cria schema
e role), gere o SQL de novo e execute.

### O relatorio mostra `!` (revisao manual)
O script nao resolve sozinho: tipo, nulidade ou valor padrao diferentes, coluna `NOT NULL` nova sem padrao, tabela so no destino. Decida caso
a caso; o `.sql` gerado nao inclui essas mudancas de proposito.

### `O schema '<s>' nao existe em <origem>`
Confira o nome do schema (`--schema`) e o ambiente de origem. O schema do sistema e o `schema_aplicacao` dele no Painel.

### `permission denied` ao executar o `.sql`
O usuario nao e dono do schema ou das tabelas. Execute com o usuario dono (o administrativo de migracao do ambiente).

---

## Painel de Controle

### Ao salvar um sistema: erro em `ck_core_sistema_categoria`
O banco ainda nao aceita as categorias novas (`API`, `FERRAMENTA`, `RELATORIO`, `INTEGRACAO`). Aplique `tools/sql/20261015_tb_sistema_categorias.sql`
(depois do da `0016`) ou `banco atualizar`.

### Um cartao do catalogo de icones aparece vazio
O nome do icone nao existe na biblioteca Phosphor 2.1.2. O catalogo do LuftBase foi corrigido, mas um sistema que **gravou** um nome antigo
(`forklift`, `safe`, `server`, `gears`, `thumbs-up-bold`) continua com o icone vazio: edite o sistema e escolha outro.

### `Corrija os campos destacados antes de salvar` ao marcar download
`tipo_acesso = DOWNLOAD` exige `url_download`, e um sistema que **integra o LuftBase** so pode ser `WEB`. Desmarque a integracao ou informe a URL.

---

## Aplicacao nao sobe ou nao enxerga o banco

| Sintoma | Causa provavel | O que fazer |
|---|---|---|
| `LUFT_SISTEMA_ID e obrigatorio` | `.env` sem o ID | preencha com o ID **do ambiente em que o app roda** |
| `Os placeholders de token devem ser substituidos` | `.env` ainda com `<TOKEN_...>` | copie `LUFT_VAULT_TOKEN` e `LUFT_TOKEN_ACESSO` de um sistema do mesmo ambiente |
| `LUFT_BANCO_LOCAL_HOST nao pode ser usado em producao` | variavel de espelho no `.env` de producao | apague as linhas `LUFT_BANCO_LOCAL_*` |
| `LUFT_BANCO_LOCAL_HOST aceita somente localhost...` | host de outra maquina | o espelho so vale na propria maquina |
| o sistema sobe mas as telas nao mostram dados | a role do sistema nao tem acesso ao schema copiado | rode `banco espelhar` de novo (ele concede acesso as roles `*_dev_app`) ou `banco conceder-permissoes` |
| `Tabela ausente: modelo=... tabela=...` no log | modelo declarado sem a tabela no schema | gere o SQL com `banco comparar` ou crie com `estrutura criar` ([doc 05](05-BANCO-E-SCHEMAS.md)) |
| `GET /_luftbase/saude` com dependencia `indisponivel` | banco, Vault ou sessao fora do ar | veja `diagnostico saude` e a aba Integracoes do Painel |

Mais casos operacionais (cookie `Secure`, prefixo de URL, fuso, deploy, servicos) estao no [doc 20](20-OPERACAO-E-DEPLOY.md).
