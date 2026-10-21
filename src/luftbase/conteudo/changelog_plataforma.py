"""Nota de atualização global: a plataforma Luft passou a rodar no LuftBase.

O texto usa o markdown seguro de `markdown_seguro` (imagens `luftbase:` ficam em
`interface/static/img/changelog`). `publicar_changelog_plataforma` cria a nota como GLOBAL (sistema 0),
com notificação, e é idempotente: repetir não duplica.
"""

from __future__ import annotations

from dataclasses import dataclass

from luftbase.conteudo.modelos import (
    ItemNotaAtualizacao,
    NovaPublicacao,
    PrioridadePublicacao,
    TipoAudiencia,
    TipoItemAtualizacao,
    TipoPublicacao,
)
from luftbase.conteudo.servicos import ServicoPublicacoes

TITULO = "Uma base nova para o Workspace, o ConnectAir e o Integrador"
RESUMO = (
    "O Luft-Workspace, o Luft-ConnectAir e o Luft-Integrador passaram a usar uma base nova: login único, "
    "perfil renovado, avisos com notificação e comunicados escritos como e-mails. O Luft-Control será o próximo a migrar."
)

# Titulos de versoes anteriores da mesma nota: a nota ja publicada e reconhecida e tem o texto corrigido.
TITULOS_ANTERIORES = (
    "Nova plataforma Luft: o ecossistema agora roda no LuftBase",
    "Uma base nova para os sistemas Luft: conheça o LuftBase",
    "Uma base nova para os sistemas web Luft",
)

_IMG = "luftbase:img/changelog/"

CONTEUDO = f"""\
![Uma base nova para o Workspace, o ConnectAir e o Integrador]({_IMG}banner.png)

:::sucesso
**Uma base nova chegou ao Luft-Workspace, ao Luft-ConnectAir e ao Luft-Integrador.** O resultado é uma
experiência mais simples, mais parecida entre esses sistemas e mais segura. O **Luft-Control** será o próximo
a ser migrado.
:::

## O que muda para você

![O que muda, em um olhar]({_IMG}antes-depois.png)

- **Um login para tudo:** entre uma vez e use o Workspace, o ConnectAir e o Integrador.
- **Perfil renovado:** foto com recorte, dispositivos conectados e histórico dos seus acessos.
- **Avisos que chegam até você:** comunicados e notas de atualização, com notificação.
- **Busca e visual:** encontre telas rapidamente e escolha o tema que prefere.
- **Mesmo jeito de usar:** menus, perfil e avisos funcionam de forma igual nesses três sistemas.

---

## Quais sistemas já estão na nova base

![Quais sistemas já estão na nova base]({_IMG}linha-do-tempo.png)

A mudança está sendo feita **sistema por sistema**, sempre depois de testada. Hoje já estão adaptados o
Workspace, o ConnectAir e o Integrador, e o **Luft-Control** será o próximo. Os outros sistemas da Luft,
construídos com outras tecnologias, continuam como são hoje, com o próprio login e o próprio visual. Quando
houver novidade, você será avisado por aqui.

---

## Entre uma vez, use em tudo

![Um login para tudo]({_IMG}login-unico.png)

Ao entrar no Workspace, no ConnectAir ou no Integrador, você já está autenticado nos outros dois. Vá de um sistema a outro pelo
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

## Novo: comunicados escritos como e-mails

![Do texto simples ao editor visual]({_IMG}comunicados-antes-depois.png)

Quem publica comunicados e notas de atualização agora tem um **editor visual**: títulos, tamanhos de letra, cores, marca-texto, listas, tabelas, links e **imagens** (cole, arraste ou use o botão). Você, que lê, recebe o aviso com a mesma cara de um e-mail, em uma caixa de entrada própria, com o que é novo em destaque.

![Barra de ferramentas do editor]({_IMG}comunicados-barra.png)

![Destaques de informação, sucesso, alerta e perigo]({_IMG}comunicados-destaques.png)

- **Caixa de entrada:** os comunicados fixados ficam no topo, o mais novo vem primeiro e um ponto azul marca o que você ainda não leu.
- **Leitura como e-mail:** quem enviou, quando e para quem, com opção de imprimir ou salvar em PDF.
- **Notas de atualização:** cada mudança aparece na categoria certa (novo, melhoria, correção, segurança ou técnico).

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
A sessão antiga foi criada antes da mudança. Depois do novo login, ela vale para os três sistemas.

**Perdi um acesso que eu tinha. E agora?**
Peça ao seu gestor ou ao TI para liberar de novo, informando o sistema e a tela.

**O sistema que eu uso não está nessa lista. Vai mudar?**
Por enquanto a mudança vale para o Workspace, o ConnectAir e o Integrador, e o Luft-Control será o próximo.
Os outros sistemas da Luft continuam como estão, e você será avisado de qualquer novidade.

## Precisa de ajuda?

Abra um chamado para o **TI** informando o **sistema e a tela**, o **que você estava fazendo** e o **horário
aproximado**. Uma captura de tela ajuda bastante. Nunca envie a sua senha.

![Obrigado]({_IMG}encerramento.png)

> Obrigado por usar os sistemas Luft. Esta é a primeira de muitas melhorias, e a sua opinião ajuda a definir as próximas.
"""


