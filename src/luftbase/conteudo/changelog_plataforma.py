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

TITULO = "Uma base nova para os sistemas web Luft"
RESUMO = (
    "Os sistemas web da Luft estão ganhando uma base nova: login único, perfil renovado e avisos com "
    "notificação. Workspace, ConnectAir e Integrador já estão nela, e os demais, como o Luft-Control, virão a seguir."
)

# Titulos de versoes anteriores da mesma nota: a nota ja publicada e reconhecida e tem o texto corrigido.
TITULOS_ANTERIORES = (
    "Nova plataforma Luft: o ecossistema agora roda no LuftBase",
    "Uma base nova para os sistemas Luft: conheça o LuftBase",
)

_IMG = "luftbase:img/changelog/"

CONTEUDO = f"""\
![Uma base nova para os sistemas web Luft]({_IMG}banner.png)

:::sucesso
**Os sistemas web da Luft estão ganhando uma base nova.** O **Luft-Workspace**, o **Luft-ConnectAir** e o
**Luft-Integrador** já funcionam sobre ela, e os demais sistemas web, como o **Luft-Control**, seguirão o
mesmo caminho. O resultado é uma experiência mais simples, mais parecida entre os sistemas e mais segura.
:::

## O que muda para você

![O que muda, em um olhar]({_IMG}antes-depois.png)

- **Um login para tudo:** entre uma vez e use todos os sistemas web já adaptados.
- **Perfil renovado:** foto com recorte, dispositivos conectados e histórico dos seus acessos.
- **Avisos que chegam até você:** comunicados e notas de atualização, com notificação.
- **Busca e visual:** encontre telas rapidamente e escolha o tema que prefere.
- **Mesmo jeito de usar:** menus, perfil e avisos funcionam de forma igual em todos os sistemas.

---

## Quais sistemas já estão na nova base

![Quais sistemas já estão na nova base]({_IMG}linha-do-tempo.png)

A mudança está sendo feita **sistema por sistema**, sempre depois de testada. Hoje já estão adaptados o
Workspace, o ConnectAir e o Integrador. O **Luft-Control** será o próximo, e **todos os sistemas web da Luft**
vão seguir o mesmo padrão. Quando cada um for migrado, você será avisado por aqui.

---

## Entre uma vez, use em tudo

![Um login para tudo]({_IMG}login-unico.png)

Ao entrar em um dos sistemas adaptados, você já está autenticado nos outros. Vá de um sistema a outro pelo
menu, sem digitar a senha de novo. Quando você **sai**, a sessão é encerrada em todos eles.

![Tela de entrada]({_IMG}tela-login.png)

![Hub de Sistemas]({_IMG}tela-hub.png)

- O **Hub de Sistemas** mostra os sistemas a que você tem acesso.
- O caminho no topo mostra onde você está: a casinha leva ao Workspace, e o nome do sistema leva à página
  inicial dele.
- O estado **Online** só aparece enquanto você está de fato conectado.

---

## Seu perfil, do seu jeito

Clique no seu nome, no canto da tela, para abrir as **Configurações de Perfil**.

### Foto com recorte

![Editor de foto]({_IMG}tela-editor-foto.png)

Clique na câmera sobre o seu avatar para abrir o editor. **Arraste** a imagem para posicionar o rosto no
círculo, use o **zoom** e os botões de **girar** e **centralizar**. Aceita imagens PNG, JPEG e WebP de até
8 MB, e dá para soltar o arquivo direto na janela. **Remover foto** pede uma confirmação, para evitar
cliques sem querer.

### Sessões e segurança

![Sessões e histórico de acessos]({_IMG}tela-perfil-sessoes.png)

Na aba **Sessões & Segurança** você acompanha a sua conta:

- **Dispositivos conectados:** cada sessão mostra o navegador, o sistema e o IP. A que você está usando
  aparece como **Esta sessão**.
- **Desconectar outras sessões:** esqueceu a conta aberta em outro computador? Um clique encerra as outras.
- **Histórico de acessos:** os seus 5 últimos acessos, com início, fim e o motivo do encerramento.

:::alerta
**Viu um acesso que não reconhece?** Use **Desconectar outras sessões**, troque a sua senha e avise o TI.
:::

---

## Avisos, busca e visual

### Comunicados e notas de atualização

![Avisos que chegam até você]({_IMG}notificacoes-arte.png)

Comunicados e notas de atualização, como esta que você está lendo, chegam com **notificação** no sino do
topo. O ponto azul indica o que ainda não foi lido, e **Marcar todas como lidas** limpa a lista.

![Central de notificações]({_IMG}tela-notificacoes.png)

![Notas de Atualização]({_IMG}tela-notas.png)

Em **Notas de Atualização**, no menu, fica o histórico do que mudou, versão por versão.

### Busca global

![Busca global]({_IMG}tela-busca.png)

A barra de busca, no topo, encontra telas e funções nos sistemas a que você tem acesso. Digite parte do
nome e escolha o resultado.

### Escolha o seu visual

![Temas]({_IMG}tela-temas.png)

No botão **Modo** e na aba **Aparência & Tema** do perfil você escolhe entre o tema claro, o escuro e a
identidade ESG. A escolha fica salva na sua conta.

---

## O que você precisa fazer

1. **Entre normalmente.** Talvez seja pedido um novo login uma única vez.
2. **Confira os seus acessos.** Os acessos foram reorganizados nesta mudança. Se algum menu ou ação que
   você usava não aparecer, peça ao seu gestor ou ao TI para liberar, informando o sistema e a tela.
3. **Dê uma olhada no perfil.** Coloque a sua foto e veja os seus dispositivos conectados.

## Perguntas frequentes

**Preciso trocar a minha senha?**
Não. Use a mesma senha de sempre.

**Por que me pediram para entrar de novo?**
A sessão antiga foi criada antes da mudança. Depois do novo login, ela vale para todos os sistemas adaptados.

**Perdi um acesso que eu tinha. E agora?**
Peça ao seu gestor ou ao TI para liberar de novo, informando o sistema e a tela.

**O sistema que eu uso ainda não mudou. Vai mudar?**
Sim. Todos os sistemas web da Luft vão seguir o mesmo padrão, e o Luft-Control é o próximo. Você será avisado.

## Precisa de ajuda?

Abra um chamado para o **TI** informando o **sistema e a tela**, o **que você estava fazendo** e o **horário
aproximado**. Uma captura de tela ajuda bastante. Nunca envie a sua senha.

![Obrigado]({_IMG}encerramento.png)

> Obrigado por usar os sistemas Luft. Esta é a primeira de muitas melhorias, e a sua opinião ajuda a definir as próximas.
"""


