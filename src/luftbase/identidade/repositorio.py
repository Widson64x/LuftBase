"""Consultas minimas do diretorio corporativo."""

from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import joinedload

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.persistencia.diretorio import UsuarioDiretorio


class RepositorioUsuariosDiretorio:
    """Carrega identidades pelo acesso SQL Server marcado como somente leitura."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        if not banco.somente_leitura:
            raise ValueError("O repositorio exige a fronteira de diretorio somente leitura.")
        self._banco = banco

    def obter_por_id(self, id_usuario: int) -> UsuarioAutenticado | None:
        """Busca um usuario por chave sem manter objetos ligados a sessao."""

        declaracao = (
            select(UsuarioDiretorio)
            .options(joinedload(UsuarioDiretorio.grupo))
            .where(UsuarioDiretorio.id_usuario == id_usuario)
        )
        return self._executar(declaracao)

    def obter_por_login(self, identificador: str) -> UsuarioAutenticado | None:
        """Busca por login ou e-mail sem carregar tabelas de menu ou permissao."""

        valor = identificador.strip().casefold()
        if not valor:
            return None
        declaracao = (
            select(UsuarioDiretorio)
            .options(joinedload(UsuarioDiretorio.grupo))
            .where(
                or_(
                    func.lower(UsuarioDiretorio.login) == valor,
                    func.lower(UsuarioDiretorio.email) == valor,
                )
            )
        )
        return self._executar(declaracao)

    def _executar(
        self,
        declaracao: Select[tuple[UsuarioDiretorio]],
    ) -> UsuarioAutenticado | None:
        with self._banco.leitura() as sessao:
            usuario = sessao.scalars(declaracao).first()
            if usuario is None:
                return None
            grupo = usuario.grupo
            return UsuarioAutenticado(
                id_usuario=usuario.id_usuario,
                login=(usuario.login or "").strip(),
                nome_completo=(usuario.nome_completo or usuario.login or "").strip(),
                email=(usuario.email or "").strip() or None,
                id_grupo=usuario.id_grupo,
                nome_grupo=(grupo.sigla or "").strip() or None if grupo else None,
            )