ITENS = (
    ItemNotaAtualizacao("Login único nos sistemas Luft", "Entre uma vez e use o Workspace, o ConnectAir e o Integrador.", TipoItemAtualizacao.NOVO, 0),
    ItemNotaAtualizacao("Comunicados escritos como e-mails", "Editor visual com tamanhos, cores, listas, tabelas, destaques e imagens.", TipoItemAtualizacao.NOVO, 1),
    ItemNotaAtualizacao("Caixa de entrada de comunicados", "Fixados no topo, mais novo primeiro e indicação do que não foi lido.", TipoItemAtualizacao.MELHORIA, 2),
    ItemNotaAtualizacao("Perfil renovado", "Foto com recorte, dispositivos conectados e histórico de acessos.", TipoItemAtualizacao.MELHORIA, 3),
    ItemNotaAtualizacao("Busca global e temas", "Encontre telas pelo nome e escolha entre o tema claro, o escuro e o ESG.", TipoItemAtualizacao.MELHORIA, 4),
    ItemNotaAtualizacao("Edição de rascunhos", "Corrigido o erro que impedia salvar a edição de um rascunho.", TipoItemAtualizacao.CORRECAO, 5),
    ItemNotaAtualizacao("Leitura das notas", "A leitura passou a mostrar o autor e a lista do que mudou.", TipoItemAtualizacao.CORRECAO, 6),
    ItemNotaAtualizacao("Texto protegido", "O conteúdo dos comunicados é limpo no servidor: sem scripts e sem links perigosos.", TipoItemAtualizacao.SEGURANCA, 7),
    ItemNotaAtualizacao("Sessão única e encerramento em todos os sistemas", "Sair em um sistema encerra a sessão nos demais.", TipoItemAtualizacao.SEGURANCA, 8),
    ItemNotaAtualizacao("Nova base da plataforma", "Workspace, ConnectAir e Integrador passam a usar o mesmo LuftBase.", TipoItemAtualizacao.TECNICO, 9),
)


@dataclass(frozen=True, slots=True)
class ResultadoChangelog:
    """O que `publicar_changelog_plataforma` fez."""

    id_publicacao: int
    acao: str  # "criada" | "atualizada" | "texto_corrigido" | "ja_publicada"
    publicada: bool
    arquivadas: int = 0  # copias antigas da mesma nota que foram arquivadas


def nova_publicacao(
    *,
    versao: str,
    notificar: bool = True,
    criado_por: str = "Equipe Luft",
    criado_por_id: int | None = None,
) -> NovaPublicacao:
    return NovaPublicacao(
        titulo=TITULO,
        resumo=RESUMO,
        conteudo=CONTEUDO,
        criado_por=criado_por,
        criado_por_id=criado_por_id,
        itens_atualizacao=ITENS,
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
    criado_por: str = "Equipe Luft",
    criado_por_id: int | None = None,
) -> ResultadoChangelog:
    """Cria (ou atualiza o rascunho de) a nota e a publica; nunca duplica uma já publicada."""

    dados = nova_publicacao(
        versao=versao, notificar=notificar, criado_por=criado_por, criado_por_id=criado_por_id
    )
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
    "ITENS",
    "RESUMO",
    "TITULO",
    "ResultadoChangelog",
    "TITULOS_ANTERIORES",
    "nova_publicacao",
    "publicar_changelog_plataforma",
]
