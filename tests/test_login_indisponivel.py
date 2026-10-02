"""Diretorio LDAP fora do ar: o login responde 503 com mensagem, nao 500."""

from __future__ import annotations

from flask import Flask

from luftbase import PlataformaLuft
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.nucleo.excecoes import ErroAutenticacao


def test_ldap_indisponivel_responde_503_com_mensagem(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)

    def fora_do_ar(_servico, _login, _senha):  # type: ignore[no-untyped-def]
        raise ErroAutenticacao("O servico de autenticacao esta indisponivel.")

    monkeypatch.setattr(type(estado.autenticacao), "autenticar", fora_do_ar)

    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["luftbase_csrf"] = "token-de-teste"
    resposta = cliente.post(
        "/login", data={"login": "alguem", "senha": "x", "csrf_token": "token-de-teste"}
    )

    assert resposta.status_code == 503
    assert "indisponível no momento" in resposta.get_data(as_text=True)
