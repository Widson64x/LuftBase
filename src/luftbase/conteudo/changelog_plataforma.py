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

TITULO = "Uma base nova para os sistemas Luft: conheça o LuftBase"
RESUMO = (
    "Workspace, ConnectAir e Integrador passaram a compartilhar o LuftBase: login único, perfil renovado, "
    "permissões padronizadas, avisos com notificação e um painel de controle completo. Veja tudo o que muda."
)

_IMG = "luftbase:img/changelog/"

CONTEUDO = f"""\
![Uma base nova para os sistemas Luft]({_IMG}banner.png)

:::sucesso
**Chegou o LuftBase.** O Workspace, o ConnectAir e o Integrador passaram a funcionar sobre uma mesma base,
construída para dar a você mais conforto no dia a dia e à equipe de TI mais controle, segurança e agilidade.
Esta nota conta, com calma e com imagens, o que mudou e o que você precisa saber.
:::

:::info
**Sobre as imagens desta nota.** As telas mostradas aqui são ilustrações com dados fictícios (nomes, IPs e
clientes de exemplo), feitas para explicar cada recurso. O que você vê no sistema real pode ter pequenas
diferenças de aparência.
:::

## Em um olhar

![O que muda, em um olhar]({_IMG}antes-depois.png)

- **Um login para tudo:** entre uma vez e use os três sistemas.
- **Perfil renovado:** foto com recorte, dispositivos conectados e histórico de acessos.
- **Avisos que chegam até você:** comunicados e notas de atualização, com notificação.
- **Busca global e temas:** encontre telas rapidamente e escolha o visual que prefere.
- **Permissões padronizadas:** cada acesso tem nome, e a equipe consegue copiar perfis com segurança.
- **Painel de controle completo:** integrações, serviços do servidor, versões e configurações.
- **Parâmetros do Integrador no banco:** sem planilha, com histórico e senhas protegidas.
- **Segurança e auditoria em todas as camadas.**

---

## Por que mudamos

Até aqui, cada sistema cuidava sozinho de login, permissões e avisos. Isso funcionava, mas tinha um custo:
uma melhoria feita em um sistema precisava ser refeita nos outros, e um mesmo problema podia aparecer de
formas diferentes em cada tela. O **LuftBase** resolve isso reunindo o que é comum num só lugar.

![Como tudo se conecta]({_IMG}arquitetura.png)

Na prática, o que melhora no núcleo melhora em todos os sistemas ao mesmo tempo. Para você, isso quer dizer
telas mais parecidas entre si, comportamento previsível e correções que chegam mais rápido.

### A jornada

![A jornada da migração]({_IMG}linha-do-tempo.png)

A mudança foi planejada, construída e **validada primeiro em homologação**, com a equipe, antes de ir para
produção. Cada sistema entra no seu tempo, sempre depois de testado.

:::cards
### Mesma identidade
Login, perfil e permissões funcionam do mesmo jeito em todos os sistemas.
### Menos retrabalho
Um recurso novo do núcleo fica disponível para todos, sem refazer em cada sistema.
### Mais visibilidade
A equipe de TI enxerga integrações, versões e serviços num painel único.
### Mais segurança
Senhas no cofre, sessões controladas e auditoria de cada alteração importante.
:::

---

## Entre uma vez, use em tudo

![Um login para tudo]({_IMG}login-unico.png)

Ao entrar em qualquer um dos sistemas, você já está autenticado nos outros. Vá do Workspace ao ConnectAir ou
ao Integrador pelo menu, sem digitar a senha de novo. Quando você **sai**, a sessão é encerrada em todos eles.

![Tela de entrada]({_IMG}tela-login.png)

![Hub de Sistemas]({_IMG}tela-hub.png)

- O **Hub de Sistemas** mostra os sistemas que você pode acessar e o estado de cada um.
- O caminho no topo (a trilha de navegação) mostra onde você está: a casinha leva ao Workspace, e o nome do
  sistema leva à página inicial dele.
- O seu estado **Online** só aparece enquanto você está de fato conectado. Ao sair, ele some.

---

## Seu perfil, do seu jeito

Clique no seu nome, no canto da tela, para abrir as **Configurações de Perfil**. Ali ficam seus dados, a
aparência e a segurança da conta.

### Foto com recorte

![Editor de foto]({_IMG}tela-editor-foto.png)

Clique na câmera sobre o seu avatar para abrir o editor:

- **Arraste** a imagem para posicionar o rosto dentro do círculo.
- Use o **zoom** (barra ou roda do mouse) e os botões de **girar** e **centralizar**.
- Aceita arquivos PNG, JPEG e WebP de até 8 MB, e dá para soltar a imagem direto na janela.
- **Remover foto** pede uma confirmação no próprio botão, para evitar cliques sem querer.

### Sessões e segurança

![Sessões e histórico de acessos]({_IMG}tela-perfil-sessoes.png)

Na aba **Sessões & Segurança** você acompanha a sua conta:

- **Status atual**, **total de logins**, **último acesso** e **IP registrado**.
- **Dispositivos conectados:** cada sessão mostra o **navegador e o sistema** (por exemplo, "Chrome 126 em
  Windows"), o IP e a última atividade. A sessão que você está usando é marcada como **Esta sessão**.
- **Desconectar outras sessões:** esqueceu a conta aberta em outro computador? Um clique encerra todas as outras.
- **Histórico de acessos:** os seus 5 últimos acessos, com início, fim e o motivo do encerramento (saiu da
  conta, expirou por inatividade, entre outros).

:::alerta
**Viu um acesso que não reconhece?** Use **Desconectar outras sessões**, troque a sua senha e avise o TI.
:::

---

## Avisos, busca e visual

### Comunicados e notas de atualização

![Avisos que chegam até você]({_IMG}notificacoes-arte.png)

Comunicados e notas de atualização (como esta que você está lendo) agora têm um lugar próprio, com
**notificação** no sino do topo.

![Central de notificações]({_IMG}tela-notificacoes.png)

![Notas de Atualização]({_IMG}tela-notas.png)

- O ponto azul indica o que ainda não foi lido; **Marcar todas como lidas** limpa a lista.
- Os avisos **globais** (de toda a plataforma) aparecem em todos os sistemas.
- A área **Notas de Atualização** reúne o histórico do que mudou, versão por versão.

### Busca global

![Busca global]({_IMG}tela-busca.png)

A barra de busca, no topo, encontra telas e funções em todos os sistemas a que você tem acesso. Digite parte
do nome (por exemplo, "parâmetros") e escolha o resultado.

### Escolha o seu visual

![Temas]({_IMG}tela-temas.png)

No botão **Modo** e na aba **Aparência & Tema** do perfil você alterna entre claro e escuro e escolhe a
identidade visual. A sua escolha fica salva na sua conta.

---

## Permissões: mais claras e mais seguras

Cada acesso agora tem um nome no formato **módulo, recurso e ação**. Isso deixa fácil entender o que cada
permissão libera e quem a possui.

![Modelo de permissões]({_IMG}permissoes-modelo.png)

### Copiar permissões

Para montar o acesso de uma pessoa nova, a equipe de segurança pode **copiar as permissões de um perfil de
referência**, em três passos, vendo antes exatamente o que será copiado.

![Copiar permissões]({_IMG}tela-copiar-permissoes.png)

1. **Origem:** escolha a pessoa de referência.
2. **Permissões:** marque o que deve ser copiado; o restante é ignorado.
3. **Destino:** escolha quem vai receber, e confirme.

Cada cópia fica registrada na auditoria.

:::alerta
**Faltou algum acesso?** Durante a mudança, as permissões foram reorganizadas. Se um menu ou uma ação que você
usava não aparecer, peça ao seu gestor ou ao TI para liberar o acesso. Informe o sistema e a tela.
:::

---

## Para quem administra

O **Painel de Controle** reúne o que antes exigia acesso direto ao servidor.

### Integrações

![Integrações]({_IMG}tela-integracoes.png)

Veja num só lugar se o **cofre de senhas**, o **banco de dados**, o **e-mail** e o **diretório de usuários**
estão respondendo, e qual versão do LuftBase cada sistema está usando.

### Serviços do servidor

![Serviços do servidor]({_IMG}tela-servicos.png)

Veja o estado do serviço de cada sistema e reinicie quando necessário. Todo reinício é **registrado na
auditoria**, com o nome de quem pediu.

### Variáveis de ambiente

Uma lista das configurações **não sensíveis** de cada ambiente, para conferência. Senhas e chaves nunca são
exibidas.

### Auditoria

![Trilha de auditoria]({_IMG}auditoria-trilha.png)

Alterações importantes (acessos, permissões, parâmetros, publicações) ficam registradas com **quem**, **o
quê**, **quando** e **de onde**. Isso ajuda a esclarecer dúvidas e a investigar ocorrências sem achismos.

---

## Integrador: parâmetros no banco

Os parâmetros da **Reintegração WMS** (clientes SFTP) e dos **XMLs do Ecobox** ficavam numa planilha. Agora são
cadastrados na própria tela de **Parâmetros** do Integrador.

![Parâmetros do Integrador]({_IMG}tela-parametros.png)

- **Cadastro em tela:** incluir, editar, ativar e desativar clientes, sem abrir planilha.
- **Teste de conexão** direto na linha do cliente.
- **Senhas cifradas:** depois de salva, a senha não pode mais ser vista, nem em tela nem nos logs.
- **Histórico:** cada alteração fica na auditoria.
- **Um parâmetro por ambiente:** homologação e produção têm cadastros separados, sem risco de misturar.

---

## Segurança, sem complicar a sua vida

![Segurança em camadas]({_IMG}seguranca-camadas.png)

Quase tudo isso acontece nos bastidores, e você não precisa fazer nada. Em resumo:

- **Sessão protegida:** expira por inatividade e é encerrada em todos os sistemas ao sair.
- **Cofre de senhas:** as credenciais dos sistemas ficam fora do código e dos arquivos de configuração.
- **Permissões mínimas:** cada pessoa vê e faz apenas o que precisa para o trabalho.
- **Logs cuidadosos:** quando algo falha, registramos o tipo do erro, nunca senhas ou dados pessoais.

---

## Novidades, sistema por sistema

### Luft-Workspace

O Workspace continua sendo a porta de entrada do ecossistema, agora com mais recursos:

- **Hub de Sistemas** com o estado de cada sistema e atalhos para abri-los.
- **Comunicados** e **Notas de Atualização**, com notificação no sino.
- **Painel de Controle** para a equipe de TI: integrações, serviços, variáveis, segurança e auditoria.
- **Perfil** com foto, sessões e histórico de acessos, igual em todos os sistemas.

### Luft-ConnectAir

O ConnectAir passou a usar o mesmo login e o mesmo perfil dos outros sistemas:

- Entrar no ConnectAir **não pede senha de novo** se você já estiver autenticado em outro sistema.
- As permissões do ConnectAir seguem o novo padrão (módulo, recurso e ação), o que facilita saber o que cada
  pessoa pode fazer ali.
- O menu, o caminho de navegação e a busca global têm o mesmo comportamento do Workspace.

### Luft-Integrador

O Integrador foi o sistema com mais mudanças por dentro:

- **Parâmetros no banco**, cadastrados em tela, sem planilha (veja a seção anterior).
- **Permissões próprias** para administrar o sistema e para editar cada grupo de parâmetros, como a
  Reintegração WMS e os XMLs do Ecobox.
- Mesma entrada única, mesmo perfil e mesma auditoria dos demais.

---

## Dicas rápidas

:::cards
### Esc fecha
Em painéis e janelas, a tecla **Esc** fecha o que está aberto.
### Setas no editor de foto
Com a imagem selecionada, as **setas do teclado** movem o recorte; **Shift** move mais rápido.
### Roda do mouse
No editor de foto, a **roda do mouse** aumenta e diminui o zoom.
### Tudo lido
Nas notificações, **Marcar todas como lidas** limpa o contador do sino de uma vez.
### Busca em qualquer tela
A barra de busca no topo funciona em todos os sistemas, com o mesmo jeito de usar.
### Sessões sob controle
Confira de vez em quando os seus dispositivos conectados, na aba Sessões & Segurança.
:::

---

## Para gestores: checklist de acessos

Se você coordena uma equipe, este roteiro ajuda a conferir se todo mundo está com o acesso certo:

1. **Peça à equipe que entre** pelo menos uma vez no Workspace e abra o sistema que usa.
2. **Liste quem não conseguiu** abrir algum menu ou executar alguma ação.
3. **Informe ao TI** o nome da pessoa, o sistema e a tela, e, se possível, **uma pessoa de referência** com o
   mesmo papel. Com ela, o TI usa **Copiar permissões** e resolve na hora.
4. **Confirme com a pessoa** depois que o acesso foi liberado.

:::sucesso
**Dica:** descrever o papel ("é analista de reintegração, igual ao Fulano") ajuda mais do que listar telas.
:::

---

## Como pedir ajuda ao TI

Para que o atendimento seja rápido, ao abrir um chamado informe:

- **O sistema e a tela** em que aconteceu.
- **O que você estava fazendo** e o que esperava que acontecesse.
- **O horário aproximado.** Com a nova base, a equipe consegue localizar o registro do ocorrido pelo horário.
- **Uma captura de tela**, se possível.

Não envie a sua senha em nenhum chamado. O TI nunca precisa dela.

---

## Compromisso com a qualidade

A nova base nasceu com **testes automatizados** e passou por validação em homologação antes de chegar a você.
Mesmo assim, é natural que algum detalhe passe despercebido. Quando isso acontecer, o caminho é curto:
você avisa, a equipe reproduz, corrige e publica a correção, e o que mudou aparece aqui, em **Notas de
Atualização**.

---

## O que você precisa fazer

1. **Entre normalmente.** Talvez seja pedido um novo login uma única vez.
2. **Confira os seus acessos.** Se algo que você usa não aparecer, fale com o gestor ou com o TI.
3. **Dê uma olhada no perfil.** Coloque a sua foto e veja os seus dispositivos conectados.
4. **Conte para a gente.** Achou algo estranho ou teve uma ideia? Abra um chamado para o TI.

## Perguntas frequentes

**Preciso trocar a minha senha?**
Não. Use a mesma senha de sempre.

**Por que me pediram para entrar de novo?**
A sessão antiga foi criada na base anterior. Depois do novo login, ela passa a valer para os três sistemas.

**Perdi um acesso que eu tinha. E agora?**
As permissões foram reorganizadas. Peça ao seu gestor ou ao TI para liberar de novo, informando o sistema e a tela.

**O que significa "Online" no meu perfil?**
Que você está conectado agora. Quando você sai ou a sessão expira, o estado deixa de ser online.

**Vi uma sessão que não reconheço.**
Use **Desconectar outras sessões**, troque a senha e avise o TI.

**Os outros sistemas da empresa também mudaram?**
Esta mudança vale para o **Workspace**, o **ConnectAir** e o **Integrador**.

**Onde vejo o que mudou nas próximas versões?**
Em **Notas de Atualização**, no menu. Cada versão traz o que há de novo.

## Pequeno glossário

- **LuftBase:** a base comum que sustenta os sistemas, com login, permissões, avisos e painel de controle.
- **Sessão:** o período em que você está conectado a partir de um navegador ou dispositivo.
- **Permissão:** um acesso específico, no formato módulo, recurso e ação.
- **Cofre de senhas:** o local protegido onde ficam as credenciais usadas pelos sistemas.
- **Auditoria:** o registro de quem fez o quê, quando e de onde.
- **Homologação:** o ambiente de testes onde validamos tudo antes da produção.

![Obrigado]({_IMG}encerramento.png)

> Obrigado por usar os sistemas Luft. Esta é a primeira de muitas melhorias, e a sua opinião ajuda a definir as próximas.
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
