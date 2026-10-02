"""Contratos que isolam o dominio de credenciais do cliente de Vault."""

from collections.abc import Mapping
from typing import Protocol


class ProvedorSegredos(Protocol):
    """Fonte de segredos cuja implementacao pode ser substituida em testes."""

    def validar_acesso(self) -> None:
        """Confirma que as credenciais do provedor ainda sao validas."""

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        """Le e devolve apenas os dados armazenados no caminho solicitado."""


class DesprotetorSegredo(Protocol):
    """Converte um valor protegido no segredo em memoria usado pelo cliente."""

    def revelar(self, valor_protegido: str) -> str:
        """Revela o valor ou produz um erro controlado, sem registra-lo."""
