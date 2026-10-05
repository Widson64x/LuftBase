"""Objetos imutaveis que representam credenciais sem vazar senhas."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Segredo:
    """Valor sensivel explicitamente revelado apenas no limite do adaptador."""

    __slots__ = ("_valor",)

    def __init__(self, valor: str) -> None:
        valor_limpo = valor.strip()
        if not valor_limpo:
            raise ValueError("Um segredo nao pode ser vazio.")
        self._valor = valor_limpo

    def revelar(self) -> str:
        """Devolve o valor para um adaptador que realmente precise utiliza-lo."""

        return self._valor

    def __bool__(self) -> bool:
        return True

    def __repr__(self) -> str:
        return "Segredo(********)"

    def __str__(self) -> str:
        return "********"


class TipoBanco(StrEnum):
    """Tipos de banco aceitos pelas credenciais da plataforma."""

    POSTGRESQL = "postgresql"
    SQLSERVER = "sqlserver"
    ORACLE = "oracle"


@dataclass(frozen=True, slots=True)
class CredencialBanco:
    """Credencial validada para a criacao tardia de uma engine SQLAlchemy."""

    tipo: TipoBanco
    host: str
    porta: int
    nome_banco: str
    usuario: str
    senha: Segredo = field(repr=False)
    esquema: str | None = None
    driver: str | None = None
    sslmode: str | None = None


@dataclass(frozen=True, slots=True)
class CredencialPostgresqlAplicacao:
    """Credencial composta e identidade tecnica conferida no segredo do sistema."""

    banco: CredencialBanco
    identificador: str
    sistema_id: int


@dataclass(frozen=True, slots=True)
class CredencialRedis:
    """Credencial validada para sessoes Redis, sem expor valores sensiveis."""

    host: str
    porta: int
    banco: int
    senha: Segredo = field(repr=False)
    chave_assinatura_sessao: Segredo = field(repr=False)
    usuario: str | None = None
    tls: bool = True


class SegurancaSmtp(StrEnum):
    """Modos de protecao do canal SMTP aceitos pela plataforma."""

    STARTTLS = "starttls"
    SSL = "ssl"


@dataclass(frozen=True, slots=True)
class CredencialEmail:
    """Conta SMTP compartilhada pelo ambiente, sem expor a senha."""

    host: str
    porta: int
    seguranca: SegurancaSmtp
    usuario: str
    senha: Segredo = field(repr=False)
    remetente: str
    nome_remetente: str | None = None
    redirecionar_para: tuple[str, ...] = ()
