# Logos da aba Integracoes

Os SVGs monocromaticos (`vault`, `postgresql`, `microsoftsqlserver`, `redis`, `gmail`, `microsoft`, `python`) vem do
projeto **Simple Icons** (https://simpleicons.org, licenca CC0 1.0 para os arquivos). Os nomes e as marcas
representados pertencem aos respectivos donos (HashiCorp, PostgreSQL Community, Microsoft, Redis, Google, Python Software
Foundation); aqui sao usados apenas para identificar a ferramenta integrada, sem sugerir parceria ou endosso.

Cada SVG e pintado de branco sobre o cartao colorido por mascara CSS (`.integ-logo-mascara`), entao nao tem cor propria.

`luftbase.png` (512 px) e `luftbase-128.png` (128 px) sao o icone do LuftBase, recortado em circulo com fundo transparente.

Para trocar ou acrescentar um logo: coloque o SVG aqui (nome so com letras, numeros, `.`, `-` e `_`) e aponte `logo=` em
`integracoes/diagnostico.py` (`_cartao(..., logo="nome-sem-.svg")`). Sem logo, o cartao usa o icone padrao.
