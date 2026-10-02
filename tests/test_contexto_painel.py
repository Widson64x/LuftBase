"""Sinalizadores do Painel de Controle para o contexto dos templates."""

from __future__ import annotations

from luftbase import PermissaoLuftBase, contexto_painel
from luftbase.web.contexto import SINALIZADORES_PAINEL


def test_sem_decisoes_tudo_falso() -> None:
    contexto = contexto_painel({})
    assert set(contexto) == set(SINALIZADORES_PAINEL)
    assert not any(contexto.values())


def test_um_item_libera_o_painel() -> None:
    contexto = contexto_painel({PermissaoLuftBase.AUDITORIA_VISUALIZAR: True})
    assert contexto["pode_ver_painel"] is True
    assert contexto["pode_ver_auditoria"] is True
    assert contexto["pode_ver_seguranca"] is False


def test_ambiente_aceita_qualquer_chave_do_grupo() -> None:
    for chave in (
        PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
        PermissaoLuftBase.SISTEMAS_VISUALIZAR,
        PermissaoLuftBase.SERVICOS_VISUALIZAR,
    ):
        assert contexto_painel({chave: True})["pode_ver_ambiente"] is True


def test_criar_conta_como_ver_comunicados() -> None:
    contexto = contexto_painel({PermissaoLuftBase.COMUNICADOS_CRIAR: True})
    assert contexto["pode_ver_comunicados"] is True
    assert contexto["pode_ver_atualizacoes"] is False


def test_sem_usuario_autenticado_nada_e_liberado() -> None:
    from flask import Flask
    from flask_login import LoginManager

    app = Flask("t")
    app.secret_key = "x" * 32
    gerenciador = LoginManager(app)
    gerenciador.user_loader(lambda _id: None)
    with app.test_request_context():
        assert contexto_painel()["pode_ver_painel"] is False
