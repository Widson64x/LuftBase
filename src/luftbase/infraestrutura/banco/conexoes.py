"""Construcao segura e tardia de engines SQLAlchemy."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import URL, Engine, create_engine

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

    def __post_init__(self) -> None:
        if self.tamanho < 1:
            raise ValueError("O tamanho do pool deve ser positivo.")
        if self.excedentes < 0:
            raise ValueError("O numero de conexoes excedentes nao pode ser negativo.")
        if self.reciclagem_segundos < 1 or self.timeout_segundos < 1:
            raise ValueError("Reciclagem e timeout do pool devem ser positivos.")


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

        return create_engine(
            self.criar_url(credencial),
            pool_pre_ping=True,
            pool_size=self._pool.tamanho,
            max_overflow=self._pool.excedentes,
            pool_recycle=self._pool.reciclagem_segundos,
            pool_timeout=self._pool.timeout_segundos,
        )

    def para_aplicacao(self, engine: Engine, esquema: str) -> Engine:
        """Vincula o schema logico dos modelos ao schema particular do segredo."""

        if not esquema:
            raise ErroConexaoBanco("A engine da aplicacao exige um schema validado.")
        return engine.execution_options(schema_translate_map={ESQUEMA_LOGICO_APLICACAO: esquema})
