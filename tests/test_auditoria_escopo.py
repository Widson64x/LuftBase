"""Filtro de sistema da auditoria: 'todos' respeita o escopo da aplicacao."""

from __future__ import annotations

import pytest
from flask import Flask
from werkzeug.exceptions import Forbidden

import luftbase.web.auditoria as auditoria


def _resolver(monkeypatch, sistema_atual: int, consulta: str):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(auditoria, "sistema_aplicacao_atual", lambda: sistema_atual)
    with Flask("t").test_request_context(f"/?{consulta}"):
        return auditoria._resolver_sistema()


@pytest.mark.parametrize("consulta", ["", "sistema_id=", "sistema_id=todos"])
def test_escopo_global_ve_todos_os_sistemas(monkeypatch, consulta) -> None:  # type: ignore[no-untyped-def]
    assert _resolver(monkeypatch, 0, consulta) is None


@pytest.mark.parametrize("consulta", ["", "sistema_id=", "sistema_id=todos"])
def test_aplicacao_comum_com_todos_ve_so_a_si_mesma(monkeypatch, consulta) -> None:  # type: ignore[no-untyped-def]
    # Regressao: o painel envia sistema_id=todos por padrao e isso dava HTTP 400 no ConnectAir.
    assert _resolver(monkeypatch, 1, consulta) == 1


def test_aplicacao_comum_aceita_o_proprio_id_e_recusa_outro(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    assert _resolver(monkeypatch, 1, "sistema_id=1") == 1
    with pytest.raises(Forbidden):
        _resolver(monkeypatch, 1, "sistema_id=2")

