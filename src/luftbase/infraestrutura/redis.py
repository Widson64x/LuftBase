"""Adaptador Redis para sessoes compartilhadas."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from luftbase.infraestrutura.cofre.credenciais import CredencialRedis
from luftbase.nucleo.excecoes import ErroSessao


class ArmazenamentoSessoesRedis:
    """Persiste sessoes com comandos simples e expiracao obrigatoria."""

    def __init__(self, cliente: Any) -> None:
        self._cliente = cliente

    def obter(self, chave: str) -> bytes | None:
        """Le uma sessao pelo identificador namespaced."""

        valor = self._cliente.get(chave)
        if valor is None:
            return None
        return valor if isinstance(valor, bytes) else str(valor).encode("utf-8")

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        """Grava de forma atomica com TTL."""

        if ttl_segundos <= 0:
            raise ErroSessao("O TTL da sessao deve ser positivo.")
        self._cliente.set(chave, valor, ex=ttl_segundos)

    def remover(self, chave: str) -> None:
        """Revoga uma sessao."""

        self._cliente.delete(chave)

    def verificar_saude(self) -> bool:
        """Executa PING e normaliza o resultado."""

        try:
            return bool(self._cliente.ping())
        except Exception:
            return False


class FabricaClienteRedis:
    """Cria o cliente Redis sem abrir conexao durante a composicao."""

    def __init__(self, construtor_cliente: Callable[..., Any] | None = None) -> None:
        self._construtor_cliente = construtor_cliente

    def criar(self, credencial: CredencialRedis) -> ArmazenamentoSessoesRedis:
        """Configura timeouts, TLS e decodificacao binaria para as sessoes."""

        construtor = self._construtor_cliente
        if construtor is None:
            try:
                from redis import Redis
            except ImportError as erro:
                raise ErroSessao("A dependencia 'redis' nao esta instalada.") from erro
            construtor = Redis

        cliente = construtor(
            host=credencial.host,
            port=credencial.porta,
            db=credencial.banco,
            username=credencial.usuario,
            password=credencial.senha.revelar(),
            ssl=credencial.tls,
            socket_connect_timeout=3,
            socket_timeout=3,
            health_check_interval=30,
            decode_responses=False,
        )
        return ArmazenamentoSessoesRedis(cliente)