@dataclass(frozen=True, slots=True)
class ResultadoChangelog:
    """O que `publicar_changelog_plataforma` fez."""

    id_publicacao: int
    acao: str  # "criada" | "atualizada" | "texto_corrigido" | "ja_publicada"
    publicada: bool
    arquivadas: int = 0  # copias antigas da mesma nota que foram arquivadas


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
    candidatas = sorted(
        (
            p
            for p in servico.listar_administracao(tipo=TipoPublicacao.ATUALIZACAO, limite=100)
            if p.titulo in (TITULO, *TITULOS_ANTERIORES) and p.status_publicacao != "ARQUIVADO"
        ),
        key=lambda p: p.id_publicacao,
        reverse=True,
    )
    existente = candidatas[0] if candidatas else None
    # Rodar o script mais de uma vez com textos diferentes pode ter deixado copias: fica a mais nova.
    arquivadas = sum(1 for copia in candidatas[1:] if servico.arquivar(copia.id_publicacao))

    if existente is not None and existente.status_publicacao == "PUBLICADO":
        # Ja foi para os usuarios (e notificou): so o texto e corrigido, nunca uma segunda notificacao.
        corrigido = servico.corrigir_texto(existente.id_publicacao, dados)
        return ResultadoChangelog(
            existente.id_publicacao,
            "texto_corrigido" if corrigido else "ja_publicada",
            True,
            arquivadas,
        )

    if existente is not None:
        servico.atualizar_rascunho(existente.id_publicacao, dados)
        id_publicacao, acao = existente.id_publicacao, "atualizada"
    else:
        id_publicacao, acao = servico.criar_rascunho(dados), "criada"

    if publicar:
        servico.publicar(id_publicacao)
    return ResultadoChangelog(id_publicacao, acao, publicar, arquivadas)


__all__ = [
    "CONTEUDO",
    "RESUMO",
    "TITULO",
    "ResultadoChangelog",
    "TITULOS_ANTERIORES",
    "nova_publicacao",
    "publicar_changelog_plataforma",
]
