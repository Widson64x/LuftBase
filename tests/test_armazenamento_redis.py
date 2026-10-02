"""Testes do adaptador Redis sem servidor externo."""

import pytest

from luftbase.infraestrutura.cofre.credenciais import CredencialRedis, Segredo
from luftbase.infraestrutura.redis import ArmazenamentoSessoesRedis, FabricaClienteRedis
from luftbase.nucleo.excecoes import ErroSessao


class RedisFalso:
    """Cliente Redis minimo e observavel."""

    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}
        self.ttl = 0
        self.saudavel = True

    def get(self, chave: str):  # type: ignore[no-untyped-def]
        return self.dados.get(chave)

    def set(self, chave: str, valor: bytes, *, ex: int) -> None:
        self.dados[chave] = valor
        self.ttl = ex

    def delete(self, chave: str) -> None:
        self.dados.pop(chave, None)

    def ping(self) -> bool:
        return self.saudavel


def test_redis_salva_com_ttl_e_remove() -> None:
    cliente = RedisFalso()
    armazenamento = ArmazenamentoSessoesRedis(cliente)

    armazenamento.salvar("luft:sessao:id", b"dados", 1800)

    assert armazenamento.obter("luft:sessao:id") == b"dados"
    assert cliente.ttl == 1800
    armazenamento.remover("luft:sessao:id")
    assert armazenamento.obter("luft:sessao:id") is None


def test_health_redis_e_normalizado() -> None:
    cliente = RedisFalso()
    armazenamento = ArmazenamentoSessoesRedis(cliente)

    assert armazenamento.verificar_saude() is True
    cliente.saudavel = False
    assert armazenamento.verificar_saude() is False


def test_fabrica_configura_cliente_sem_abrir_conexao() -> None:
    chamadas: list[dict[str, object]] = []

    def construir(**opcoes: object) -> RedisFalso:
        chamadas.append(opcoes)
        return RedisFalso()

    credencial = CredencialRedis(
        host="redis.interno",
        porta=6380,
        banco=2,
        usuario="svc_sessoes",
        senha=Segredo("senha"),
        tls=True,
        chave_assinatura_sessao=Segredo("x" * 64),
    )

    armazenamento = FabricaClienteRedis(construir).criar(credencial)

    assert isinstance(armazenamento, ArmazenamentoSessoesRedis)
    assert chamadas == [
        {
            "host": "redis.interno",
            "port": 6380,
            "db": 2,
            "username": "svc_sessoes",
            "password": "senha",
            "ssl": True,
            "socket_connect_timeout": 3,
            "socket_timeout": 3,
            "health_check_interval": 30,
            "decode_responses": False,
        }
    ]


def test_redis_rejeita_ttl_nao_positivo() -> None:
    with pytest.raises(ErroSessao, match="TTL"):
        ArmazenamentoSessoesRedis(RedisFalso()).salvar("chave", b"dados", 0)
