"""Nota de atualização global: os sistemas Luft passaram a rodar no LuftBase.

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

TITULO = "Uma base nova para o Workspace, o ConnectAir, o Integrador, o Control e o Docs"
RESUMO = (
    "O Luft-Workspace, o Luft-ConnectAir, o Luft-Integrador, o Luft-Control e o Luft-Docs passaram a usar a mesma base: "
    "login único, perfil renovado, avisos com notificação e comunicados escritos como e-mails."
)

# Titulos de versoes anteriores da mesma nota: a nota ja publicada e reconhecida e tem o texto corrigido.
TITULOS_ANTERIORES = (
    "Uma base nova para o Workspace, o ConnectAir e o Integrador",
    "Nova plataforma Luft: o ecossistema agora roda no LuftBase",
    "Uma base nova para os sistemas Luft: conheça o LuftBase",
    "Uma base nova para os sistemas web Luft",
)

_IMG = "luftbase:img/changelog/"

CONTEUDO = f"""\
![Uma base nova para o seu dia a dia]({_IMG}banner.png)

:::sucesso
**Uma base nova chegou a cinco sistemas Luft:** o **Workspace**, o **ConnectAir**, o **Integrador**, o **Control** e o **Docs**.
O resultado é uma experiência mais simples, mais parecida entre os sistemas e mais segura: você entra uma vez, usa o mesmo
perfil em todos eles e recebe os avisos no mesmo lugar.
:::

## Em resumo

:::cards
### Um login para tudo
Entre uma vez e use os cinco sistemas. Ao sair, a sessão é encerrada em todos.
### Perfil renovado
Foto com recorte, dispositivos conectados e histórico dos seus acessos.
### Avisos com notificação
Comunicados e notas de atualização chegam ao sino, com o que é novo em destaque.
### Comunicados como e-mails
Texto formatado, tabelas, destaques e imagens, em uma caixa de entrada própria.
### Busca e atalhos
Encontre telas e funções pelo nome com o Ctrl+K.
### Visual à sua escolha
Tema claro, escuro ou ESG, salvo na sua conta.
:::

---

## O que muda para você

![O que muda, em um olhar]({_IMG}antes-depois.png)

- **Um login para tudo:** entre uma vez e use o Workspace, o ConnectAir, o Integrador, o Control e o Docs.
- **Perfil renovado:** foto com recorte, dispositivos conectados e histórico dos seus acessos.
- **Avisos que chegam até você:** comunicados e notas de atualização, com notificação.
- **Comunicados mais claros:** escritos com títulos, listas, tabelas, destaques e imagens.
- **Busca e visual:** encontre telas rapidamente e escolha o tema que prefere.
- **Mesmo jeito de usar:** menus, perfil e avisos funcionam de forma igual nos cinco sistemas.
- **Mais controle sobre a sua conta:** você vê onde está conectado e pode encerrar o que não reconhece.

---

## Quais sistemas já estão na nova base

![Quais sistemas já estão na nova base]({_IMG}linha-do-tempo.png)

A mudança foi feita **sistema por sistema**, sempre depois de testada. Hoje os cinco sistemas abaixo já usam a nova base.

![Os sistemas da nova base]({_IMG}sistemas-cartoes.png)

### Luft-Workspace

O portal central: o **Hub de Sistemas**, o **Painel de Controle**, os comunicados e as notas de atualização. É por ele que você
chega aos outros sistemas. Está na nova base desde **2 de outubro**.

### Luft-ConnectAir

O sistema de **planejamento aéreo**. Também migrou em **2 de outubro**. O login, as permissões, os avisos e o perfil agora são
os mesmos do Workspace.

### Luft-Integrador

O sistema de **integração de arquivos e dados**. Migrou em **5 de outubro**, com o mesmo login único, perfil e avisos.

### Luft-Control

O sistema de **controladoria**: Razão contábil, DRE e Budget. Migrou em **14 de outubro**. As permissões foram reescritas e a
gestão de usuários e acessos passou a ser feita no Painel de Controle, como nos outros sistemas.

### Luft-Docs

