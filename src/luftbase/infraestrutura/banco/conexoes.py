"""Construcao segura e tardia de engines SQLAlchemy."""

from __future__ import annotations

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
            return URL.create(
                drivername="mssql+pyodbc",
                username=credencial.usuario,
                password=credencial.senha.revelar(),
                host=credencial.host,
                port=credencial.porta,
                database=credencial.nome_banco,
                query={
                    "driver": credencial.driver or "ODBC Driver 18 for SQL Server",
                    "Encrypt": "yes",
                    "TrustServerCertificate": "yes",
                },
            )
        raise ErroConexaoBanco("O tipo de banco nao possui um adaptador registrado.")

    def criar(self, credencial: CredencialBanco) -> Engine:
        """Cria uma engine com verificacao de conexao e pool limitado."""

        engine = create_engine(
            self.criar_url(credencial),
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
