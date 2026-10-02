"""Adaptador HVAC sem conexao de rede durante importacao ou construcao."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.nucleo.excecoes import (
    AutenticacaoCofreInvalida,
    ErroCofre,
    SegredoNaoEncontrado,
)


def _validar_caminho(caminho: str) -> str:
    caminho_limpo = caminho.strip().strip("/")
    partes = caminho_limpo.split("/")
    if not caminho_limpo or any(parte in {"", ".", ".."} for parte in partes):
        raise ErroCofre("O caminho solicitado no Vault e invalido.")
    return caminho_limpo


class ClienteVaultHvac:
    """Implementa acesso KV v2 com erros de infraestrutura controlados."""

    def __init__(
        self,
        endereco: str,
        token: Segredo,
        *,
        cliente: Any | None = None,
        montagem: str = "secret",
    ) -> None:
        self._endereco = endereco.rstrip("/")
        self._token = token
        self._cliente = cliente
        self._montagem = montagem
        self._acesso_validado = False

    def _obter_cliente(self) -> Any:
        if self._cliente is None:
            try:
                import hvac
            except ImportError as erro:
                raise ErroCofre("A dependencia 'hvac' nao esta instalada.") from erro
            self._cliente = hvac.Client(url=self._endereco, token=self._token.revelar())
        return self._cliente

    def validar_acesso(self) -> None:
        """Valida o token somente quando o Vault for realmente utilizado."""

        if self._acesso_validado:
            return
        try:
            autenticado = bool(self._obter_cliente().is_authenticated())
        except AutenticacaoCofreInvalida:
            raise
        except Exception as erro:
            raise ErroCofre("Nao foi possivel validar o acesso ao Vault.") from erro
        if not autenticado:
            raise AutenticacaoCofreInvalida("O token informado nao autentica no Vault.")
        self._acesso_validado = True

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        """Le um segredo KV v2 e normaliza a estrutura devolvida pelo HVAC."""

        caminho_valido = _validar_caminho(caminho)
        self.validar_acesso()
        try:
            resposta = self._obter_cliente().secrets.kv.v2.read_secret_version(
                path=caminho_valido,
                mount_point=self._montagem,
                raise_on_deleted_version=True,
            )
            dados = resposta["data"]["data"]
        except (KeyError, TypeError) as erro:
            raise ErroCofre("O Vault devolveu um payload de segredo invalido.") from erro
        except Exception as erro:
            if erro.__class__.__name__ == "InvalidPath":
                raise SegredoNaoEncontrado(
                    f"O segredo solicitado nao existe no caminho {caminho_valido!r}."
                ) from erro
            if erro.__class__.__name__ in {"Forbidden", "Unauthorized"}:
                raise AutenticacaoCofreInvalida(
                    "O token nao possui acesso ao segredo solicitado."
                ) from erro
            raise ErroCofre("Nao foi possivel ler o segredo no Vault.") from erro
        if not isinstance(dados, Mapping):
            raise ErroCofre("O Vault devolveu dados de segredo em formato invalido.")
        return dados
