"""Testes da criacao segura de URLs e engines."""

from typing import Any

import pytest

from luftbase.infraestrutura.banco import conexoes
from luftbase.infraestrutura.banco.conexoes import (
    ESQUEMA_LOGICO_APLICACAO,
    ConfiguracaoPool,
    ConstrutorEngines,
)
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco


def _credencial(tipo: TipoBanco, esquema: str | None = None) -> CredencialBanco:
    return CredencialBanco(
        tipo=tipo,
        host="banco.interno",
        porta=5432 if tipo is TipoBanco.POSTGRESQL else 1433,
        nome_banco="luft_web" if tipo is TipoBanco.POSTGRESQL else "intec",
        usuario="svc_aplicacao",
        senha=Segredo("p@ss:/?#[]"),
        esquema=esquema,
    )


def test_url_postgresql_e_escapada_e_oculta_senha() -> None:
    url = ConstrutorEngines().criar_url(_credencial(TipoBanco.POSTGRESQL, "luft_workspace"))

    assert url.drivername == "postgresql+psycopg"
    assert "p@ss:/?#[]" not in str(url)
    assert "p%40ss%3A%2F%3F%23%5B%5D" in url.render_as_string(hide_password=False)


def test_url_sqlserver_define_driver_seguro() -> None:
    url = ConstrutorEngines().criar_url(_credencial(TipoBanco.SQLSERVER))

    assert url.drivername == "mssql+pyodbc"
    assert url.query["driver"] == "ODBC Driver 18 for SQL Server"
    assert url.query["Encrypt"] == "yes"


def test_url_oracle_usa_oracledb_e_nome_do_banco_no_caminho() -> None:
    url = ConstrutorEngines().criar_url(_credencial(TipoBanco.ORACLE, None))

    assert url.drivername == "oracle+oracledb"
    assert url.database == "intec"
    assert "p@ss:/?#[]" not in str(url)


def test_segredo_oracle_e_aceito_pelo_carregador() -> None:
    from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais

    class Provedor:
        def ler_segredo(self, caminho: str) -> dict[str, str]:
            return {
                "tipo_banco": "oracle",
                "host": "silt.interno",
                "porta": "1521",
                "nome_banco": "SILT",
                "usuario": "consulta_silt",
                "senha": "x",
            }

    credencial = CarregadorCredenciais(Provedor()).carregar_banco(
        "luft/producao/bancos/oracle/conexoes/silt", TipoBanco.ORACLE
    )

    assert credencial.tipo is TipoBanco.ORACLE
    assert credencial.porta == 1521


def test_engine_usa_pool_limitado_e_pre_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    argumentos: dict[str, Any] = {}

    def criar_engine_falsa(url: object, **opcoes: object) -> object:
        argumentos["url"] = url
        argumentos.update(opcoes)
        return object()

    monkeypatch.setattr(conexoes, "create_engine", criar_engine_falsa)
    construtor = ConstrutorEngines(
        ConfiguracaoPool(
            tamanho=7,
            excedentes=2,
            reciclagem_segundos=900,
            timeout_segundos=12,
        )
    )

    construtor.criar(_credencial(TipoBanco.POSTGRESQL, "luft_workspace"))

    assert argumentos["pool_pre_ping"] is True
    assert argumentos["pool_size"] == 7
    assert argumentos["max_overflow"] == 2
    assert argumentos["pool_recycle"] == 900
    assert argumentos["pool_timeout"] == 12


def test_engine_aplicacao_recebe_schema_translate_map() -> None:
    engine = object()
    opcoes: dict[str, object] = {}

    class EngineFalsa:
        def execution_options(self, **argumentos: object) -> object:
            opcoes.update(argumentos)
            return engine

    resultado = ConstrutorEngines().para_aplicacao(  # type: ignore[arg-type]
        EngineFalsa(),
        "luft_workspace",
    )

    assert resultado is engine
    assert opcoes["schema_translate_map"] == {ESQUEMA_LOGICO_APLICACAO: "luft_workspace"}


@pytest.mark.parametrize(
    ("argumentos", "mensagem"),
    [
        ({"tamanho": 0}, "tamanho"),
        ({"excedentes": -1}, "excedentes"),
        ({"timeout_segundos": 0}, "timeout"),
    ],
)
def test_rejeita_configuracao_invalida_de_pool(argumentos: dict[str, int], mensagem: str) -> None:
    with pytest.raises(ValueError, match=mensagem):
        ConfiguracaoPool(**argumentos)


