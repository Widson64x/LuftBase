"""Testes do repositorio de sistemas do schema core."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroInicializacao
from luftbase.persistencia.core.seguranca import Sistema
from luftbase.persistencia.core.sistemas import RepositorioSistemas


@pytest.fixture
def banco_core_memoria() -> BancoSQLAlchemy:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        execution_options={"schema_translate_map": {"core": None}},
    )
    Sistema.__table__.create(engine)
    with engine.begin() as conexao:
        conexao.execute(
            Sistema.__table__.insert(),
            [
                {
                    "id_sistema": 0,
                    "nome_sistema": "Luft-WorkSpace",
                    "descricao_sistema": "Painel de controle corporativo",
                    "ativo": True,
                    "em_manutencao": False,
                    "icone": "workspace.svg",
                    "link": "/hub",
                },
                {
                    "id_sistema": 4,
                    "nome_sistema": "Luft-MonitorRDP",
                    "descricao_sistema": "Monitor de sessoes legadas",
                    "ativo": False,
                    "em_manutencao": False,
                    "icone": "rdp.svg",
                    "link": "/rdp",
                },
            ],
        )
    return BancoSQLAlchemy("core_postgresql", engine)


def test_consultar_por_id_carrega_metadados_com_sucesso(
    banco_core_memoria: BancoSQLAlchemy,
) -> None:
    repo = RepositorioSistemas(banco_core_memoria)
    meta = repo.consultar_por_id(0)

    assert meta.sistema_id == 0
    assert meta.nome == "Luft-WorkSpace"
    assert meta.descricao == "Painel de controle corporativo"
    assert meta.ativo is True
    assert meta.em_manutencao is False
    assert meta.icone == "workspace.svg"
    assert meta.link == "/hub"


def test_consultar_por_id_rejeita_sistema_inexistente(
    banco_core_memoria: BancoSQLAlchemy,
) -> None:
    repo = RepositorioSistemas(banco_core_memoria)
    with pytest.raises(ErroInicializacao, match="nao foi encontrado"):
        repo.consultar_por_id(99)


def test_consultar_por_id_rejeita_sistema_inativo(
    banco_core_memoria: BancoSQLAlchemy,
) -> None:
    repo = RepositorioSistemas(banco_core_memoria)
    with pytest.raises(ErroInicializacao, match="inativa"):
        repo.consultar_por_id(4)
