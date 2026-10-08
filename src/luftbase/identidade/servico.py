"""Caso de uso central de autenticacao corporativa."""

from __future__ import annotations

import logging
from typing import Protocol

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.identidade.repositorio_core import RepositorioUsuariosPostgreSQL
from luftbase.nucleo.excecoes import ErroAutenticacao, ErroUsuarioBloqueado

logger = logging.getLogger("luftbase.identidade")


class AutenticadorCredenciais(Protocol):
    """Fronteira que valida uma credencial no diretorio corporativo."""

    def autenticar(self, login: str, senha: str) -> bool:
        """Informa se a credencial foi aceita."""


class RepositorioIdentidades(Protocol):
    """Fronteira minima para montar o retrato do usuario."""

    def obter_por_login(self, identificador: str) -> UsuarioAutenticado | None:
        """Busca a identidade pelo login ou e-mail informado."""


class ServicoAutenticacao:
    """Coordena LDAP e diretorio sem acoplar a aplicacao aos adaptadores."""

    def __init__(
        self,
        autenticador: AutenticadorCredenciais,
        repositorio: RepositorioIdentidades,
        repositorio_core: RepositorioUsuariosPostgreSQL | None = None,
    ) -> None:
        self._autenticador = autenticador
        self._repositorio = repositorio
        self._repositorio_core = repositorio_core

    @property
    def repositorio_core(self) -> RepositorioUsuariosPostgreSQL | None:
        """Acesso ao repositorio da tabela core.tb_usuario no PostgreSQL."""
        return self._repositorio_core

    def _recusar_se_bloqueado(self, codigo_usuario: int, login: str) -> None:
        """Bloqueio de acesso (fail-closed): na duvida, a pessoa nao entra."""

        assert self._repositorio_core is not None
        try:
            bloqueado = self._repositorio_core.esta_bloqueado(codigo_usuario)
        except Exception as erro:
            logger.error("Nao foi possivel conferir o bloqueio de '%s': %s", login, erro)
            raise ErroAutenticacao("Nao foi possivel conferir o bloqueio do usuario.") from erro
        if bloqueado:
            raise ErroUsuarioBloqueado(f"Acesso bloqueado para '{login}'.")

    def autenticar(self, login: str, senha: str) -> UsuarioAutenticado | None:
        """Valida a senha, carrega o retrato corporativo e sincroniza com o banco local."""

        identificador = login.strip()
        if not identificador or not senha:
            return None

        usuario: UsuarioAutenticado | None = None
        if "@" in identificador:
            usuario = self._repositorio.obter_por_login(identificador)
            if usuario is None or not usuario.login:
                return None
            login_ad = usuario.login
        else:
            login_ad = identificador

        if not self._autenticador.autenticar(login_ad, senha):
            return None

        if usuario is None:
            usuario = self._repositorio.obter_por_login(identificador)

        if usuario is not None and self._repositorio_core is not None:
            self._recusar_se_bloqueado(usuario.id_usuario, usuario.login)
            try:
                registro_core = self._repositorio_core.garantir_usuario_do_diretorio(
                    codigo_usuario=usuario.id_usuario,
                    login_usuario=usuario.login,
                    nome_usuario=usuario.nome_completo,
                    email_usuario=usuario.email,
                    codigo_usuariogrupo=usuario.id_grupo,
                    sigla_usuariogrupo=usuario.nome_grupo,
                )
                usuario = UsuarioAutenticado(
                    id_usuario=usuario.id_usuario,
                    login=usuario.login,
                    nome_completo=registro_core.nome_usuario or usuario.nome_completo,
                    email=usuario.email,
                    id_grupo=usuario.id_grupo,
                    nome_grupo=usuario.nome_grupo,
                    permissoes=usuario.permissoes,
                    foto_perfil=registro_core.foto_perfil,
                    status_online=True,
                    cargo=registro_core.cargo_usuario,
                    departamento=registro_core.departamento_usuario,
                    telefone=registro_core.telefone_usuario,
                    celular=registro_core.celular_usuario,
                    unidade_filial=registro_core.unidade_filial,
                    tema_preferido=registro_core.tema_preferido or "luft",
                    modo_tema=registro_core.modo_tema or "SISTEMA",
                    idioma=registro_core.idioma or "pt-BR",
                )
            except Exception as erro:
                logger.error("Erro ao sincronizar usuario corporativo em core.tb_usuario: %s", erro)

        return usuario