def test_vigia_fecha_conexoes_ociosas_e_preserva_as_em_uso(tmp_path: Any) -> None:
    import time

    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{tmp_path / 'ocioso.db'}")
    # Margens folgadas: sob carga (suite inteira, antivirus) um atraso de 0,3 s derrubava o teste.
    thread = conexoes.vigiar_ociosidade(engine, 1.5, intervalo_segundos=0.1)
    assert thread is not None and thread.daemon

    def esperar(condicao: Any, limite: float = 10.0) -> bool:
        fim = time.monotonic() + limite
        while time.monotonic() < fim:
            if condicao():
                return True
            time.sleep(0.05)
        return False

    with engine.connect() as conexao:
        conexao.execute(text("SELECT 1"))
    assert engine.pool.checkedin() == 1

    # Ociosa e sem emprestimos: o pool e descartado e a conexao fecha no banco.
    assert esperar(lambda: engine.pool.checkedin() == 0)

    # Conexao emprestada por mais tempo que a ociosidade nunca e derrubada.
    with engine.connect() as conexao:
        time.sleep(2.5)
        assert engine.pool.checkedout() == 1
        assert conexao.execute(text("SELECT 2")).scalar() == 2

    # Depois de devolvida, volta a ser considerada ociosa.
    assert esperar(lambda: engine.pool.checkedin() == 0)


def test_vigia_desligado_ou_sem_engine_real_nao_cria_thread() -> None:
    assert conexoes.vigiar_ociosidade(object(), 120) is None  # type: ignore[arg-type]
    assert ConfiguracaoPool(ociosidade_segundos=0).ociosidade_segundos == 0
    with pytest.raises(ValueError, match="ociosidade"):
        ConfiguracaoPool(ociosidade_segundos=-1)


@pytest.mark.parametrize(
    ("tipo", "somente_leitura", "autocommit"),
    [
        (TipoBanco.SQLSERVER, True, True),
        (TipoBanco.SQLSERVER, False, False),
        (TipoBanco.POSTGRESQL, True, False),  # PostgreSQL nunca muda o modo
        (TipoBanco.POSTGRESQL, False, False),
    ],
)
def test_autocommit_so_para_sqlserver_somente_leitura(
    monkeypatch: pytest.MonkeyPatch, tipo: TipoBanco, somente_leitura: bool, autocommit: bool
) -> None:
    capturado: dict[str, Any] = {}

    def falso_create_engine(url: Any, **opcoes: Any) -> Any:
        capturado.update(opcoes)
        return object()

    monkeypatch.setattr(conexoes, "create_engine", falso_create_engine)
    monkeypatch.setattr(conexoes, "vigiar_ociosidade", lambda *_a, **_k: None)
    ConstrutorEngines().criar(_credencial(tipo), somente_leitura=somente_leitura)
    assert (capturado.get("isolation_level") == "AUTOCOMMIT") is autocommit


# ---- Driver ODBC: cai no que o servidor tem -------------------------------------------------


def test_driver_pedido_e_usado_quando_instalado() -> None:
    instalados = ("SQL Server", "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server")

    assert (
        conexoes.resolver_driver_odbc("ODBC Driver 17 for SQL Server", instalados)
        == "ODBC Driver 17 for SQL Server"
    )
    assert conexoes.resolver_driver_odbc(None, instalados) == "ODBC Driver 18 for SQL Server"


def test_sem_o_driver_18_usa_o_17_instalado(caplog: pytest.LogCaptureFixture) -> None:
    # Caso real do servidor Windows de producao: so tem 'SQL Server' e o Driver 17.
    instalados = ("SQL Server", "ODBC Driver 17 for SQL Server", "Qlik-teradata")

    with caplog.at_level("WARNING", logger="luftbase.banco"):
        escolhido = conexoes.resolver_driver_odbc(None, instalados)

    assert escolhido == "ODBC Driver 17 for SQL Server"
    assert "nao esta instalado" in caplog.text


def test_driver_legado_so_como_ultimo_recurso_e_sem_nenhum_devolve_o_pedido() -> None:
    assert conexoes.resolver_driver_odbc(None, ("SQL Server",)) == "SQL Server"
    assert (
        conexoes.resolver_driver_odbc(None, ("Qlik-teradata",)) == "ODBC Driver 18 for SQL Server"
    )
    # sem pyodbc/lista vazia nao ha o que comparar: respeita o pedido
    assert conexoes.resolver_driver_odbc("Outro", ()) == "Outro"


def test_url_sqlserver_usa_o_driver_resolvido_e_so_manda_tls_se_o_driver_entende(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo

    def url_com(instalados: tuple[str, ...]):  # type: ignore[no-untyped-def]
        monkeypatch.setattr(conexoes, "drivers_odbc_instalados", lambda: instalados)
        credencial = CredencialBanco(
            tipo=TipoBanco.SQLSERVER,
            host="h",
            porta=1433,
            nome_banco="b",
            usuario="u",
            senha=Segredo("s"),
        )
        return ConstrutorEngines().criar_url(credencial)

    moderno = url_com(("ODBC Driver 17 for SQL Server",))
    legado = url_com(("SQL Server",))

    assert moderno.query["driver"] == "ODBC Driver 17 for SQL Server"
    assert moderno.query["Encrypt"] == "yes" and moderno.query["TrustServerCertificate"] == "yes"
    assert legado.query["driver"] == "SQL Server" and "Encrypt" not in legado.query
