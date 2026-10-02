"""Catalogo de modelos particulares registrado por uma aplicacao."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import inspect

from luftbase.estrutura.modelos import (
    DefinicaoModelo,
    EstadoModelo,
    OrigemDados,
    PoliticaEstrutura,
)
from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroInicializacao


class CatalogoEstruturas:
    """Valida modelos sem misturar DDL ao ciclo de inicializacao web."""

    def __init__(
        self,
        bancos: CatalogoBancos,
        definicoes: Iterable[DefinicaoModelo] = (),
        *,
        incluir_core: bool = True,
    ) -> None:
        self._bancos = bancos
        lista = list(definicoes)
        if incluir_core:
            from luftbase.persistencia.base import BaseLuft

            for tabela in sorted(BaseLuft.metadata.tables.values(), key=lambda t: t.name):
                lista.append(
                    DefinicaoModelo(
                        nome=f"core.{tabela.name}",
                        tabela=tabela,
                        origem=OrigemDados.CORE,
                        politica=PoliticaEstrutura.VALIDAR,
                    )
                )
        self._definicoes = {definicao.nome: definicao for definicao in lista}
        if len(self._definicoes) != len(lista):
            raise ErroInicializacao("Existem modelos duplicados no catalogo de estruturas.")

    def listar(self) -> tuple[DefinicaoModelo, ...]:
        """Retorna as definicoes em ordem deterministica."""

        return tuple(self._definicoes[nome] for nome in sorted(self._definicoes))

    def verificar(self) -> tuple[EstadoModelo, ...]:
        """Consulta apenas metadados dos bancos e informa tabelas ausentes."""

        estados: list[EstadoModelo] = []
        for definicao in self.listar():
            banco = self._banco(definicao.origem)
            if not hasattr(banco, "engine") or banco.engine is None:
                continue
            # O schema logico dos models da aplicacao (ex.: luft_aplicacao) so e trocado pelo real
            # na compilacao de SQL; o Inspector precisa receber o nome ja traduzido.
            traducao = banco.engine.get_execution_options().get("schema_translate_map") or {}
            esquema = traducao.get(definicao.tabela.schema, definicao.tabela.schema)
            try:
                existe = inspect(banco.engine).has_table(
                    definicao.tabela.name,
                    schema=esquema,
                )
            except Exception:
                existe = False
            estados.append(
                EstadoModelo(
                    nome=definicao.nome,
                    tabela=definicao.tabela.fullname,
                    origem=definicao.origem,
                    politica=definicao.politica,
                    existe=existe,
                )
            )
        return tuple(estados)

    def criar(self, nome: str) -> None:
        """Cria uma unica tabela cuja politica autoriza gerenciamento."""

        try:
            definicao = self._definicoes[nome]
        except KeyError as erro:
            raise ErroInicializacao(f"O modelo {nome!r} nao esta registrado.") from erro
        if definicao.politica is not PoliticaEstrutura.GERENCIAR:
            raise ErroInicializacao(f"O modelo {nome!r} nao permite criacao pelo LuftBase.")
        banco = self._banco(definicao.origem)
        if banco.somente_leitura:
            raise ErroInicializacao(
                f"O banco do modelo {nome!r} esta configurado somente para leitura."
            )
        definicao.tabela.create(banco.engine, checkfirst=True)

    def _banco(self, origem: OrigemDados) -> BancoSQLAlchemy:
        if origem is OrigemDados.DIRETORIO:
            return self._bancos.diretorio
        if origem is OrigemDados.CORE:
            return self._bancos.core
        return self._bancos.aplicacao