O portal de **documentação** da Luft, com busca, roteiros e a assistente **LIA**. Migrou em **19 de outubro**. As preferências e o
**Reportar problema** ficam em **Config.**, na aba *Configurações Gerais*.

![Como chegamos até aqui]({_IMG}cronologia.png)

:::info
**E os outros sistemas da Luft?** Os sistemas construídos com outras tecnologias continuam como são hoje, com o próprio login e o
próprio visual. Quando houver novidade, você será avisado por aqui.
:::

---

## Entre uma vez, use em tudo

![Um login para tudo]({_IMG}login-unico.png)

Ao entrar em um dos cinco sistemas, você já está autenticado nos outros quatro. Vá de um sistema a outro pelo menu, sem digitar a
senha de novo. Quando você **sai**, a sessão é encerrada em todos eles.

![Tela de entrada]({_IMG}tela-login.png)

- **O mesmo usuário e a mesma senha da rede** da Luft. A senha não é guardada pelos sistemas.
- **A sessão expira por inatividade.** O prazo é definido pelo ambiente. Ao voltar, entre de novo; o que você digitava e não salvou se perde.
- **Para sair**, use o botão **Sair**, no rodapé do menu lateral.
- **O estado Online** só aparece enquanto você está de fato conectado.

:::alerta
**Sessão expirada no meio de um trabalho?** Salve com frequência o que estiver preenchendo. A sessão expira só depois de um período
sem nenhuma atividade, mas o que não foi salvo não é recuperado.
:::

---

## O Hub de Sistemas, por dentro

![Hub de Sistemas]({_IMG}tela-hub.png)

O Hub é a sua tela inicial. Ele mostra uma saudação com o seu nome e uma etiqueta que resume se tudo está no ar.

- **Total de sistemas:** quantos sistemas você pode acessar.
- **Online:** quantos deles estão no ar.
- **Em manutenção:** quantos estão indisponíveis no momento.
- **Favoritos:** quantos você marcou com a estrela.

Abaixo, um cartão por sistema, os **acessos recentes** e os **avisos e comunicados** mais novos, com o botão **Suporte** sempre à mão.

### Organize a lista

![Organize os seus sistemas]({_IMG}hub-organizar.png)

1. Troque entre a lista completa e as abas **Favoritos** e **Acessados recentemente**.
2. Ordene por **Nome (A-Z)**, **Nome (Z-A)**, **Online primeiro** ou **Em manutenção primeiro**.
3. Clique na **estrela** do cartão para favoritar.

:::info
Favoritos e acessos recentes ficam guardados **no seu navegador**. Se você trocar de computador, de navegador ou limpar os dados
do navegador, eles não acompanham você.
:::

### Quando um sistema está em manutenção

![Sistema em manutenção]({_IMG}manutencao.png)

Um cartão **Indisponível** é um sistema em manutenção: ele não abre enquanto ela durar, e no menu lateral aparece com a etiqueta
*indisponível*. Quando a manutenção termina, ele volta ao normal sozinho.

### "Não vejo um sistema que eu deveria ver"

O Hub só mostra os sistemas para os quais você tem **permissão de acesso**. Se algum não aparece, peça a liberação ao responsável
pelo sistema ou ao TI, informando o nome do sistema.

---

## Como o seu acesso chega até você

![Como o seu acesso chega até você]({_IMG}acesso-liberado.png)

Os acessos são concedidos no Painel de Controle, para uma pessoa ou para um grupo inteiro. Quando você **passa de "sem acesso" para
"com acesso"** a um sistema, a plataforma avisa:

- com uma **notificação** no sino, com um atalho para abrir o sistema;
- e com um **e-mail**, quando o envio de e-mail está configurado no ambiente e você tem e-mail no cadastro.

O aviso não é repetido se você já tinha acesso por outro caminho, como o seu grupo.

:::alerta
**Os acessos foram reorganizados nesta mudança.** Se algum menu ou ação que você usava não aparecer, peça ao seu gestor ou ao TI
para liberar, informando o **sistema** e a **tela**.
:::

---

## Seu perfil, do seu jeito

