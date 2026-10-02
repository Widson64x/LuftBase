"""Contratos explicitos para validar e, quando permitido, criar tabelas."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from sqlalchemy import Table


class OrigemDados(StrEnum):
    """Fronteira de banco que contem o modelo."""

    CORE = "core"
    APLICACAO = "aplicacao"
    DIRETORIO = "diretorio"


class PoliticaEstrutura(StrEnum):
    """Nivel de autoridade do LuftBase sobre a tabela."""

    EXTERNA_SOMENTE_LEITURA = "externa_somente_leitura"
    VALIDAR = "validar"
    GERENCIAR = "gerenciar"


@dataclass(frozen=True, slots=True)
class DefinicaoModelo:
    """Associa uma tabela a sua origem e politica operacional."""

    nome: str
    tabela: Table
    origem: OrigemDados
    politica: PoliticaEstrutura

    @classmethod
    def de_modelo(
        cls,
        modelo: type[Any],
        *,
        origem: OrigemDados = OrigemDados.APLICACAO,
        politica: PoliticaEstrutura | None = None,
    ) -> DefinicaoModelo:
        """Cria a definicao a partir de um model SQLAlchemy declarativo."""

        tabela = getattr(modelo, "__table__", None)
        if not isinstance(tabela, Table):
            raise TypeError("O modelo deve possuir uma tabela SQLAlchemy declarativa.")
        politica_modelo: object = politica or getattr(
            modelo,
            "__politica_estrutura__",
            PoliticaEstrutura.VALIDAR,
        )
        politica_resolvida = PoliticaEstrutura(str(politica_modelo))
        if (
            origem is OrigemDados.DIRETORIO
            and politica_resolvida is not PoliticaEstrutura.EXTERNA_SOMENTE_LEITURA
        ):
            raise ValueError("Modelos do diretorio SQL Server devem ser EXTERNA_SOMENTE_LEITURA.")
        if origem is OrigemDados.CORE and politica_resolvida is PoliticaEstrutura.GERENCIAR:
            raise ValueError("Tabelas do schema core devem usar migrations e politica VALIDAR.")
        return cls(
            nome=modelo.__name__,
            tabela=tabela,
            origem=origem,
            politica=politica_resolvida,
        )


@dataclass(frozen=True, slots=True)
class EstadoModelo:
    """Resultado sanitizado da verificacao de uma tabela."""

    nome: str
    tabela: str
    origem: OrigemDados
    politica: PoliticaEstrutura
    existe: bool
