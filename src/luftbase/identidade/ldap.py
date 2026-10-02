"""Autenticacao LDAP com transporte criptografado e dependencias injetaveis."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol, cast

from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.nucleo.excecoes import ErroAutenticacao


class TransporteLdap(StrEnum):
    """Transportes LDAP aceitos; conexao em texto puro nao e suportada."""

    LDAPS = "ldaps"
    STARTTLS = "starttls"


@dataclass(frozen=True, slots=True)
class ConfiguracaoLdap:
    """Parametros nao sensiveis de conexao com o diretorio corporativo."""

    servidor: str
    dominio: str
    transporte: TransporteLdap = TransporteLdap.LDAPS
    porta: int | None = None
    timeout_segundos: int = 5

    def __post_init__(self) -> None:
        if not self.servidor.strip() or not self.dominio.strip():
            raise ValueError("Servidor e dominio LDAP sao obrigatorios.")
        porta = self.porta_efetiva
        if not 1 <= porta <= 65535:
            raise ValueError("A porta LDAP esta fora do intervalo valido.")
        if not 1 <= self.timeout_segundos <= 60:
            raise ValueError("O timeout LDAP deve estar entre 1 e 60 segundos.")

    @property
    def porta_efetiva(self) -> int:
        """Resolve a porta segura padrao do transporte escolhido."""

        if self.porta is not None:
            return self.porta
        return 636 if self.transporte is TransporteLdap.LDAPS else 389


class ConexaoLdap(Protocol):
    """Subconjunto da conexao ldap3 usado pelo adaptador."""

    @property
    def closed(self) -> bool:
        """Indica se a conexao fisica esta fechada."""

    def open(self) -> Any:
        """Abre o socket sem autenticar."""

    def start_tls(self) -> bool:
        """Promove o socket para TLS antes do envio de credenciais."""

    def bind(self) -> bool:
        """Tenta autenticar as credenciais configuradas."""

    def unbind(self) -> bool:
        """Encerra a conexao."""


class FabricaConexaoLdap(Protocol):
    """Cria conexoes sem acoplar os testes ao pacote ldap3."""

    def criar(
        self,
        configuracao: ConfiguracaoLdap,
        usuario: str,
        senha: Segredo,
    ) -> ConexaoLdap:
        """Cria uma conexao ainda nao autenticada."""


class FabricaLdap3:
    """Adaptador concreto para a biblioteca ldap3, importada sob demanda."""

    def criar(
        self,
        configuracao: ConfiguracaoLdap,
        usuario: str,
        senha: Segredo,
    ) -> ConexaoLdap:
        """Configura servidor e conexao sem auto-bind inseguro."""

        try:
            import ldap3
        except ImportError as erro:
            raise ErroAutenticacao("A dependencia 'ldap3' nao esta instalada.") from erro

        servidor = ldap3.Server(
            configuracao.servidor,
            port=configuracao.porta_efetiva,
            use_ssl=configuracao.transporte is TransporteLdap.LDAPS,
            connect_timeout=configuracao.timeout_segundos,
            get_info=ldap3.NONE,
        )
        return cast(
            ConexaoLdap,
            ldap3.Connection(
                servidor,
                user=usuario,
                password=senha.revelar(),
                authentication=ldap3.SIMPLE,
                auto_bind=False,
                receive_timeout=configuracao.timeout_segundos,
                raise_exceptions=False,
            ),
        )


class AutenticadorLdap:
    """Valida usuario e senha sem registrar credenciais ou erro bruto do servidor."""

    def __init__(
        self,
        configuracao: ConfiguracaoLdap,
        fabrica: FabricaConexaoLdap | None = None,
    ) -> None:
        self._configuracao = configuracao
        self._fabrica = fabrica or FabricaLdap3()

    def autenticar(self, login: str, senha: str) -> bool:
        """Retorna falso para credencial invalida e erro controlado para indisponibilidade."""

        login_normalizado = self._normalizar_login(login)
        if not login_normalizado or not senha:
            return False
        conexao: ConexaoLdap | None = None
        try:
            conexao = self._fabrica.criar(
                self._configuracao,
                login_normalizado,
                Segredo(senha),
            )
            conexao.open()
            if getattr(conexao, "closed", False):
                raise ErroAutenticacao("Nao foi possivel abrir uma conexao LDAP segura.")
            if self._configuracao.transporte is TransporteLdap.STARTTLS and not conexao.start_tls():
                raise ErroAutenticacao("Nao foi possivel negociar TLS com o servidor LDAP.")
            return bool(conexao.bind())
        except ErroAutenticacao:
            raise
        except Exception as erro:
            raise ErroAutenticacao("O servico de autenticacao esta indisponivel.") from erro
        finally:
            if conexao is not None:
                with suppress(Exception):
                    conexao.unbind()

    def _normalizar_login(self, login: str) -> str:
        valor = login.strip()
        if not valor or "\x00" in valor:
            return ""
        if "@" in valor or "\\" in valor:
            return valor
        return f"{self._configuracao.dominio}\\{valor}"
