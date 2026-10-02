"""Repositorio de consulta e validacao do sistema em core.tb_sistema."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from luftbase.configuracao.modelos import MetadadosSistema
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroInicializacao
from luftbase.persistencia.core.seguranca import Sistema


class RepositorioSistemas:
    """Consulta o catalogo oficial de sistemas no schema core."""

    def __init__(self, banco_core: BancoSQLAlchemy) -> None:
        self._banco = banco_core

    def consultar_por_id(self, sistema_id: int) -> MetadadosSistema:
        """Carrega os metadados do sistema a partir da chave primaria id_sistema."""

        consulta = select(
            Sistema.id_sistema,
            Sistema.nome_sistema,
            Sistema.descricao_sistema,
            Sistema.ativo,
            Sistema.em_manutencao,
            Sistema.icone,
            Sistema.link,
        ).where(Sistema.id_sistema == sistema_id)

        try:
            with self._banco.leitura() as sessao:
                linha = sessao.execute(consulta).one_or_none()
        except Exception as erro:
            raise ErroInicializacao(
                f"Nao foi possivel consultar core.tb_sistema pelo id_sistema {sistema_id}. "
                "Verifique a conectividade e privilegios da role da aplicacao."
            ) from erro

        if linha is None:
            raise ErroInicializacao(
                f"O sistema_id {sistema_id} nao foi encontrado em core.tb_sistema."
            )

        return self._montar_metadados(linha, f"sistema_id {sistema_id}")

    def _montar_metadados(
        self,
        linha: Any,
        origem: str,
    ) -> MetadadosSistema:
        if linha.ativo is False:
            raise ErroInicializacao(
                f"A aplicacao {origem} ({linha.nome_sistema}) esta inativa no catalogo corporativo."
            )

        return MetadadosSistema(
            sistema_id=int(linha.id_sistema),
            nome=str(linha.nome_sistema),
            descricao=str(linha.descricao_sistema) if linha.descricao_sistema else None,
            ativo=bool(linha.ativo is not False),
            em_manutencao=bool(linha.em_manutencao),
            icone=str(linha.icone) if linha.icone else None,
            link=str(linha.link) if linha.link else None,
        )