Clique no seu nome, no canto inferior esquerdo, para abrir o **perfil**. Ele é o mesmo nos cinco sistemas: o que você muda em um
vale para os outros.

### Dados e contatos

Atualize telefone, celular, cargo, departamento e unidade. O **login** e o **código de usuário** não mudam.

### Foto com recorte

![Editor de foto]({_IMG}tela-editor-foto.png)

Clique na câmera sobre o seu avatar para abrir o editor. **Arraste** a imagem para posicionar o rosto no círculo, use o **zoom** e os
botões de **girar** e **centralizar**. Aceita imagens PNG, JPEG e WebP de até 8 MB, e dá para soltar o arquivo direto na janela.
**Remover foto** pede uma confirmação, para evitar cliques sem querer. A foto vale nos cinco sistemas.

### Sessões e segurança

![Sessões e histórico de acessos]({_IMG}tela-perfil-sessoes.png)

Na aba **Sessões & Segurança** você acompanha a sua conta:

- **Resumo:** o seu estado atual, o total de logins, o último acesso e o IP registrado.
- **Dispositivos conectados:** cada sessão mostra o navegador, o sistema e o IP. A que você está usando aparece como **Esta sessão**.
- **Desconectar outras sessões:** esqueceu a conta aberta em outro computador? Um clique encerra todas as outras.
- **Histórico de acessos:** os seus 5 últimos acessos, com início, fim e o motivo do encerramento (você saiu, a sessão expirou por inatividade, foi renovada ou foi encerrada à força).

:::alerta
**Viu um acesso que não reconhece?** Use **Desconectar outras sessões**, troque a sua senha e avise o TI.
:::

---

## A sua conta, protegida e à vista

![A sua conta, protegida e à vista]({_IMG}protecao-conta.png)

- **Sessão com prazo:** sem atividade por um tempo, ela expira.
- **Sair em um, sair em todos:** a saída vale para os cinco sistemas.
- **Você enxerga onde está conectado:** navegador, sistema, IP e última atividade.
- **Bloqueio de acesso:** se um administrador bloquear uma conta, as sessões dela caem e a entrada é recusada com a mensagem "Seu acesso está bloqueado. Procure um administrador."
- **Tudo fica registrado:** acessos, mudanças de permissão e encerramentos de sessão ficam registrados e podem ser consultados pelos responsáveis.

---

## Avisos, notificações e comunicados

### O sino

![Avisos que chegam até você]({_IMG}notificacoes-arte.png)

Comunicados, notas de atualização e avisos de acesso chegam com **notificação** no sino do topo. O ponto indica o que ainda não foi
lido. Você pode **marcar como lida**, **marcar todas como lidas** e **limpar**.

![Central de notificações]({_IMG}tela-notificacoes.png)

### Limpar sem apagar para os outros

![Limpe a sua lista]({_IMG}notificacoes-limpar.png)

O botão **Limpar** tem duas opções: **Limpar as lidas** e **Limpar todas**. A notificação some **só da sua lista** e do contador do
sino; as demais pessoas continuam a vê-la. Depois de limpar, um aviso de 8 segundos oferece **Desfazer**.

### Comunicados escritos como e-mails

![Do texto simples ao editor visual]({_IMG}comunicados-antes-depois.png)

Quem publica comunicados agora tem um **editor visual**: títulos, tamanhos de letra, cores, marca-texto, listas, tabelas, links e
**imagens**. Para você, que lê, isso significa avisos mais claros e fáceis de ler.

![Caixa de entrada de comunicados]({_IMG}comunicados-caixa-entrada.png)

- **Caixa de entrada:** os comunicados fixados ficam no topo, o mais novo vem primeiro e um **ponto azul** marca o que você ainda não leu.
- **Marcas de importância:** avisos de prioridade alta ou crítica ganham uma faixa de cor e a etiqueta *Importante* ou *Urgente*.
- **Busca:** a caixa de busca encontra por assunto, resumo, autor e versão.

![Tela de leitura de um comunicado]({_IMG}comunicados-leitura.png)

