"""Transportes de envio: SMTP real e memoria para testes."""

from __future__ import annotations

import smtplib
import ssl
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from email.message import EmailMessage
from typing import Protocol

from luftbase.infraestrutura.cofre.credenciais import CredencialEmail, SegurancaSmtp


class ConexaoEmail(Protocol):
    """Conexao aberta capaz de entregar varias mensagens em sequencia."""

    def enviar(self, mensagem: EmailMessage, destinatarios: Sequence[str]) -> Mapping[str, object]:
        """Entrega a mensagem e devolve os enderecos recusados pelo servidor."""


class TransporteEmail(Protocol):
    """Fonte de conexoes substituivel em testes."""

    def conectar(self) -> AbstractContextManager[ConexaoEmail]:
        """Abre uma sessao que e encerrada ao sair do bloco `with`."""


class _ConexaoSmtp:
    def __init__(self, servidor: smtplib.SMTP) -> None:
        self._servidor = servidor

    def enviar(self, mensagem: EmailMessage, destinatarios: Sequence[str]) -> Mapping[str, object]:
        return self._servidor.send_message(mensagem, to_addrs=list(destinatarios))


class TransporteSmtp:
    """Abre uma sessao SMTP autenticada por lote, com TLS obrigatorio."""

    def __init__(
        self,
        credencial: CredencialEmail,
        *,
        timeout_segundos: float = 30.0,
        construtor_smtp: Callable[..., smtplib.SMTP] | None = None,
        construtor_smtp_ssl: Callable[..., smtplib.SMTP] | None = None,
    ) -> None:
        self._credencial = credencial
        self._timeout = timeout_segundos
        self._construtor_smtp = construtor_smtp or smtplib.SMTP
        self._construtor_smtp_ssl = construtor_smtp_ssl or smtplib.SMTP_SSL

    @contextmanager
    def conectar(self) -> Iterator[ConexaoEmail]:
        """Conecta, protege o canal e autentica antes de liberar a conexao."""

        credencial = self._credencial
        contexto = ssl.create_default_context()
        if credencial.seguranca is SegurancaSmtp.SSL:
            servidor = self._construtor_smtp_ssl(
                credencial.host, credencial.porta, timeout=self._timeout, context=contexto
            )
        else:
            servidor = self._construtor_smtp(
                credencial.host, credencial.porta, timeout=self._timeout
            )

        with servidor:
            servidor.ehlo()
            if credencial.seguranca is SegurancaSmtp.STARTTLS:
                servidor.starttls(context=contexto)
                servidor.ehlo()
            servidor.login(credencial.usuario, credencial.senha.revelar())
            yield _ConexaoSmtp(servidor)


class _ConexaoMemoria:
    def __init__(self, transporte: TransporteMemoria) -> None:
        self._transporte = transporte

    def enviar(self, mensagem: EmailMessage, destinatarios: Sequence[str]) -> Mapping[str, object]:
        if self._transporte.falha_envio is not None:
            raise self._transporte.falha_envio
        self._transporte.enviadas.append((mensagem, tuple(destinatarios)))
        return {
            endereco: (550, b"recusado")
            for endereco in destinatarios
            if endereco in self._transporte.recusar
        }


class TransporteMemoria:
    """Guarda as mensagens em memoria; permite simular falhas e recusas."""

    def __init__(
        self,
        *,
        recusar: Sequence[str] = (),
        falha_conexao: Exception | None = None,
        falha_envio: Exception | None = None,
    ) -> None:
        self.enviadas: list[tuple[EmailMessage, tuple[str, ...]]] = []
        self.conexoes = 0
        self.recusar = frozenset(recusar)
        self.falha_conexao = falha_conexao
        self.falha_envio = falha_envio

    @contextmanager
    def conectar(self) -> Iterator[ConexaoEmail]:
        """Simula a abertura de uma sessao."""

        if self.falha_conexao is not None:
            raise self.falha_conexao
        self.conexoes += 1
        yield _ConexaoMemoria(self)
