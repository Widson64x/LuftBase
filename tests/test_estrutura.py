"""Testes das politicas explicitas para models particulares."""

import pytest
from sqlalchemy import Integer, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from luftbase.estrutura import (
    CatalogoEstruturas,
    DefinicaoModelo,
    OrigemDados,
    PoliticaEstrutura,
)
from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroInicializacao


class BaseTeste(DeclarativeBase):
    pass


class ItemGerenciado(BaseTeste):
    __tablename__ = "tb_item_gerenciado"
    __politica_estrutura__ = PoliticaEstrutura.GERENCIAR

    id_item: Mapped[int] = mapped_column(Integer, primary_key=True)


class ItemValidado(BaseTeste):
    __tablename__ = "tb_item_validado"

    id_item: Mapped[int] = mapped_column(Integer, primary_key=True)


def _catalogo(*definicoes: DefinicaoModelo) -> CatalogoEstruturas:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    banco = BancoSQLAlchemy("teste", engine)
    diretorio = BancoSQLAlchemy("diretorio", engine, somente_leitura=True)
    return CatalogoEstruturas(
        CatalogoBancos(diretorio=diretorio, core=banco, aplicacao=banco),
        definicoes,
    )


def test_verifica_e_cria_somente_modelo_gerenciado() -> None:
    gerenciado = DefinicaoModelo.de_modelo(ItemGerenciado)
    validado = DefinicaoModelo.de_modelo(ItemValidado)
    catalogo = _catalogo(gerenciado, validado)

    assert all(not estado.existe for estado in catalogo.verificar())

    catalogo.criar("ItemGerenciado")

    estados = {estado.nome: estado for estado in catalogo.verificar()}
    assert estados["ItemGerenciado"].existe is True
    assert estados["ItemValidado"].existe is False
    with pytest.raises(ErroInicializacao, match="nao permite criacao"):
        catalogo.criar("ItemValidado")


def test_sqlserver_exige_politica_externa_somente_leitura() -> None:
    with pytest.raises(ValueError, match="EXTERNA_SOMENTE_LEITURA"):
        DefinicaoModelo.de_modelo(
            ItemValidado,
            origem=OrigemDados.DIRETORIO,
            politica=PoliticaEstrutura.GERENCIAR,
        )

    definicao = DefinicaoModelo.de_modelo(
        ItemValidado,
        origem=OrigemDados.DIRETORIO,
        politica=PoliticaEstrutura.EXTERNA_SOMENTE_LEITURA,
    )
    with pytest.raises(ErroInicializacao, match="nao permite criacao"):
        _catalogo(definicao).criar("ItemValidado")


def test_verificar_traduz_schema_logico_da_aplicacao() -> None:
    from types import SimpleNamespace

    from sqlalchemy import Column, Integer, MetaData, Table, create_engine

    from luftbase.estrutura.catalogo import CatalogoEstruturas
    from luftbase.estrutura.modelos import DefinicaoModelo, OrigemDados, PoliticaEstrutura

    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conexao:
        conexao.exec_driver_sql("ATTACH DATABASE ':memory:' AS real_app")
        conexao.exec_driver_sql("CREATE TABLE real_app.tb_pedido (id INTEGER PRIMARY KEY)")
    engine_app = engine.execution_options(schema_translate_map={"luft_aplicacao": "real_app"})
    tabela = Table(
        "tb_pedido", MetaData(schema="luft_aplicacao"), Column("id", Integer, primary_key=True)
    )
    bancos = SimpleNamespace(aplicacao=SimpleNamespace(engine=engine_app, somente_leitura=False))
    catalogo = CatalogoEstruturas(
        bancos,  # type: ignore[arg-type]
        [DefinicaoModelo("Pedido", tabela, OrigemDados.APLICACAO, PoliticaEstrutura.VALIDAR)],
        incluir_core=False,
    )

    (estado,) = catalogo.verificar()

    assert estado.existe is True
