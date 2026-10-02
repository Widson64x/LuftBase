"""Operacoes administrativas sobre os segredos de sistemas no Vault (KV v2).

Exigem um token de operador informado no momento da operacao; o runtime das aplicacoes usa
somente tokens de leitura e nunca chega aqui.
"""

from __future__ import annotations

from typing import Any

from luftbase.configuracao.ambientes import Ambiente, normalizar_ambiente


def raiz_segredos_sistemas(ambiente: Ambiente | str, namespace: str = "luft") -> str:
    """Pasta com um segredo por sistema: `{namespace}/{ambiente}/bancos/postgresql/sistemas`."""

    return f"{namespace}/{normalizar_ambiente(ambiente).value}/bancos/postgresql/sistemas"


def listar_segredos_sistemas(
    cliente: Any, mount: str, ambiente: Ambiente | str, namespace: str = "luft"
) -> list[str]:
    """Nomes das chaves existentes na pasta (ids dos sistemas); vazio se a pasta nao existe."""

    from hvac import exceptions as excecoes_vault

    try:
        resposta = cliente.secrets.kv.v2.list_secrets(
            path=raiz_segredos_sistemas(ambiente, namespace), mount_point=mount
        )
    except excecoes_vault.InvalidPath:
        return []
    return sorted(str(chave) for chave in resposta["data"]["keys"])


def remover_segredo_sistema(
    cliente: Any,
    mount: str,
    ambiente: Ambiente | str,
    sistema_id: int | str,
    namespace: str = "luft",
) -> None:
    """Apaga metadados e todas as versoes; nao ha como recuperar depois."""

    caminho = f"{raiz_segredos_sistemas(ambiente, namespace)}/{sistema_id}"
    cliente.secrets.kv.v2.delete_metadata_and_all_versions(path=caminho, mount_point=mount)


__all__ = ["listar_segredos_sistemas", "raiz_segredos_sistemas", "remover_segredo_sistema"]
