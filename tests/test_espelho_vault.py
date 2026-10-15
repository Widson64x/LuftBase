"""Espelho do Vault de desenvolvimento: um segredo por sistema do core copiado."""

from __future__ import annotations

from typing import Any

import pytest

from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.espelho_vault import (
    SistemaLocal,
    espelhar_vault,
    ler_sistemas_locais,
)
from luftbase.infraestrutura.provisionamento_sistema import (
    ErroProvisionamento,
    PlanoSistema,
)


class ProvisionadorFalso:
    """Faz o papel do ProvisionadorSistema: guarda o que seria criado, sem banco nem Vault."""

    def __init__(self, segredos: dict[int, dict[str, Any]] | None = None) -> None:
        self.ambiente = "desenvolvimento"
        self.segredos = segredos or {}
        self.planos: list[PlanoSistema] = []
        self.gravados: list[tuple[int, str, bool]] = []
        self.falhar_em: set[int] = set()

    def ler_segredo(self, sistema_id: int) -> dict[str, Any] | None:
        return self.segredos.get(sistema_id)

    def provisionar_banco(self, plano: PlanoSistema) -> tuple[Segredo, bool]:
        if plano.sistema_id in self.falhar_em:
            raise ErroProvisionamento("sem permissao para criar a role")
        self.planos.append(plano)
        return Segredo("senha-aleatoria"), False

    def gravar_segredo(
        self, plano: PlanoSistema, alias: str, senha: Segredo, *, substituir: bool = False
    ) -> str:
        self.gravados.append((plano.sistema_id, alias, substituir))
        return f"sistemas/{plano.sistema_id}"


def _sistemas() -> list[SistemaLocal]:
    return [
        SistemaLocal(0, "Luft-Workspace", "workspace"),
        SistemaLocal(1, "Luft-ConnectAir", "connectair"),
    ]


def test_cria_role_e_segredo_para_cada_sistema_sem_segredo() -> None:
    provisionador = ProvisionadorFalso()
    etapas: list[str] = []

    resultado = espelhar_vault(
        provisionador,  # type: ignore[arg-type]
        _sistemas(),
        "luft-web",
        ao_etapa=etapas.append,
    )

    assert resultado.criados == [0, 1]
    assert [p.role for p in provisionador.planos] == [
        "luft_workspace_dev_app",
        "luft_connectair_dev_app",
    ]
    assert provisionador.gravados == [(0, "luft-web", False), (1, "luft-web", False)]
    assert "senha" not in " ".join(etapas).lower()


def test_segredo_que_bate_e_mantido_sem_trocar_senha() -> None:
    provisionador = ProvisionadorFalso(
        {0: {"esquema": "workspace", "usuario": "luft_workspace_dev_app", "senha": "x"}}
    )

    resultado = espelhar_vault(provisionador, _sistemas(), "luft-web")  # type: ignore[arg-type]

    assert resultado.mantidos == [0] and resultado.criados == [1]
    assert [p.sistema_id for p in provisionador.planos] == [1]


def test_segredo_de_outro_schema_e_conflito_e_nao_e_alterado() -> None:
    provisionador = ProvisionadorFalso({1: {"esquema": "outro", "usuario": "luft_outro_dev_app"}})

    resultado = espelhar_vault(provisionador, _sistemas(), "luft-web")  # type: ignore[arg-type]

    assert len(resultado.conflitos) == 1 and "--substituir-segredos" in resultado.conflitos[0]
    assert resultado.criados == [0]
    assert all(g[0] != 1 for g in provisionador.gravados)


def test_substituir_regrava_o_segredo_em_conflito_com_nova_versao() -> None:
    provisionador = ProvisionadorFalso({1: {"esquema": "outro", "usuario": "luft_outro_dev_app"}})

    resultado = espelhar_vault(
        provisionador,  # type: ignore[arg-type]
        _sistemas(),
        "luft-web",
        substituir=True,
    )

    assert resultado.conflitos == [] and resultado.criados == [0, 1]
    assert (1, "luft-web", True) in provisionador.gravados


def test_falha_em_um_sistema_nao_impede_os_demais_e_nao_vaza_detalhe() -> None:
    provisionador = ProvisionadorFalso()
    provisionador.falhar_em = {0}

    resultado = espelhar_vault(provisionador, _sistemas(), "luft-web")  # type: ignore[arg-type]

    assert resultado.criados == [1]
    assert resultado.falhas == ["Sistema 0: sem permissao para criar a role"]


def test_recusa_escrever_fora_de_desenvolvimento() -> None:
    provisionador = ProvisionadorFalso()
    provisionador.ambiente = "homologacao"

    with pytest.raises(ErroProvisionamento, match="so escreve em"):
        espelhar_vault(provisionador, _sistemas(), "luft-web")  # type: ignore[arg-type]
    assert provisionador.gravados == []


def test_ler_sistemas_locais_converte_as_linhas() -> None:
    class Cursor:
        def __enter__(self) -> Cursor:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, consulta: str) -> None:
            assert "schema_aplicacao IS NOT NULL" in consulta

        def fetchall(self) -> list[tuple[int, str, str]]:
            return [(0, "Luft-Workspace", "workspace")]

    class Conexao:
        def cursor(self) -> Cursor:
            return Cursor()

    assert ler_sistemas_locais(Conexao()) == [SistemaLocal(0, "Luft-Workspace", "workspace")]
