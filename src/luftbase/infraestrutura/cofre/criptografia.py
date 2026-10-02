"""Compatibilidade de descriptografia dos tokens atuais do Vault."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from luftbase.nucleo.excecoes import ErroCofre


class DesprotetorFernet:
    """Protege e revela valores usando uma chave derivada por SHA-256.

    A derivacao preserva compatibilidade com os tokens protegidos padrao Luft.
    A chave de acesso continua pertencendo ao ambiente consumidor, nunca ao pacote.
    """

    def __init__(self, chave_acesso: str) -> None:
        chave_limpa = chave_acesso.strip()
        if not chave_limpa:
            raise ErroCofre("A chave de acesso ao token do Vault nao foi informada.")
        resumo = hashlib.sha256(chave_limpa.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(resumo))

    def revelar(self, valor_protegido: str) -> str:
        """Descriptografa um valor sem inclui-lo em mensagens de erro."""

        try:
            return self._fernet.decrypt(valor_protegido.encode("utf-8")).decode("utf-8")
        except (InvalidToken, UnicodeDecodeError) as erro:
            raise ErroCofre("O token protegido do Vault e invalido.") from erro

    def proteger(self, valor: str) -> str:
        """Protege um valor; util para provisionamento e testes controlados."""

        if not valor:
            raise ErroCofre("Nao e possivel proteger um valor vazio.")
        return self._fernet.encrypt(valor.encode("utf-8")).decode("utf-8")
