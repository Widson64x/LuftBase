"""Testes da remocao manual de segredos de sistemas no Vault."""

from __future__ import annotations

import sys

from click.testing import CliRunner

from luftbase.cli import cli


class Kv2Falso:
    def __init__(self, chaves: list[str]) -> None:
        self.chaves = list(chaves)
        self.removidos: list[str] = []

    def list_secrets(self, path: str, mount_point: str) -> dict[str, object]:
        assert path == "luft/desenvolvimento/bancos/postgresql/sistemas"
        return {"data": {"keys": list(self.chaves)}}

    def delete_metadata_and_all_versions(self, path: str, mount_point: str) -> None:
        self.removidos.append(path)


class ClienteFalso:
    def __init__(self, kv2: Kv2Falso) -> None:
        self.secrets = type("S", (), {"kv": type("K", (), {"v2": kv2})()})()


def _preparar(monkeypatch, chaves: list[str]) -> Kv2Falso:  # type: ignore[no-untyped-def]
    kv2 = Kv2Falso(chaves)
    modulo = sys.modules["luftbase.cli.vault"]
    monkeypatch.setattr(modulo, "_solicitar_segredo", lambda rotulo: "token")
    monkeypatch.setattr(modulo, "_criar_cliente_hvac_operador", lambda *a: ClienteFalso(kv2))
    return kv2


def test_remove_todos_os_sistemas_apos_confirmacao(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _preparar(monkeypatch, ["0", "1"])

    resultado = CliRunner().invoke(
        cli,
        ["vault", "postgresql", "remover-sistemas", "--ambiente", "dev"],
        input="REMOVER-DESENVOLVIMENTO\n",
    )

    assert resultado.exit_code == 0, resultado.output
    assert kv2.removidos == [
        "luft/desenvolvimento/bancos/postgresql/sistemas/0",
        "luft/desenvolvimento/bancos/postgresql/sistemas/1",
    ]


def test_remove_somente_o_sistema_informado(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _preparar(monkeypatch, ["0", "1"])

    resultado = CliRunner().invoke(
        cli,
        [
            "vault",
            "postgresql",
            "remover-sistemas",
            "--ambiente",
            "desenvolvimento",
            "--sistema-id",
            "1",
            "--sistema-id",
            "7",
        ],
        input="REMOVER-DESENVOLVIMENTO\n",
    )

    assert resultado.exit_code == 0, resultado.output
    assert kv2.removidos == ["luft/desenvolvimento/bancos/postgresql/sistemas/1"]
    assert "ignorados (nao existem)=7" in resultado.output


def test_confirmacao_errada_nao_remove_nada(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _preparar(monkeypatch, ["0"])

    resultado = CliRunner().invoke(
        cli,
        ["vault", "postgresql", "remover-sistemas", "--ambiente", "desenvolvimento"],
        input="sim\n",
    )

    assert resultado.exit_code != 0
    assert kv2.removidos == []