A leitura parece um e-mail: mostra **quem enviou**, **quando** e **para quem**, e tem o botão **Imprimir**, que também serve para salvar
o comunicado em PDF.

![Destaques de informação, sucesso, alerta e perigo]({_IMG}comunicados-destaques.png)

Os **destaques coloridos** chamam a atenção para o que importa: azul para informação, verde para boas notícias, amarelo para prazos e
vermelho para riscos.

### Notas de atualização

![Notas de Atualização]({_IMG}tela-notas.png)

Em **Notas de Atualização**, no menu, fica o histórico do que mudou, versão por versão. Cada mudança aparece em uma categoria:
**Novo**, **Melhoria**, **Correção**, **Segurança** ou **Técnico**. As notas **globais** aparecem nos cinco sistemas.

---

## Busca global

![Busca global]({_IMG}tela-busca.png)

A caixa **Buscar**, no topo, encontra telas e funções nos sistemas a que você tem acesso. Digite parte do nome e escolha o resultado.

![Busca com o teclado]({_IMG}busca-atalho.png)

Use **Ctrl+K** para abrir a busca de qualquer lugar. As **setas** navegam pelos resultados, **Enter** abre e **Esc** fecha.

---

## Escolha o seu visual

![Temas]({_IMG}tela-temas.png)

No botão **Modo** (rodapé do menu) e na aba **Aparência & Tema** do perfil você escolhe entre o tema **claro**, o **escuro** e a
identidade **ESG**. Há também a opção de seguir o modo do seu sistema operacional. A escolha fica salva na sua conta e vale nos cinco sistemas.

![Os três visuais]({_IMG}temas-tres.png)

---

## Para quem administra

![O Painel de Controle em seis abas]({_IMG}painel-controle.png)

O **Painel de Controle** fica no menu lateral e no botão **Config.** **Cada aba só aparece para quem tem a permissão correspondente.**
No Workspace, o painel enxerga cada um dos sistemas; no painel de um sistema comum, só aquele sistema.

- **Segurança & Permissões:** conceder e bloquear acessos por pessoa ou por grupo, copiar permissões, bloquear e desbloquear usuários e criar módulos.
- **Aplicações & Ambiente:** o catálogo de sistemas, a manutenção, as variáveis permitidas e os serviços do servidor.
- **Comunicação:** os comunicados e a gestão das notas de atualização, agora com o editor visual.
- **Auditoria & Análise:** quem acessou, desempenho, segurança, quem está conectado agora e o controle de sessões.
- **Configurações Gerais:** parâmetros que o próprio sistema declara.

### Liberar o acesso de uma pessoa

1. Abra **Painel de Controle** e **Segurança & Permissões**.
2. Escolha o **sistema** e abra **Por Usuários (Exceções)** ou **Por Grupos Corporativos**.
3. Busque a pessoa ou o grupo e clique em **Permitir** na permissão **Acessar o sistema**, mais as permissões de que ela precisa.
4. Ao salvar, a própria tela informa quantas pessoas foram avisadas.

### Publicar um comunicado

1. Abra **Comunicação** e **Comunicados** (ou **Gestão de Changelog**).
2. Escreva no editor, confira na aba **Pré-visualizar** e defina a audiência: todos ou grupos.
3. Use **Salvar rascunho** para guardar sem entregar ou **Salvar e publicar** para entregar agora.
4. Se quiser, agende o início e defina quando o comunicado deixa de aparecer.

:::sucesso
**Para o TI:** os alertas técnicos da plataforma (erros que afetam usuários) chegam por e-mail à caixa de **sistemas.web**, com o
sistema, a rota e a pessoa afetada. Nunca levam senha nem dados enviados.
:::

---

## O que você precisa fazer

1. **Entre normalmente.** Talvez seja pedido um novo login uma única vez.
2. **Confira os seus acessos.** Os acessos foram reorganizados nesta mudança. Se algum menu ou ação que você usava não aparecer, peça ao seu gestor ou ao TI para liberar, informando o sistema e a tela.
3. **Dê uma olhada no perfil.** Coloque a sua foto e veja os seus dispositivos conectados.
4. **Escolha o seu tema** e experimente o **Ctrl+K**.
5. **Favorite** os sistemas que você mais usa no Hub.

