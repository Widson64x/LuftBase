"""Identidade corporativa independente de ORM, Flask e LDAP."""

from luftbase.identidade.ldap import (
    AutenticadorLdap,
    ConfiguracaoLdap,
    TransporteLdap,
)
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.identidade.repositorio import RepositorioUsuariosDiretorio
from luftbase.identidade.repositorio_core import RepositorioUsuariosPostgreSQL
from luftbase.identidade.servico import ServicoAutenticacao
from luftbase.identidade.sessoes import (
    InterfaceSessaoCompartilhada,
    carregar_usuario_sessao,
    descartar_cookie_lembrar,
    encerrar_sessao_global,
    iniciar_sessao_usuario,
    revogar_sessao_atual,
    rotacionar_sessao,
)

__all__ = [
    "AutenticadorLdap",
    "ConfiguracaoLdap",
    "InterfaceSessaoCompartilhada",
    "RepositorioUsuariosDiretorio",
    "RepositorioUsuariosPostgreSQL",
    "ServicoAutenticacao",
    "TransporteLdap",
    "UsuarioAutenticado",
    "carregar_usuario_sessao",
    "descartar_cookie_lembrar",
    "encerrar_sessao_global",
    "iniciar_sessao_usuario",
    "revogar_sessao_atual",
    "rotacionar_sessao",
]
