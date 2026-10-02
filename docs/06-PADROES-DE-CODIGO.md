# Padroes de codigo

## Linguagem

A API e a implementacao usam portugues sem acentos nos identificadores. Nomes oficiais de
tecnologias nao sao traduzidos.

## Estilo

- PEP 8 e formatacao Ruff;
- PEP 257 nas APIs publicas;
- type hints obrigatorios;
- funcoes pequenas e coesas;
- objetos imutaveis para configuracao;
- protocolos nas fronteiras externas;
- composicao em vez de herancas vazias;
- excecoes de dominio em vez de `Exception` generica;
- nenhum `except: pass` em caminhos importantes;
- nenhum `**kwargs` em API publica estavel.

## Comentarios

Comentarios explicam por que uma decisao existe, quais invariantes protege ou qual risco
evita. Codigo autoexplicativo nao recebe narracao linha a linha.

## Testes

Cada correcao de defeito recebe um teste de regressao. Integracoes externas sao testadas por
contratos e adaptadores. Modulos criticos de seguranca, sessao, Vault e banco exigem cobertura
de caminhos de erro, nao somente do fluxo feliz.

