"""Espelho do Vault de desenvolvimento: um segredo por sistema do core copiado.

Depois de `banco espelhar`, o core local tem os sistemas de homologacao, mas o Vault de
desenvolvimento nao tem os segredos deles (`bancos/postgresql/sistemas/<id>`), e sem eles nenhuma
aplicacao sobe em desenvolvimento. Para cada sistema com schema proprio este modulo cria a role
`luft_<schema>_dev_app` com senha nova, da acesso ao core e ao schema, e grava o segredo.

Regras de seguranca:

- Escreve so em `desenvolvimento`; o ambiente de origem (homologacao) nunca e tocado.
- Segredo que ja existe e bate (mesmo schema e mesma role) e mantido como esta.
- Segredo que existe mas aponta para outro schema ou role e um conflito: nada e alterado sem
  `substituir`.
- A senha da role nasce aleatoria, vai direto para o Vault e nunca e mostrada nem registrada.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from luftbase.infraestrutura.provisionamento_sistema import (
    ErroProvisionamento,
    ProvisionadorSistema,
    derivar_plano,
)

AMBIENTE_DO_VAULT = "desenvolvimento"


@dataclass(frozen=True, slots=True)
class SistemaLocal:
    """Sistema lido do core copiado."""

    id_sistema: int
    nome: str
    esquema: str


@dataclass(slots=True)
class ResultadoVault:
    criados: list[int]
    mantidos: list[int]
    conflitos: list[str]
    falhas: list[str]


def ler_sistemas_locais(conexao: Any) -> list[SistemaLocal]:
    """Sistemas do core copiado que tem schema proprio, em ordem de ID."""

    with conexao.cursor() as cursor:
        cursor.execute(
            "SELECT id_sistema, nome_sistema, schema_aplicacao FROM core.tb_sistema "
            "WHERE schema_aplicacao IS NOT NULL ORDER BY id_sistema"
        )
        return [SistemaLocal(int(i), str(n), str(e)) for i, n, e in cursor.fetchall()]


def espelhar_vault(
    provisionador: ProvisionadorSistema,
    sistemas: Sequence[SistemaLocal],
    alias_conexao: str,
    *,
    substituir: bool = False,
    ao_etapa: Callable[[str], None] | None = None,
) -> ResultadoVault:
    """Cria role e segredo de desenvolvimento para cada sistema que ainda nao os tem."""

    def avisar(texto: str) -> None:
        if ao_etapa is not None:
            ao_etapa(texto)

    if provisionador.ambiente != AMBIENTE_DO_VAULT:
        raise ErroProvisionamento(
            f"O espelho do Vault so escreve em {AMBIENTE_DO_VAULT!r}, "
            f"nao em {provisionador.ambiente!r}."
        )
    resultado = ResultadoVault([], [], [], [])
    for sistema in sistemas:
        try:
            plano = derivar_plano(
                sistema.id_sistema, sistema.nome, sistema.esquema, AMBIENTE_DO_VAULT
            )
            existente = provisionador.ler_segredo(sistema.id_sistema)
            if existente is not None:
                if (existente.get("esquema"), existente.get("usuario")) == (
                    plano.esquema,
                    plano.role,
                ):
                    resultado.mantidos.append(sistema.id_sistema)
                    avisar(f"Sistema {sistema.id_sistema} ({sistema.nome}): segredo mantido.")
                    continue
                if not substituir:
                    resultado.conflitos.append(
                        f"Sistema {sistema.id_sistema} ({sistema.nome}): o Vault tem outro schema "
                        f"ou role em sistemas/{sistema.id_sistema}; use --substituir-segredos."
                    )
                    continue
            senha, _ = provisionador.provisionar_banco(plano)
            provisionador.gravar_segredo(
                plano, alias_conexao, senha, substituir=existente is not None
            )
        except ErroProvisionamento as falha:
            resultado.falhas.append(f"Sistema {sistema.id_sistema}: {falha.mensagem}")
            continue
        except Exception as erro:
            # So o tipo: a mensagem de erro do Vault ou do banco pode citar valores sensiveis.
            resultado.falhas.append(
                f"Sistema {sistema.id_sistema} ({sistema.nome}): {type(erro).__name__}"
            )
            continue
        resultado.criados.append(sistema.id_sistema)
        avisar(
            f"Sistema {sistema.id_sistema} ({sistema.nome}): role {plano.role} e segredo criados."
        )
    return resultado


__all__ = [
    "AMBIENTE_DO_VAULT",
    "ResultadoVault",
    "SistemaLocal",
    "espelhar_vault",
    "ler_sistemas_locais",
]
