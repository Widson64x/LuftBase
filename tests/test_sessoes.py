"""Testes das unidades de trabalho e health checks."""

import pytest
from sqlalchemy import create_engine, text

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroConexaoBanco


def _banco(*, somente_leitura: bool = False) -> BancoSQLAlchemy:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conexao:
        conexao.execute(text("CREATE TABLE itens (id INTEGER PRIMARY KEY, nome TEXT)"))
    return BancoSQLAlchemy("teste", engine, somente_leitura=somente_leitura)


def test_unidade_trabalho_confirma_no_sucesso() -> None:
    banco = _banco()

    with banco.unidade_trabalho() as sessao:
        sessao.execute(text("INSERT INTO itens (nome) VALUES ('confirmado')"))

    with banco.leitura() as sessao:
        quantidade = sessao.scalar(text("SELECT COUNT(*) FROM itens"))
    assert quantidade == 1


def test_unidade_trabalho_desfaz_no_erro() -> None:
    banco = _banco()

    with pytest.raises(RuntimeError, match="falha simulada"), banco.unidade_trabalho() as sessao:
        sessao.execute(text("INSERT INTO itens (nome) VALUES ('descartado')"))
        raise RuntimeError("falha simulada")

    with banco.leitura() as sessao:
        quantidade = sessao.scalar(text("SELECT COUNT(*) FROM itens"))
    assert quantidade == 0


def test_leitura_nunca_confirma_escrita_acidental() -> None:
    banco = _banco()

    with banco.leitura() as sessao:
        sessao.execute(text("INSERT INTO itens (nome) VALUES ('nao confirmar')"))

    with banco.leitura() as sessao:
        quantidade = sessao.scalar(text("SELECT COUNT(*) FROM itens"))
    assert quantidade == 0


def test_banco_somente_leitura_bloqueia_unidade_de_trabalho() -> None:
    banco = _banco(somente_leitura=True)

    with pytest.raises(ErroConexaoBanco, match="apenas para leitura"), banco.unidade_trabalho():
        pass


def test_health_check_disponivel() -> None:
    resultado = _banco().verificar_saude()

    assert resultado.disponivel is True
    assert resultado.codigo == "ok"
    assert resultado.dependencia == "teste"
    assert set(resultado.como_dict()) == {
        "dependencia",
        "disponivel",
        "latencia_ms",
        "codigo",
    }


def test_health_check_nao_vaza_erro_do_driver() -> None:
    banco = _banco()
    banco.engine.dispose()

    resultado = banco.verificar_saude()

    # SQLite em memoria cria outro banco e SELECT 1 ainda funciona; forca a falha
    # substituindo a engine por um colaborador minimo que nao expoe sua mensagem.
    class EngineComFalha:
        def connect(self) -> object:
            raise RuntimeError("senha=nao-pode-vazar")

    banco.engine = EngineComFalha()  # type: ignore[assignment]
    resultado = banco.verificar_saude()
    assert resultado.disponivel is False
    assert resultado.codigo == "indisponivel"
    assert "senha" not in str(resultado.como_dict())


def test_entidade_lida_em_leitura_continua_utilizavel_fora_do_bloco() -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

    class Base(DeclarativeBase):
        pass

    class Item(Base):
        __tablename__ = "itens"
        id: Mapped[int] = mapped_column(primary_key=True)
        nome: Mapped[str]

    banco = _banco()
    with banco.unidade_trabalho() as sessao:
        sessao.execute(text("INSERT INTO itens (nome) VALUES ('lido')"))

    with banco.leitura() as sessao:
        itens = list(sessao.scalars(select(Item)).all())

    # Sem expunge, o rollback do bloco expiraria o objeto e este acesso levantaria
    # DetachedInstanceError.
    assert [(item.id, item.nome) for item in itens] == [(1, "lido")]
