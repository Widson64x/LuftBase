"""Persistencia PostgreSQL das preferencias visuais."""

from __future__ import annotations

from sqlalchemy import literal_column, select, update

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.interface.modelos import PreferenciaTema
from luftbase.persistencia.core.preferencias import ModoTema
from luftbase.persistencia.core.usuario import Usuario


class RepositorioPreferenciasTema:
    """Le e atualiza somente os campos pertencentes ao design system em core.tb_usuario."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def obter(self, id_usuario: int) -> PreferenciaTema | None:
        """Busca a preferencia sem materializar a entidade inteira."""

        with self._banco.leitura() as sessao:
            linha = sessao.execute(
                select(Usuario.tema_preferido, Usuario.modo_tema).where(
                    Usuario.codigo_usuario == id_usuario
                )
            ).one_or_none()
        if linha is None:
            return None
        tema, modo = linha
        try:
            modo_validado = ModoTema(modo)
        except ValueError:
            modo_validado = ModoTema.SISTEMA
        return PreferenciaTema(tema=tema, modo=modo_validado)

    def salvar(self, id_usuario: int, preferencia: PreferenciaTema) -> None:
        """Atualiza tema e modo_tema no cadastro do usuario."""

        comando = (
            update(Usuario)
            .where(Usuario.codigo_usuario == id_usuario)
            .values(
                tema_preferido=preferencia.tema,
                modo_tema=preferencia.modo.value,
                atualizado_em=literal_column(
                    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
                ),
            )
        )
        with self._banco.unidade_trabalho() as sessao:
            sessao.execute(comando)
