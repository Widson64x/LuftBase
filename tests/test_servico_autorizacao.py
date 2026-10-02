"""Testes da politica fail-closed e dos caches de autorizacao."""

import pytest

from luftbase.autorizacao.cache import CacheAutorizacaoRedis
from luftbase.autorizacao.servico import ServicoAutorizacao
from luftbase.identidade import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroAutorizacao


class ArmazenamentoMemoria:
    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        del ttl_segundos
        self.dados[chave] = valor

    def remover(self, chave: str) -> None:
        self.dados.pop(chave, None)


class RepositorioFalso:
    def __init__(self) -> None:
        self.revisao = 1
        self.consultas = 0
        self.resultados = {"RELATORIOS.VER": True}
        self.falhar = False

    def consultar(self, **opcoes: object) -> dict[str, bool]:
        self.consultas += 1
        if self.falhar:
            raise RuntimeError("host=interno senha=vazada")
        chaves = opcoes["chaves"]
        return {chave: self.resultados.get(chave, False) for chave in chaves}  # type: ignore[union-attr]

    def obter_revisao(self) -> int:
        if self.falhar:
            raise RuntimeError("banco indisponivel")
        return self.revisao

    def incrementar_revisao(self) -> int:
        self.revisao += 1
        return self.revisao


def _usuario() -> UsuarioAutenticado:
    return UsuarioAutenticado(2759, "widson", "Widson", None, 7, "TI")


def _servico(repositorio: RepositorioFalso) -> ServicoAutorizacao:
    return ServicoAutorizacao(
        id_sistema=2,
        repositorio=repositorio,
        cache_distribuido=CacheAutorizacaoRedis(
            ArmazenamentoMemoria(),
            ttl_resultado_segundos=300,
            ttl_revisao_segundos=5,
        ),
    )


def test_consulta_somente_chaves_pedidas_e_reutiliza_cache_redis() -> None:
    repositorio = RepositorioFalso()
    servico = _servico(repositorio)

    primeira = servico.consultar(
        _usuario(),
        ["relatorios.ver", "relatorios.desconhecida"],
    )
    segunda = servico.consultar(
        _usuario(),
        ["RELATORIOS.VER", "RELATORIOS.DESCONHECIDA"],
    )

    assert (
        primeira
        == segunda
        == {
            "RELATORIOS.DESCONHECIDA": False,
            "RELATORIOS.VER": True,
        }
    )
    assert repositorio.consultas == 1


def test_nova_revisao_torna_resultado_anterior_inacessivel() -> None:
    repositorio = RepositorioFalso()
    servico = _servico(repositorio)
    assert servico.possui(_usuario(), "RELATORIOS.VER") is True
    repositorio.resultados["RELATORIOS.VER"] = False

    assert servico.invalidar_cache() == 2
    assert servico.possui(_usuario(), "RELATORIOS.VER") is False
    assert repositorio.consultas == 2


def test_falha_de_banco_nunca_concede_permissao() -> None:
    repositorio = RepositorioFalso()
    repositorio.falhar = True
    servico = _servico(repositorio)

    with pytest.raises(ErroAutorizacao) as captura:
        servico.possui(_usuario(), "RELATORIOS.VER")

    assert "senha" not in str(captura.value)
    assert "host" not in str(captura.value)


def test_sistema_global_zero_consulta_permissoes_sem_conceder_por_padrao() -> None:
    repositorio = RepositorioFalso()
    servico = ServicoAutorizacao(
        id_sistema=0,
        repositorio=repositorio,
        cache_distribuido=CacheAutorizacaoRedis(
            ArmazenamentoMemoria(),
            ttl_resultado_segundos=300,
            ttl_revisao_segundos=5,
        ),
    )

    assert servico.possui(_usuario(), "RELATORIOS.VER") is True
    assert servico.possui(_usuario(), "RELATORIOS.DESCONHECIDA") is False
    assert repositorio.consultas == 2