## Perguntas frequentes

**Preciso trocar a minha senha?**
Não. Use a mesma senha de sempre.

**Por que me pediram para entrar de novo?**
A sessão antiga foi criada antes da mudança. Depois do novo login, ela vale para os cinco sistemas.

**Perdi um acesso que eu tinha. E agora?**
Peça ao seu gestor ou ao TI para liberar de novo, informando o sistema e a tela.

**O sistema que eu uso não está nessa lista. Vai mudar?**
Por enquanto a mudança vale para o Workspace, o ConnectAir, o Integrador, o Control e o Docs. Os outros sistemas da Luft continuam como estão, e você será avisado de qualquer novidade.

**Sair de um sistema me desconecta dos outros?**
Sim. A sessão é única: ao sair de um, você sai de todos.

**Esqueci a sessão aberta em outro computador. Como encerro?**
Abra o perfil, vá em **Sessões & Segurança** e use **Desconectar outras sessões**.

**Como sei se alguém usou a minha conta?**
Veja o **Histórico de acessos** na aba **Sessões & Segurança**: ele mostra os seus 5 últimos acessos com horário e IP. Se algo estiver estranho, desconecte as outras sessões, troque a senha e avise o TI.

**Os meus favoritos sumiram.**
Favoritos e acessos recentes ficam guardados no navegador em uso. Se você mudou de navegador ou de computador, favorite de novo.

**Um sistema aparece como *Indisponível*.**
Ele está em manutenção. Aguarde ou fale com o responsável.

**Fui desconectado sem avisar.**
A sessão expira depois de um tempo sem atividade. Entre de novo.

**Limpei uma notificação sem querer.**
Logo depois de limpar aparece um aviso com **Desfazer**, por 8 segundos.

**Limpar uma notificação apaga para os outros?**
Não. Ela some só da sua lista e do seu contador.

**Posso imprimir um comunicado?**
Sim. Abra o comunicado e clique em **Imprimir**. A janela de impressão também permite salvar em PDF.

**Mudei a foto em um sistema. Ela vale nos outros?**
Sim. O perfil é o mesmo nos cinco sistemas.

**O tema escuro vale nos cinco sistemas?**
Sim. A escolha fica salva na sua conta.

**Liberaram o meu acesso e não recebi e-mail.**
A notificação no sino chega sempre. O e-mail depende de o envio estar configurado no ambiente e de você ter e-mail no cadastro. Não receber o e-mail não impede o acesso.

## Glossário rápido

- **Hub de Sistemas:** a sua tela inicial, com os sistemas a que você tem acesso.
- **Login único (SSO):** entrar uma vez e valer nos cinco sistemas.
- **Sessão:** o período em que você está conectado.
- **Permissão:** a autorização para ver ou fazer algo em uma tela.
- **Grupo:** um conjunto de pessoas, como uma área ou função.
- **Notificação:** o aviso que aparece no sino.
- **Comunicado:** um aviso corporativo, para todos ou para grupos.
- **Nota de atualização:** o texto que conta o que mudou em uma versão.
- **Painel de Controle:** a área de administração dos sistemas.
- **LuftBase:** a base comum que os sistemas Luft passaram a usar.

---

*As telas mostradas nesta nota são ilustrações, com dados fictícios.*

## Precisa de ajuda?

![Precisa de ajuda?]({_IMG}ajuda-chamado.png)

Use o botão **Suporte**, no Hub, ou abra um chamado para o **TI** informando o **sistema e a tela**, o **que você estava fazendo** e o
**horário aproximado**. Uma captura de tela ajuda bastante. Nunca envie a sua senha.

![Obrigado]({_IMG}encerramento.png)

