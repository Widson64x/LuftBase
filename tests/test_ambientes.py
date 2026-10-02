"""Testes da normalizacao de ambientes."""

import pytest

from luftbase.configuracao import Ambiente, normalizar_ambiente
from luftbase.nucleo import ErroConfiguracao


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("dev", Ambiente.DESENVOLVIMENTO),
        ("development", Ambiente.DESENVOLVIMENTO),
        ("desenvolvimento", Ambiente.DESENVOLVIMENTO),
        ("hml", Ambiente.HOMOLOGACAO),
        ("homologacao", Ambiente.HOMOLOGACAO),
        ("homologação", Ambiente.HOMOLOGACAO),
        ("prd", Ambiente.PRODUCAO),
        ("production", Ambiente.PRODUCAO),
        ("produção", Ambiente.PRODUCAO),
    ],
)
def test_normaliza_aliases(valor: str, esperado: Ambiente) -> None:
    assert normalizar_ambiente(valor) is esperado


def test_rejeita_ambiente_desconhecido() -> None:
    with pytest.raises(ErroConfiguracao, match="Ambiente invalido"):
        normalizar_ambiente("laboratorio")
