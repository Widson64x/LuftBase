"""Nota de atualização global: a plataforma Luft passou a rodar no LuftBase.

O texto usa o markdown seguro de `markdown_seguro` (imagens `luftbase:` ficam em
`interface/static/img/changelog`). `publicar_changelog_plataforma` cria a nota como GLOBAL (sistema 0),
com notificação, e é idempotente: repetir não duplica.
"""

from __future__ import annotations

from dataclasses import dataclass

from luftbase.conteudo.modelos import (
    NovaPublicacao,
    PrioridadePublicacao,
    TipoAudiencia,
    TipoPublicacao,
)
from luftbase.conteudo.servicos import ServicoPublicacoes

TITULO = "Nova plataforma Luft: o ecossistema agora roda no LuftBase"
RESUMO = (
    "Todos os sistemas Luft passaram para uma base única e mais segura: login único, permissões "
    "mais claras, perfil renovado e um painel de controle completo. Veja o que muda para você."
)

CONTEUDO = """\
![O ecossistema Luft ganhou uma nova base](luftbase:img/changelog/banner-plataforma.svg)

:::sucesso
**Tudo certo por aqui!** Os sistemas Luft passaram por uma grande atualização: trocamos o framework
que sustenta o Workspace, o ConnectAir e o Integrador por uma base nova, única e compartilhada, o **LuftBase**.
:::

## Por que mudamos

Cada sistema tinha a sua própria forma de cuidar de login, permissões e avisos. Agora todos usam **o mesmo
núcleo**: o que melhora em um sistema melhora em todos, e a segurança passa a ser tratada num lugar só.

:::cards
### Login único
Entre uma vez e navegue entre Workspace, ConnectAir e Integrador sem digitar a senha de novo.
### Permissões mais claras
Cada acesso tem nome e dono, no formato módulo, recurso e ação. Fica fácil saber quem pode o quê.
### Painel de controle
Integrações, serviços do servidor, versões e configurações reunidos em um só lugar.
### Perfil renovado
Foto com recorte, dispositivos conectados e histórico dos seus últimos acessos.
### Avisos e notas
Comunicados e notas de atualização com notificação, como esta que você está lendo.
### Horário de Brasília
Todos os registros usam o mesmo relógio, em qualquer servidor.
:::

## Entre uma vez, use em tudo

![Um login para tudo](luftbase:img/changelog/acesso-unico.svg)

Ao entrar em qualquer sistema, você já está autenticado nos outros. Ao sair, a sessão é encerrada em todos,
e sua conta mostra **online** apenas enquanto você está de fato conectado.

## Seu perfil, do seu jeito

![Perfil e sessões](luftbase:img/changelog/perfil-sessoes.svg)

- Clique na câmera sobre a sua foto para **ajustar o recorte**, dar zoom, girar ou remover.
- Na aba **Sessões & Segurança** veja onde você está conectado, com **navegador, sistema e IP** de cada acesso.
- Use **Desconectar outras sessões** se esqueceu a conta aberta em outro computador.
- O **histórico de acessos** mostra os 5 últimos acessos, com início, fim e motivo do encerramento.

## Para quem administra

![Painel de controle](luftbase:img/changelog/painel-integracoes.svg)

- **Integrações:** estado do cofre de senhas, banco e e-mail, com a versão do LuftBase de cada sistema.
- **Serviços do servidor:** veja e reinicie o serviço de cada sistema, sem acesso ao servidor.
- **Segurança:** copie as permissões de um usuário para outro e acompanhe tudo pela auditoria.
- **Integrador:** os parâmetros da Reintegração WMS e do Ecobox saíram da planilha e agora são editados na tela
  de **Parâmetros**, com senhas protegidas.

:::alerta
**O que muda para você:** talvez seja preciso entrar novamente uma vez. As permissões foram reorganizadas;
se algum menu ou ação que você usava não aparecer, avise o seu gestor ou o TI para liberar o acesso.
:::

## E agora?

Navegue como de costume. Se encontrar algo estranho, abra um chamado para o **TI** com o que você estava
fazendo e a hora aproximada: com a nova base, conseguimos achar a causa muito mais rápido.

> Obrigado por usar os sistemas Luft. Esta é só a primeira de muitas melhorias que vêm por aí.
"""


@dataclass(frozen=True, slots=True)
class ResultadoChangelog:
    """O que `publicar_changelog_plataforma` fez."""

    id_publicacao: int
    acao: str  # "criada" | "atualizada" | "ja_publicada"
    publicada: bool


def nova_publicacao(*, versao: str, notificar: bool = True, criado_por: str = "Equipe Luft") -> NovaPublicacao:
    return NovaPublicacao(
        titulo=TITULO,
        resumo=RESUMO,
        conteudo=CONTEUDO,
        criado_por=criado_por,
        tipo=TipoPublicacao.ATUALIZACAO,
        audiencia=TipoAudiencia.GERAL,
        prioridade=PrioridadePublicacao.ALTA,
        versao=versao,
        notificar=notificar,
        fixado=True,
    )


def publicar_changelog_plataforma(
    servico: ServicoPublicacoes,
    *,
    versao: str,
    notificar: bool = True,
    publicar: bool = True,
) -> ResultadoChangelog:
    """Cria (ou atualiza o rascunho de) a nota e a publica; nunca duplica uma já publicada."""

    dados = nova_publicacao(versao=versao, notificar=notificar)
    existente = next(
        (
            p
            for p in servico.listar_administracao(tipo=TipoPublicacao.ATUALIZACAO, limite=100)
            if p.titulo == TITULO and p.status_publicacao != "ARQUIVADO"
        ),
        None,
    )
    if existente is not None and existente.status_publicacao == "PUBLICADO":
        return ResultadoChangelog(existente.id_publicacao, "ja_publicada", True)

    if existente is not None:
        servico.atualizar_rascunho(existente.id_publicacao, dados)
        id_publicacao, acao = existente.id_publicacao, "atualizada"
    else:
        id_publicacao, acao = servico.criar_rascunho(dados), "criada"

    if publicar:
        servico.publicar(id_publicacao)
    return ResultadoChangelog(id_publicacao, acao, publicar)


__all__ = [
    "CONTEUDO",
    "RESUMO",
    "TITULO",
    "ResultadoChangelog",
    "nova_publicacao",
    "publicar_changelog_plataforma",
]
