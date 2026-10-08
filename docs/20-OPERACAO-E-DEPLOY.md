# Operacao e deploy

Como uma mudanca vai do computador de quem desenvolve ate homologacao e producao, e o que fazer quando algo da errado.

## Ambientes

| Ambiente | Servidor | Servico | Banco core | Branch |
|---|---|---|---|---|
| Desenvolvimento | maquina de quem desenvolve | `python App.py` | `luft_web` (ou o que o `.env` apontar) | qualquer |
| Homologacao | Linux | systemd `luft-<sistema>.service` | `luft_web_hml` | `homologacao` |
| Producao | Windows Server | NSSM (servico com o nome do sistema) | `luft_web` | `main` |

Cada ambiente tem o **seu** `.env`, os **seus** segredos no Vault (`luft/<ambiente>/...`), a **sua** role de banco
(`luft_<schema>_app` em producao; `luft_<schema>_hml_app` em homologacao) e a **sua** chave de cifra (derivada de
`LUFT_TOKEN_ACESSO`; senhas cifradas em um ambiente nao abrem em outro).

## Fluxo de uma mudanca

```text
LuftBase (main) --tag v0.1.0aNN--> requirements.txt de cada app (pin) --push homologacao--> deploy Linux
                                                                       --merge main------> deploy Windows
```

1. **Mudanca no LuftBase** (`Widson64x/LuftBase`, branch `main`):
   - rode a suite completa (`python -m pytest`); ela e o portao: so publique com tudo verde;
   - suba a versao em `pyproject.toml` **e** `src/luftbase/_versao.py` (devem ser iguais);
   - registre no `CHANGELOG.md`;
   - `git commit`, `git tag v0.1.0aNN` (no commit certo) e `git push origin main v0.1.0aNN`;
   - confira com `git ls-remote origin refs/tags/v0.1.0aNN`.
2. **Em cada aplicacao** (Workspace, ConnectAir, Integrador): troque o pin
   `luft-base @ git+https://github.com/Widson64x/LuftBase.git@v0.1.0aNN` no `requirements.txt` e faca push na branch
   `homologacao`. O deploy roda sozinho.
3. **Local**: `pip install -r requirements.txt` em cada projeto; `pip show luft-base` confirma a versao.
4. **Producao**: so por **merge `homologacao` -> `main`** (Pull Request). Producao so sobe o que passou por homologacao.

> O repositorio do LuftBase e **publico**, por isso o `pip` instala direto do GitHub sem credencial.

## Workflow de deploy (`.github/workflows/deploy.yml`)

O arquivo e **o mesmo em todos os sistemas**; mudam so o nome do servico, o caminho e o do runner.

### Producao (push em `main`, runner Windows)

1. Valida Python >= 3.11 e a existencia do NSSM.
2. Para o servico (`nssm stop <Servico>`) e espera parar.
3. **Espelha** o checkout em `C:\ProjetosPython\<Sistema>` com `scripts/DeployMirror.py`.
4. Cria o `.venv` se faltar e roda `pip install -r requirements.txt`.
5. Valida a sintaxe (`compileall`).
6. Inicia o servico e espera ficar `Running`; se falhar, tenta religar o servico anterior.
7. O log fica em `C:\GitHubRunners\<Sistema>\deploy-log.txt`.

`DeployMirror.py` torna a pasta de destino um espelho do repositorio (copia o que mudou por hash e **remove o que nao existe
mais**), preservando: `.git`, `.venv`, `.env`, `logs`, bancos locais e pastas de dados (`data/save`, `data/temp` no Workspace;
a pasta `data` inteira no Integrador). **Antes do primeiro deploy de um sistema, confira se ha arquivos so do servidor fora
dessa lista**: eles seriam apagados.

### Homologacao (push em `homologacao`, runner Linux)

1. Para `luft-<sistema>.service` (`sudo systemctl`).
2. `rsync` do checkout para `/home/suporte/Mirror_Python_80/ProjetosPython/<Sistema>` (sem `.git` e `.venv`).
3. Cria o `.venv`, `pip install -r requirements.txt`.
4. Inicia o servico e confere que ficou ativo; senao imprime o `systemctl status` e falha.

## Qualidade da tag, promocao e rollback

**CI do LuftBase** (`.github/workflows/ci.yml`, neste repositorio; os apps seguem so com o `deploy.yml`): a cada push na `main`,
em tags `v*` e em PR roda em **Windows e Linux** (Python 3.11 e 3.12) `ruff`, `pytest` e o build do wheel, e confere que a tag
e igual a versao do `pyproject.toml`. O `mypy` roda como informativo ate a divida de tipos zerar. **So publique a tag com a
matriz verde**: os apps instalam o LuftBase pela tag, entao tag ruim chega a todos no proximo deploy.

**Ordem de promocao**: a tag nova entra primeiro nos tres sistemas em homologacao (Workspace, ConnectAir, Integrador). O pin de
producao so muda depois de a homologacao validar; o CHANGELOG da versao diz qual app ja a validou.

**Rollback** (voltar uma versao):
1. No `requirements.txt` do app, volte `luft-base @ git+https://github.com/Widson64x/LuftBase.git@v<anterior>`.
2. Commit e push na `homologacao` (ou na `main`, em producao, so com pedido explicito); o deploy refaz o `.venv`.
3. **Nao desfaca migracao.** O codigo anterior roda sobre o schema novo porque as migracoes sao **aditivas**
   (`tests/test_migracoes_aditivas.py` barra `drop_*`, `rename_*` e `alter_column` em qualquer migracao nova). Colunas e tabelas
   novas ficam sem uso ate a versao voltar.
