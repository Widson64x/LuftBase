# Visao do produto

O LuftBase e a plataforma de desenvolvimento das aplicacoes Python da Luft. Seu objetivo e
oferecer uma experiencia equivalente a um framework corporativo: convencoes fortes, uma API
pequena e extensoes internas consistentes.

## Responsabilidade do LuftBase

- configuracao e ambientes;
- integracao com Vault;
- conexoes e ciclo de vida de sessoes;
- identidade corporativa e SSO;
- autorizacao baseada em permissoes;
- auditoria e observabilidade;
- notificacoes e publicacoes;
- layout, componentes, temas e acessibilidade;
- health checks e diagnostico;
- CLI e criacao de projetos.

## Responsabilidade das aplicacoes

- regras de negocio;
- modelos e repositorios do proprio dominio;
- rotas especificas;
- telas especificas;
- integracoes que nao sejam corporativas.

## Principio de experiencia do desenvolvedor

Uma aplicacao web deve inicializar o LuftBase uma vez. Configuracoes que sao iguais em todas
as aplicacoes nao devem aparecer como argumentos repetidos. Pontos de extensao existem para
necessidades reais, nao para permitir que cada projeto desmonte o padrao corporativo.

