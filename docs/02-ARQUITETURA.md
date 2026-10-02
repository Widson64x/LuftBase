# Arquitetura

## Fluxo principal

```text
Aplicacao Flask
    -> PlataformaLuft
        -> Configuracao validada
        -> Vault
        -> SQL Server do diretorio
        -> PostgreSQL luft_web
            -> schema core
            -> schema da aplicacao
        -> Redis de sessao e cache
        -> modulos corporativos
        -> design system
```

## Limites

- SQL Server e PostgreSQL usam sessoes distintas.
- O SQL Server corporativo e somente leitura para o LuftBase.
- O schema `core` e propriedade da plataforma.
- O schema particular e informado pelo segredo PostgreSQL da aplicacao.
- Redis armazena estado efemero; PostgreSQL continua sendo a fonte definitiva.
- Migrations nunca sao executadas automaticamente no startup.

## Organizacao

O nucleo contem contratos sem Flask ou SQLAlchemy. A infraestrutura implementa esses
contratos. Os modulos verticais concentram regras de identidade, autorizacao, auditoria,
notificacoes e publicacoes. A camada web registra rotas, templates e assets.

## Estado por aplicacao

Uma instancia de `PlataformaLuft` pode ser usada no padrao application factory. Todo estado
dependente do Flask fica em `app.extensions["luftbase"]`; nao existe singleton mutavel global.
A fabrica de infraestrutura e injetavel para testes, enquanto a API normal permanece apenas
`PlataformaLuft().inicializar(app)`.

A importacao nao chama Vault, SQL Server ou PostgreSQL. A composicao ocorre na inicializacao
explicita e falha de forma visivel caso configuracao, token, payload ou conexao estejam
invalidos. Nao existe fallback silencioso para credencial, schema ou banco alternativo.
