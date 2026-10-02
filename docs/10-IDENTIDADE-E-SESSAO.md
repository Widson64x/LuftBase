# Identidade e sessao

## Separacao de responsabilidades

```text
LDAP seguro -> valida a credencial
SQL Server  -> localiza usuario e grupo, somente leitura
Dominio     -> cria UsuarioAutenticado desacoplado do ORM
Redis       -> mantem a sessao compartilhada e revogavel
Cookie      -> transporta somente um identificador aleatorio assinado
```

O modelo ORM nao herda `UserMixin`, nao carrega permissao e nunca e guardado na sessao. O
retrato `UsuarioAutenticado` possui apenas dados necessarios e um conjunto imutavel de
permissoes, que sera preenchido pelo M05.

## Diretorio

`UsuarioDiretorio` e `GrupoDiretorio` preservam os nomes fisicos do Luftinforma, mas oferecem
atributos Python em portugues. Eles pertencem a `BaseDiretorio`, nunca a `BaseLuft`, portanto
Alembic jamais tenta criar ou alterar tabelas no SQL Server.

O repositorio aceita somente `bancos.diretorio`, que e marcado como leitura. A role SQL Server
com privilegio apenas `SELECT` continua sendo a barreira definitiva.

## LDAP

O adaptador aceita dois transportes:

- `ldaps`, porta padrao 636;
- `starttls`, porta padrao 389, promovida para TLS antes do bind.

LDAP simples em texto puro nao e representavel na configuracao. Credencial invalida retorna
falso; indisponibilidade gera erro controlado sem ecoar servidor, login ou senha.

## Sessao compartilhada

A interface implementada usa JSON UTF-8, nunca `pickle`. O Redis recebe um envelope versionado
e com TTL. O navegador recebe apenas um ID aleatorio assinado com `TimestampSigner` e SHA-256.
Uma assinatura adulterada ou uma chave expirada inicia sessao anonima.

`iniciar_sessao_usuario()` rotaciona o identificador depois do login, grava o retrato e
integra Flask-Login. `encerrar_sessao_global()` remove a chave Redis e limpa a identidade;
assim, o mesmo cookie deixa de funcionar em todas as aplicacoes que compartilham o Redis.

O `user_loader` restaura `UsuarioAutenticado` diretamente do JSON da sessao. Ele nao consulta
SQL Server nem PostgreSQL por requisicao. O diretorio e consultado uma vez depois que o LDAP
aceita a credencial.

```python
from flask import redirect, request
from luftbase import obter_luftbase
from luftbase.identidade import iniciar_sessao_usuario


def entrar():
    usuario = obter_luftbase().autenticacao.autenticar(
        request.form["login"],
        request.form["senha"],
    )
    if usuario is None:
        return {"erro": "Credencial invalida."}, 401
    iniciar_sessao_usuario(usuario)
    return redirect("/")
```

## Estado da integracao

`PlataformaLuft.inicializar()` instala Redis, politica de cookie e Flask-Login. O health check
inclui `sessoes_redis`. Um teste com duas aplicacoes confirma compartilhamento e revogacao sem
rede real. Permissoes permanecem vazias ate o M05, que implementara autorizacao sob demanda.
