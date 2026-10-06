"""Construcao segura e tardia de engines SQLAlchemy."""

from __future__ import annotations

import logging
import threading
import time
import weakref
from dataclasses import dataclass

from sqlalchemy import URL, Engine, create_engine, event

from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, TipoBanco
from luftbase.nucleo.excecoes import ErroConexaoBanco

ESQUEMA_LOGICO_APLICACAO = "luft_aplicacao"
ESQUEMA_CORE = "core"


@dataclass(frozen=True, slots=True)
class ConfiguracaoPool:
    """Limites conservadores compartilhados pelos pools da aplicacao."""

    tamanho: int = 5
    excedentes: int = 5
    reciclagem_segundos: int = 1_800
    timeout_segundos: int = 30
    # Segundos sem uso apos os quais o pool fecha as conexoes ociosas (0 desliga).
    # pool_recycle so renova conexoes no proximo emprestimo; sem isto, uma conexao
    # usada uma vez ficaria aberta (sleeping) no servidor de banco indefinidamente.
    ociosidade_segundos: int = 120

    def __post_init__(self) -> None:
        if self.tamanho < 1:
            raise ValueError("O tamanho do pool deve ser positivo.")
        if self.excedentes < 0:
            raise ValueError("O numero de conexoes excedentes nao pode ser negativo.")
        if self.reciclagem_segundos < 1 or self.timeout_segundos < 1:
            raise ValueError("Reciclagem e timeout do pool devem ser positivos.")
        if self.ociosidade_segundos < 0:
            raise ValueError("A ociosidade do pool nao pode ser negativa.")


def vigiar_ociosidade(
    engine: Engine,
    ociosidade_segundos: float,
    *,
    intervalo_segundos: float | None = None,
) -> threading.Thread | None:
    """Fecha as conexoes do pool quando a engine fica ociosa por ``ociosidade_segundos``.

    O pool do SQLAlchemy nunca encerra uma conexao devolvida: ela continua aberta no banco
    ate o proximo uso. Um vigia (thread daemon) observa emprestimos e devolucoes e, se nada
    foi usado pelo prazo e nao ha conexao emprestada, descarta o pool com ``dispose()``.
    Conexoes em uso nao sao afetadas. A thread termina sozinha quando a engine e coletada.
    Retorna ``None`` quando desligado ou quando o objeto nao e uma engine real.
    """

    if ociosidade_segundos <= 0 or not isinstance(engine, Engine):
        return None

    estado = {"ultimo_uso": time.monotonic()}

    def marcar_uso(*_argumentos: object) -> None:
        estado["ultimo_uso"] = time.monotonic()

    event.listen(engine, "checkout", marcar_uso)
    event.listen(engine, "checkin", marcar_uso)

    referencia = weakref.ref(engine)
    espera = intervalo_segundos or min(30.0, max(ociosidade_segundos / 2, 0.05))

    def vigiar() -> None:
        while True:
            time.sleep(espera)
            alvo = referencia()
            if alvo is None:
                return
            inativo = time.monotonic() - estado["ultimo_uso"] >= ociosidade_segundos
            if inativo and alvo.pool.checkedout() == 0 and alvo.pool.checkedin() > 0:
                alvo.dispose()
            del alvo

    thread = threading.Thread(target=vigiar, name="luftbase-pool-ocioso", daemon=True)
    thread.start()
    return thread


DRIVER_ODBC_PADRAO = "ODBC Driver 18 for SQL Server"
# Do mais novo ao mais antigo. O "SQL Server" legado e o ultimo recurso (sem TLS moderno).
_DRIVERS_ODBC_PREFERIDOS = (
    DRIVER_ODBC_PADRAO,
    "ODBC Driver 17 for SQL Server",
    "ODBC Driver 13 for SQL Server",
    "ODBC Driver 11 for SQL Server",
    "SQL Server Native Client 11.0",
    "SQL Server",
)
_logger = logging.getLogger("luftbase.banco")


def drivers_odbc_instalados() -> tuple[str, ...]:
    """Drivers ODBC visiveis nesta maquina (vazio se o pyodbc nao existir)."""

    try:
        import pyodbc
    except ImportError:
        return ()
    return tuple(pyodbc.drivers())


