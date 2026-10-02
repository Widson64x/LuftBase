"""Testes da protecao compativel de tokens do Vault."""

import pytest

from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.nucleo.excecoes import ErroCofre


def test_proteger_e_revelar_token() -> None:
    desprotetor = DesprotetorFernet("chave-do-ambiente")

    protegido = desprotetor.proteger("token-do-vault")

    assert protegido != "token-do-vault"
    assert desprotetor.revelar(protegido) == "token-do-vault"


def test_chave_incorreta_nao_expoe_token() -> None:
    protegido = DesprotetorFernet("chave-correta").proteger("token-supersecreto")

    with pytest.raises(ErroCofre) as captura:
        DesprotetorFernet("chave-incorreta").revelar(protegido)

    assert "token-supersecreto" not in str(captura.value)


def test_rejeita_chave_vazia() -> None:
    with pytest.raises(ErroCofre, match="chave de acesso"):
        DesprotetorFernet("  ")
