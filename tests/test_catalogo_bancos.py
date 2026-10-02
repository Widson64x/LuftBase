"""Testes da separacao logica entre diretorio, core e aplicacao."""

from sqlalchemy import create_engine

from luftbase.infraestrutura.banco.catalogo import FabricaCatalogoBancos
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco


class ConstrutorFalso:
    """Construtor sem drivers externos para observar a montagem do catalogo."""

    def __init__(self) -> None:
        self.engines = []
        self.esquema: str | None = None

    def criar(self, credencial: CredencialBanco):  # type: ignore[no-untyped-def]
        engine = create_engine("sqlite+pysqlite:///:memory:")
        self.engines.append((credencial.tipo, engine))
        return engine

    def para_aplicacao(self, engine, esquema: str):  # type: ignore[no-untyped-def]
        self.esquema = esquema
        return engine.execution_options(schema_translate_map={"luft_aplicacao": esquema})


def _credencial(tipo: TipoBanco, esquema: str | None = None) -> CredencialBanco:
    return CredencialBanco(
        tipo=tipo,
        host="db",
        porta=1433 if tipo is TipoBanco.SQLSERVER else 5432,
        nome_banco="banco",
        usuario="svc_app",
        senha=Segredo("senha"),
        esquema=esquema,
    )


def test_catalogo_separa_responsabilidades_e_compartilha_pool_postgresql() -> None:
    construtor = ConstrutorFalso()
    catalogo = FabricaCatalogoBancos(construtor).criar(  # type: ignore[arg-type]
        _credencial(TipoBanco.SQLSERVER),
        _credencial(TipoBanco.POSTGRESQL, "luft_workspace"),
    )

    assert catalogo.diretorio.somente_leitura is True
    assert catalogo.core.somente_leitura is False
    assert catalogo.aplicacao.somente_leitura is False
    assert catalogo.core.engine.pool is catalogo.aplicacao.engine.pool
    assert construtor.esquema == "luft_workspace"
    assert len(construtor.engines) == 2