4. Confira `GET /_luftbase/saude` e a aba Integracoes (versao instalada).

Se uma migracao nova precisar mesmo remover ou endurecer algo, ela exige duas versoes: a primeira para de usar a coluna, a
segunda (em outra tag, depois de a primeira estar em todos os ambientes) a remove. A regra do teste so se aplica as migracoes
posteriores a `20260923_0013`.

**Carga** (`tools/carga.py`, so biblioteca padrao): roteiro de N usuarios simultaneos sobre rotas GET, com p50/p95/p99 e erros por
rota; sai com codigo 1 se o p95 ou a taxa de erro passam do limite. Rode **so em homologacao**:

```
python tools/carga.py --base https://<host>/<prefixo> --usuarios 100 --duracao 60     --rota /_luftbase/saude --rota /auditoria/api/visao-geral --cookie "<cookie de sessao de teste>"
```

Meta inicial: 100 usuarios simultaneos, p95 de ate 3000 ms e menos de 1% de erros; ajuste depois da primeira medicao real.

## Primeiro deploy de um sistema (checklist)

- [ ] Servico criado (NSSM ou systemd) com **o nome do sistema** do catalogo.
- [ ] `.env` do ambiente na pasta do servico, com `HOST`/`PORT` iguais aos do nginx.
- [ ] Runner do GitHub registrado para o repositorio.
- [ ] `scripts/DeployMirror.py` existe no repositorio (o workflow de producao falha sem ele).
- [ ] Linux: usuario do servico com sudo sem senha para `systemctl` dos servicos Luft (necessario tambem para o painel de servicos).
- [ ] Windows: ODBC Driver instalado (o LuftBase usa o melhor disponivel e registra qual).

## Operacao do dia a dia

| Preciso... | Faca |
|---|---|
| ver o estado dos servicos / reiniciar | Painel de Controle > Aplicacoes & Ambiente > Servicos |
| trocar um parametro simples (`.env`) | Painel de Controle > Variaveis, depois reiniciar o servico |
| saber se o LuftBase esta atualizado | Painel de Controle > Integracoes (compara com o GitHub) |
| ver quem esta online / derrubar uma sessao | Auditoria > Ao vivo ([doc 15](15-AUDITORIA-ANALITICA-E-CONTROLE-DE-SESSOES.md)) |
| conferir saude | `GET /_luftbase/saude` (dependencias) e `/_luftbase/prontidao` |
| ver o que aconteceu num erro | `Logs/luftbase.log` e Auditoria > Registros (o 500 registra so tipos e linhas, nunca valores) |
| diagnosticar configuracao | `luftbase diagnostico configuracao` e `luftbase diagnostico saude` |

## Banco: migracoes e manutencao

- O core evolui por **Alembic** embutido no pacote: `luftbase banco versao`, `validar`, `pendencias`, `historico`, `atualizar`.
  Em um banco ja existente use `registrar-base` uma vez.
- **Aditivo sempre**: o catalogo de permissoes e sincronizado sem apagar nada; migracoes novas nao removem dados.
- Provisionamento de schemas, roles e senhas: `luftbase vault postgresql ...` ([doc 19](19-GUIA-DA-APLICACAO-SATELITE.md)).
- SQL manual de apoio (ex.: limpar sessoes antigas, ajustar permissoes provisorias) fica em `scripts/` do Workspace; todos
  mostram primeiro um bloco de **conferir** e rodam em transacao com `COMMIT`/`ROLLBACK`.

## Quando algo da errado

| Sintoma | Causa provavel | O que fazer |
|---|---|---|
| Todo POST dá 403 e o login nao entra | cookie `Secure` em site HTTP | `LUFT_PERMITIR_COOKIE_INSEGURO=true` (temporario) ou servir por HTTPS |
| Login vai para `/login` na raiz | codigo sem `script_root` | usar `request.script_root` / `url_for` |
| Erro `IM002` no SQL Server | driver ODBC pedido nao instalado | o LuftBase escolhe outro; veja qual no log (atualize a versao) |
| IP sempre 127.0.0.1 | proxy nao confiavel | `LUFT_PROXY_CONFIAVEL` (doc 17) |
| Horario 3 h adiantado no Linux | fuso do processo | versao >= 0.1.0a70; registros antigos nao se corrigem sozinhos |
| Pessoa continua "online" depois de sair | sessao fantasma (versoes < 0.1.0a69) | atualizar; limpar com `scripts/limpar_sessoes_antigas.sql` |
| Deploy de producao falha em `DeployMirror.py` | arquivo ausente no repositorio | copiar de um sistema irmao |
| Servico nao inicia apos deploy | `.env` ausente ou porta diferente do nginx | conferir o `.env` e o log do servico |
| `PermissionError` em `Logs\session.log` ao rodar `Wsgi.py` a mao | outro processo/conta ja usa o log | pare o servico antes de testar a mao |

## Seguranca operacional

- Segredos so no Vault; `.env` nunca vai para o Git.
- Nada de senha em log, auditoria ou resposta (os logs de erro guardam so tipos e linhas da pilha).
- Producao so recebe o que passou por homologacao.
- Toda acao administrativa (permissoes, servicos, sessoes, parametros) deixa rastro na auditoria.
