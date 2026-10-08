"""Catalogo canonico de modulos, acoes e permissoes do LuftBase."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AcaoPermissao(StrEnum):
    """Acoes autorizaveis aceitas pelo catalogo corporativo."""

    ACESSAR = "ACESSAR"
    ADMINISTRAR = "ADMINISTRAR"
    APROVAR = "APROVAR"
    ARQUIVAR = "ARQUIVAR"
    ATIVAR = "ATIVAR"
    BAIXAR = "BAIXAR"
    CANCELAR = "CANCELAR"
    CONCEDER = "CONCEDER"
    CONFIGURAR = "CONFIGURAR"
    CRIAR = "CRIAR"
    DESATIVAR = "DESATIVAR"
    EDITAR = "EDITAR"
    ENVIAR = "ENVIAR"
    EXECUTAR = "EXECUTAR"
    EXCLUIR = "EXCLUIR"
    EXPORTAR = "EXPORTAR"
    GERENCIAR = "GERENCIAR"
    IGNORAR = "IGNORAR"
    IMPORTAR = "IMPORTAR"
    IMPRIMIR = "IMPRIMIR"
    LISTAR = "LISTAR"
    PROCESSAR = "PROCESSAR"
    PUBLICAR = "PUBLICAR"
    REJEITAR = "REJEITAR"
    REPROCESSAR = "REPROCESSAR"
    REVOGAR = "REVOGAR"
    SINCRONIZAR = "SINCRONIZAR"
    VISUALIZAR = "VISUALIZAR"


class PermissaoLuftBase(StrEnum):
    """Chaves usadas pelas funcionalidades sistemicas do LuftBase e Workspace."""

    SISTEMA_ADMINISTRAR = "PLATAFORMA.SISTEMA.ADMINISTRAR"
    SISTEMA_ACESSAR = "PLATAFORMA.SISTEMA.ACESSAR"

    INICIO_GERENCIAR = "INICIO.MODULO.GERENCIAR"
    INICIO_VISUALIZAR = "INICIO.PAINEL.VISUALIZAR"

    CONFIGURACOES_GERENCIAR = "CONFIGURACOES.MODULO.GERENCIAR"
    CONFIGURACOES_VISUALIZAR = "CONFIGURACOES.PAINEL.VISUALIZAR"
    SISTEMAS_GERENCIAR = "CONFIGURACOES.SISTEMAS.GERENCIAR"
    SISTEMAS_VISUALIZAR = "CONFIGURACOES.SISTEMAS.VISUALIZAR"
    SISTEMAS_CRIAR = "CONFIGURACOES.SISTEMAS.CRIAR"
    SISTEMAS_EDITAR = "CONFIGURACOES.SISTEMAS.EDITAR"
    SISTEMAS_DESATIVAR = "CONFIGURACOES.SISTEMAS.DESATIVAR"
    MANUTENCAO_GERENCIAR = "CONFIGURACOES.MANUTENCAO.GERENCIAR"
    MANUTENCAO_IGNORAR = "CONFIGURACOES.MANUTENCAO.IGNORAR"

    SEGURANCA_GERENCIAR = "SEGURANCA.MODULO.GERENCIAR"
    PERMISSOES_GERENCIAR = "SEGURANCA.PERMISSOES.GERENCIAR"
    PERMISSOES_VISUALIZAR = "SEGURANCA.PERMISSOES.VISUALIZAR"
    PERMISSOES_CRIAR = "SEGURANCA.PERMISSOES.CRIAR"
    PERMISSOES_CONCEDER = "SEGURANCA.PERMISSOES.CONCEDER"
    SESSOES_GERENCIAR = "SEGURANCA.SESSOES.GERENCIAR"
    SESSOES_VISUALIZAR = "SEGURANCA.SESSOES.VISUALIZAR"
    SESSOES_REVOGAR = "SEGURANCA.SESSOES.REVOGAR"
    USUARIOS_DESATIVAR = "SEGURANCA.USUARIOS.DESATIVAR"

    OBSERVABILIDADE_GERENCIAR = "OBSERVABILIDADE.MODULO.GERENCIAR"
    AUDITORIA_VISUALIZAR = "OBSERVABILIDADE.AUDITORIA.VISUALIZAR"
    AUDITORIA_EXPORTAR = "OBSERVABILIDADE.AUDITORIA.EXPORTAR"
    AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR = "OBSERVABILIDADE.DADOS_SENSIVEIS.VISUALIZAR"

    AMBIENTE_GERENCIAR = "AMBIENTE.MODULO.GERENCIAR"
    VARIAVEIS_VISUALIZAR = "AMBIENTE.VARIAVEIS.VISUALIZAR"
    VARIAVEIS_EDITAR = "AMBIENTE.VARIAVEIS.EDITAR"
    SERVICOS_VISUALIZAR = "AMBIENTE.SERVICOS.VISUALIZAR"
    SERVICOS_EXECUTAR = "AMBIENTE.SERVICOS.EXECUTAR"

    CONTEUDO_GERENCIAR = "CONTEUDO.MODULO.GERENCIAR"
    COMUNICADOS_GERENCIAR = "CONTEUDO.COMUNICADOS.GERENCIAR"
    COMUNICADOS_VISUALIZAR = "CONTEUDO.COMUNICADOS.VISUALIZAR"
    COMUNICADOS_CRIAR = "CONTEUDO.COMUNICADOS.CRIAR"
    COMUNICADOS_EDITAR = "CONTEUDO.COMUNICADOS.EDITAR"
    COMUNICADOS_PUBLICAR = "CONTEUDO.COMUNICADOS.PUBLICAR"
    COMUNICADOS_ARQUIVAR = "CONTEUDO.COMUNICADOS.ARQUIVAR"
    COMUNICADOS_SINCRONIZAR = "CONTEUDO.COMUNICADOS.SINCRONIZAR"
    ATUALIZACOES_GERENCIAR = "CONTEUDO.ATUALIZACOES.GERENCIAR"
    ATUALIZACOES_VISUALIZAR = "CONTEUDO.ATUALIZACOES.VISUALIZAR"
    ATUALIZACOES_CRIAR = "CONTEUDO.ATUALIZACOES.CRIAR"
    ATUALIZACOES_EDITAR = "CONTEUDO.ATUALIZACOES.EDITAR"
    ATUALIZACOES_PUBLICAR = "CONTEUDO.ATUALIZACOES.PUBLICAR"
    ATUALIZACOES_ARQUIVAR = "CONTEUDO.ATUALIZACOES.ARQUIVAR"

    NOTIFICACOES_GERENCIAR = "NOTIFICACOES.MODULO.GERENCIAR"
    NOTIFICACOES_VISUALIZAR = "NOTIFICACOES.PAINEL.VISUALIZAR"

    DESENVOLVIMENTO_GERENCIAR = "DESENVOLVIMENTO.MODULO.GERENCIAR"
    TESTES_NOTIFICACOES_EXECUTAR = "DESENVOLVIMENTO.NOTIFICACOES.EXECUTAR"
    TESTES_PUBLICACOES_EXECUTAR = "DESENVOLVIMENTO.PUBLICACOES.EXECUTAR"


@dataclass(frozen=True, slots=True)
class DefinicaoModulo:
    """Metadados declarativos de um modulo funcional."""

    codigo: str
    nome: str
    descricao: str
    icone: str
    ordem: int


@dataclass(frozen=True, slots=True)
class DefinicaoPermissao:
    """No declarativo da arvore de permissoes."""

    chave: PermissaoLuftBase
    modulo: str
    recurso: str
    acao: AcaoPermissao
    descricao: str
    pai: PermissaoLuftBase | None = None
    sensivel: bool = False
    acesso_sistema: bool = False
    ordem: int = 0


MODULOS_PADRAO: tuple[DefinicaoModulo, ...] = (
    DefinicaoModulo("PLATAFORMA", "Plataforma", "Acesso e administracao global.", "ph-cube", 10),
    DefinicaoModulo("INICIO", "Inicio", "Pagina inicial e indicadores.", "ph-house", 20),
    DefinicaoModulo(
        "CONFIGURACOES", "Configuracoes", "Catalogo e configuracoes operacionais.", "ph-gear", 30
    ),
    DefinicaoModulo("SEGURANCA", "Seguranca", "Permissoes e sessoes.", "ph-shield-check", 40),
    DefinicaoModulo(
        "OBSERVABILIDADE",
        "Auditoria",
        "Analise de acessos, usuarios, grupos, eventos e diagnosticos.",
        "ph-file-magnifying-glass",
        50,
    ),
    DefinicaoModulo("AMBIENTE", "Ambiente", "Variaveis e servicos.", "ph-terminal-window", 60),
    DefinicaoModulo("CONTEUDO", "Conteudo", "Comunicados e atualizacoes.", "ph-megaphone", 70),
    DefinicaoModulo("NOTIFICACOES", "Notificacoes", "Central de notificacoes.", "ph-bell", 80),
    DefinicaoModulo(
        "DESENVOLVIMENTO",
        "Desenvolvimento",
        "Ferramentas exclusivas de desenvolvimento.",
        "ph-code",
        90,
    ),
)


def _permissao(
    chave: PermissaoLuftBase,
    descricao: str,
    *,
    pai: PermissaoLuftBase | None = None,
    sensivel: bool = False,
    acesso_sistema: bool = False,
    ordem: int = 0,
) -> DefinicaoPermissao:
    modulo, recurso, acao = chave.value.split(".")
    return DefinicaoPermissao(
        chave=chave,
        modulo=modulo,
        recurso=recurso,
        acao=AcaoPermissao(acao),
        descricao=descricao,
        pai=pai,
        sensivel=sensivel,
        acesso_sistema=acesso_sistema,
        ordem=ordem,
    )


_ADMIN = PermissaoLuftBase.SISTEMA_ADMINISTRAR
PERMISSOES_PADRAO: tuple[DefinicaoPermissao, ...] = (
    _permissao(_ADMIN, "Administrar todos os recursos do sistema.", sensivel=True, ordem=10),
    _permissao(
        PermissaoLuftBase.SISTEMA_ACESSAR,
        "Acessar o sistema pelo Hub.",
        pai=_ADMIN,
        acesso_sistema=True,
        ordem=20,
    ),
    _permissao(PermissaoLuftBase.INICIO_GERENCIAR, "Gerenciar o modulo Inicio.", pai=_ADMIN),
    _permissao(
        PermissaoLuftBase.INICIO_VISUALIZAR,
        "Visualizar a pagina inicial.",
        pai=PermissaoLuftBase.INICIO_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.CONFIGURACOES_GERENCIAR,
        "Gerenciar todas as configuracoes.",
        pai=_ADMIN,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.CONFIGURACOES_VISUALIZAR,
        "Visualizar o painel de configuracoes.",
        pai=PermissaoLuftBase.CONFIGURACOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.SISTEMAS_GERENCIAR,
        "Gerenciar o catalogo de sistemas.",
        pai=PermissaoLuftBase.CONFIGURACOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SISTEMAS_VISUALIZAR,
        "Visualizar sistemas.",
        pai=PermissaoLuftBase.SISTEMAS_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.SISTEMAS_CRIAR,
        "Cadastrar sistemas.",
        pai=PermissaoLuftBase.SISTEMAS_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SISTEMAS_EDITAR,
        "Editar sistemas.",
        pai=PermissaoLuftBase.SISTEMAS_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SISTEMAS_DESATIVAR,
        "Descontinuar ou reativar sistemas. Sistemas nunca sao excluidos.",
        pai=PermissaoLuftBase.SISTEMAS_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.MANUTENCAO_GERENCIAR,
        "Gerenciar o modo de manutencao.",
        pai=PermissaoLuftBase.CONFIGURACOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.MANUTENCAO_IGNORAR,
        "Ignorar o modo de manutencao.",
        pai=PermissaoLuftBase.CONFIGURACOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SEGURANCA_GERENCIAR,
        "Gerenciar todo o modulo de seguranca.",
        pai=_ADMIN,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.PERMISSOES_GERENCIAR,
        "Gerenciar regras de acesso.",
        pai=PermissaoLuftBase.SEGURANCA_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.PERMISSOES_VISUALIZAR,
        "Visualizar regras de acesso.",
        pai=PermissaoLuftBase.PERMISSOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.PERMISSOES_CRIAR,
        "Criar modulos e permissoes.",
        pai=PermissaoLuftBase.PERMISSOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.PERMISSOES_CONCEDER,
        "Conceder, negar e restaurar permissoes.",
        pai=PermissaoLuftBase.PERMISSOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SESSOES_GERENCIAR,
        "Gerenciar sessoes autenticadas.",
        pai=PermissaoLuftBase.SEGURANCA_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SESSOES_VISUALIZAR,
        "Visualizar sessoes autenticadas.",
        pai=PermissaoLuftBase.SESSOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.SESSOES_REVOGAR,
        "Revogar sessoes autenticadas.",
        pai=PermissaoLuftBase.SESSOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.USUARIOS_DESATIVAR,
        "Bloquear e desbloquear o login de uma pessoa.",
        pai=PermissaoLuftBase.SEGURANCA_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.OBSERVABILIDADE_GERENCIAR,
        "Gerenciar observabilidade e auditoria.",
        pai=_ADMIN,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.AUDITORIA_VISUALIZAR,
        "Visualizar a trilha de auditoria.",
        pai=PermissaoLuftBase.OBSERVABILIDADE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.AUDITORIA_EXPORTAR,
        "Exportar a trilha de auditoria.",
        pai=PermissaoLuftBase.OBSERVABILIDADE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,
        "Visualizar parametros, alteracoes e rastros tecnicos protegidos.",
        pai=PermissaoLuftBase.OBSERVABILIDADE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.AMBIENTE_GERENCIAR,
        "Gerenciar recursos do ambiente.",
        pai=_ADMIN,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
        "Visualizar variaveis nao secretas.",
        pai=PermissaoLuftBase.AMBIENTE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.VARIAVEIS_EDITAR,
        "Editar variaveis autorizadas.",
        pai=PermissaoLuftBase.AMBIENTE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.SERVICOS_VISUALIZAR,
        "Visualizar servicos do ambiente.",
        pai=PermissaoLuftBase.AMBIENTE_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.SERVICOS_EXECUTAR,
        "Executar comandos de servico autorizados.",
        pai=PermissaoLuftBase.AMBIENTE_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.CONTEUDO_GERENCIAR, "Gerenciar todo o conteudo corporativo.", pai=_ADMIN
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_GERENCIAR,
        "Gerenciar comunicados.",
        pai=PermissaoLuftBase.CONTEUDO_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_VISUALIZAR,
        "Visualizar a administracao de comunicados.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_CRIAR,
        "Criar comunicados.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_EDITAR,
        "Editar comunicados.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_PUBLICAR,
        "Publicar ou agendar comunicados.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_ARQUIVAR,
        "Arquivar comunicados.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.COMUNICADOS_SINCRONIZAR,
        "Sincronizar comunicados externos.",
        pai=PermissaoLuftBase.COMUNICADOS_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
        "Gerenciar notas de atualizacao.",
        pai=PermissaoLuftBase.CONTEUDO_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_VISUALIZAR,
        "Visualizar a administracao das notas de atualizacao.",
        pai=PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_CRIAR,
        "Criar notas de atualizacao.",
        pai=PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_EDITAR,
        "Editar notas de atualizacao.",
        pai=PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_PUBLICAR,
        "Publicar ou agendar notas de atualizacao.",
        pai=PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.ATUALIZACOES_ARQUIVAR,
        "Arquivar notas de atualizacao.",
        pai=PermissaoLuftBase.ATUALIZACOES_GERENCIAR,
    ),
    _permissao(PermissaoLuftBase.NOTIFICACOES_GERENCIAR, "Gerenciar notificacoes.", pai=_ADMIN),
    _permissao(
        PermissaoLuftBase.NOTIFICACOES_VISUALIZAR,
        "Visualizar o painel de notificacoes.",
        pai=PermissaoLuftBase.NOTIFICACOES_GERENCIAR,
    ),
    _permissao(
        PermissaoLuftBase.DESENVOLVIMENTO_GERENCIAR,
        "Executar ferramentas de desenvolvimento.",
        pai=_ADMIN,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.TESTES_NOTIFICACOES_EXECUTAR,
        "Executar testes de notificacoes.",
        pai=PermissaoLuftBase.DESENVOLVIMENTO_GERENCIAR,
        sensivel=True,
    ),
    _permissao(
        PermissaoLuftBase.TESTES_PUBLICACOES_EXECUTAR,
        "Executar testes de publicacoes.",
        pai=PermissaoLuftBase.DESENVOLVIMENTO_GERENCIAR,
        sensivel=True,
    ),
)


ACOES_PERMISSAO: tuple[str, ...] = tuple(acao.value for acao in AcaoPermissao)


__all__ = [
    "ACOES_PERMISSAO",
    "MODULOS_PADRAO",
    "PERMISSOES_PADRAO",
    "AcaoPermissao",
    "DefinicaoModulo",
    "DefinicaoPermissao",
    "PermissaoLuftBase",
]