def resolver_driver_odbc(pedido: str | None, instalados: tuple[str, ...] | None = None) -> str:
    """Devolve o driver pedido se existir; senao o melhor SQL Server instalado.

    O mesmo segredo do Vault serve ao Linux (driver 18) e a um servidor Windows que tenha so o 17,
    sem editar o segredo nem instalar nada. Sem nenhum driver compativel, devolve o pedido e o
    erro nativo do ODBC aparece na conexao.
    """

    desejado = pedido or DRIVER_ODBC_PADRAO
    disponiveis = drivers_odbc_instalados() if instalados is None else instalados
    if not disponiveis or desejado in disponiveis:
        return desejado
    for candidato in _DRIVERS_ODBC_PREFERIDOS:
        if candidato in disponiveis:
            _logger.warning(
                "Driver ODBC %r nao esta instalado; usando %r. Instale o driver pedido ou ajuste "
                "o campo `driver` do segredo no Vault.",
                desejado,
                candidato,
            )
            return candidato
    return desejado


class ConstrutorEngines:
    """Transforma credenciais tipadas em engines sem montar URLs manualmente."""

    def __init__(self, configuracao_pool: ConfiguracaoPool | None = None) -> None:
        self._pool = configuracao_pool or ConfiguracaoPool()

    def criar_url(self, credencial: CredencialBanco) -> URL:
        """Cria uma URL escapada pelo proprio SQLAlchemy."""

        if credencial.tipo is TipoBanco.POSTGRESQL:
            return URL.create(
                drivername="postgresql+psycopg",
                username=credencial.usuario,
                password=credencial.senha.revelar(),
                host=credencial.host,
                port=credencial.porta,
                database=credencial.nome_banco,
                query={"sslmode": credencial.sslmode or "prefer"},
            )
        if credencial.tipo is TipoBanco.SQLSERVER:
            driver = resolver_driver_odbc(credencial.driver)
            consulta = {"driver": driver}
            if driver != "SQL Server":  # o driver legado nao entende estes parametros
                consulta.update({"Encrypt": "yes", "TrustServerCertificate": "yes"})
            return URL.create(
                drivername="mssql+pyodbc",
                username=credencial.usuario,
                password=credencial.senha.revelar(),
                host=credencial.host,
                port=credencial.porta,
                database=credencial.nome_banco,
                query=consulta,
            )
        if credencial.tipo is TipoBanco.ORACLE:
            # Mesmo formato do legado: o nome do banco (SID/servico) vai no caminho da URL.
            # O driver (python-oracledb) e dependencia de quem usa Oracle, nao do LuftBase.
            return URL.create(
                drivername=f"oracle+{credencial.driver or 'oracledb'}",
                username=credencial.usuario,
                password=credencial.senha.revelar(),
                host=credencial.host,
                port=credencial.porta,
                database=credencial.nome_banco,
            )
        raise ErroConexaoBanco("O tipo de banco nao possui um adaptador registrado.")

    def criar(self, credencial: CredencialBanco, *, somente_leitura: bool = False) -> Engine:
        """Cria uma engine com verificacao de conexao e pool limitado.

        `somente_leitura=True` em SQL Server liga o autocommit do driver. No modo padrao o driver
        ODBC mantem uma transacao SEMPRE aberta na conexao (inclusive ociosa no pool), que aparece
        nos monitores como sessao "sleeping" com transacao aberta. Quem so le (diretorio de
        usuarios, ERP) nao precisa de transacao, entao nenhuma fica aberta.
        """

        opcoes: dict[str, object] = {}
        if somente_leitura and credencial.tipo is TipoBanco.SQLSERVER:
            opcoes["isolation_level"] = "AUTOCOMMIT"
        engine = create_engine(
            self.criar_url(credencial),
            **opcoes,
            pool_pre_ping=True,
            pool_size=self._pool.tamanho,
            max_overflow=self._pool.excedentes,
            pool_recycle=self._pool.reciclagem_segundos,
            pool_timeout=self._pool.timeout_segundos,
        )
        vigiar_ociosidade(engine, self._pool.ociosidade_segundos)
        return engine

    def para_aplicacao(self, engine: Engine, esquema: str) -> Engine:
        """Vincula o schema logico dos modelos ao schema particular do segredo."""

        if not esquema:
            raise ErroConexaoBanco("A engine da aplicacao exige um schema validado.")
        return engine.execution_options(schema_translate_map={ESQUEMA_LOGICO_APLICACAO: esquema})