> Obrigado por usar os sistemas Luft. Esta é a primeira de muitas melhorias, e a sua opinião ajuda a definir as próximas.
"""

ITENS = (
    ItemNotaAtualizacao("Login único nos cinco sistemas", "Workspace, ConnectAir, Integrador, Control e Docs: entre uma vez e use todos.", TipoItemAtualizacao.NOVO, 0),
    ItemNotaAtualizacao("Comunicados escritos como e-mails", "Editor visual com tamanhos, cores, listas, tabelas, destaques e imagens.", TipoItemAtualizacao.NOVO, 1),
    ItemNotaAtualizacao("Dispositivos conectados e histórico de acessos", "Veja onde a conta está aberta e os 5 últimos acessos, e encerre as outras sessões.", TipoItemAtualizacao.NOVO, 2),
    ItemNotaAtualizacao("Desfazer ao limpar notificações", "Depois de limpar, um aviso de 8 segundos permite voltar atrás. Limpar vale só para você.", TipoItemAtualizacao.NOVO, 3),
    ItemNotaAtualizacao("Hub com indicadores e favoritos", "Total, online, em manutenção e favoritos, com abas e ordenação.", TipoItemAtualizacao.MELHORIA, 4),
    ItemNotaAtualizacao("Caixa de entrada de comunicados", "Fixados no topo, mais novo primeiro e ponto azul no que não foi lido.", TipoItemAtualizacao.MELHORIA, 5),
    ItemNotaAtualizacao("Leitura como e-mail", "Remetente, data, audiência e botão para imprimir ou salvar em PDF.", TipoItemAtualizacao.MELHORIA, 6),
    ItemNotaAtualizacao("Perfil renovado", "Foto com recorte, dados de contato e aparência em um só lugar.", TipoItemAtualizacao.MELHORIA, 7),
    ItemNotaAtualizacao("Busca global e temas", "Ctrl+K para achar telas e três visuais: claro, escuro e ESG.", TipoItemAtualizacao.MELHORIA, 8),
    ItemNotaAtualizacao("Edição de rascunhos", "Corrigido o erro que impedia salvar a edição de um rascunho.", TipoItemAtualizacao.CORRECAO, 9),
    ItemNotaAtualizacao("Leitura das notas de atualização", "A leitura passou a mostrar o autor e a lista do que mudou.", TipoItemAtualizacao.CORRECAO, 10),
    ItemNotaAtualizacao("Editor de comunicados com textos grandes", "O editor deixou de estourar a janela com tabelas e blocos largos.", TipoItemAtualizacao.CORRECAO, 11),
    ItemNotaAtualizacao("Texto dos comunicados protegido", "O conteúdo é limpo no servidor: sem scripts e sem links perigosos.", TipoItemAtualizacao.SEGURANCA, 12),
    ItemNotaAtualizacao("Sessão única e saída em todos os sistemas", "Sair em um sistema encerra a sessão nos demais.", TipoItemAtualizacao.SEGURANCA, 13),
    ItemNotaAtualizacao("Bloqueio de acesso derruba as sessões", "Ao bloquear uma conta, as sessões abertas caem e a entrada é recusada.", TipoItemAtualizacao.SEGURANCA, 14),
    ItemNotaAtualizacao("Aviso de acesso liberado", "Notificação e e-mail quando você passa a ter acesso a um sistema.", TipoItemAtualizacao.SEGURANCA, 15),
    ItemNotaAtualizacao("Migração do Workspace e do ConnectAir", "Em 2 de outubro, para a base comum da plataforma.", TipoItemAtualizacao.TECNICO, 16),
    ItemNotaAtualizacao("Migração do Integrador", "Em 5 de outubro, com o core da plataforma em PostgreSQL.", TipoItemAtualizacao.TECNICO, 17),
    ItemNotaAtualizacao("Migração do Control", "Em 14 de outubro, com permissões reescritas e banco no schema do sistema.", TipoItemAtualizacao.TECNICO, 18),
    ItemNotaAtualizacao("Migração do Docs", "Em 19 de outubro, eliminando a API separada que o Docs usava.", TipoItemAtualizacao.TECNICO, 19),
    ItemNotaAtualizacao("Alertas técnicos por e-mail", "Erros que afetam usuários avisam a caixa de sistemas.web, sem dados sensíveis.", TipoItemAtualizacao.TECNICO, 20),
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
