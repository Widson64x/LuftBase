"""Provas de renderizacao das telas oficiais de publicacoes."""

from __future__ import annotations

from types import SimpleNamespace

from flask import Flask

from luftbase import PlataformaLuft
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria


def _aplicacao() -> tuple[Flask, object]:
    app = Flask(__name__)
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": 0,
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
            "LUFT_LDAP_SERVIDOR": "ldap.invalid",
            "LUFT_LDAP_DOMINIO": "luft",
        }
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app, configuracao)
    app.testing = True
    return app, estado


def _autenticar(cliente) -> None:  # type: ignore[no-untyped-def]
    usuario = UsuarioAutenticado(7, "teste", "Usuario Teste", None, 2, "TI")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}


def test_feed_oficial_renderiza_sem_override_local(monkeypatch) -> None:
    app, estado = _aplicacao()
    monkeypatch.setattr(
        type(estado.publicacoes),
        "listar_para_usuario",
        lambda _servico, _usuario, _grupo, **_opcoes: SimpleNamespace(itens=()),
    )
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/atualizacoes")

    assert resposta.status_code == 200
    assert "Notas de atualização" in resposta.text
    assert "publicacoes-search" in resposta.text
    assert b"publicacoes.css" in resposta.data


def test_painel_oficial_tem_switcher_e_endpoints_validos(monkeypatch) -> None:
    app, estado = _aplicacao()
    monkeypatch.setattr(
        type(estado.autorizacao),
        "possui",
        lambda _servico, _usuario, _chave: True,
    )
    monkeypatch.setattr(
        type(estado.autorizacao),
        "consultar",
        lambda _servico, _usuario, chaves: {chave: True for chave in chaves},
    )
    import luftbase.web.publicacoes as modulo_publicacoes

    monkeypatch.setattr(modulo_publicacoes, "_listar_administracao", lambda _tipo: [])
    monkeypatch.setattr(
        modulo_publicacoes,
        "_listar_sistemas",
        lambda: [{"id": 0, "nome": "Todos os sistemas (global)"}],
    )
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/painel/comunicados")

    assert resposta.status_code == 200
    assert "Comunicados" in resposta.text
    assert "publicacoes-switcher" in resposta.text
    assert "/publicacoes/api/comunicados" in resposta.text
    assert "/publicacoes/api/atualizacoes" in resposta.text


def test_visualizar_publicacao_marca_lida(monkeypatch) -> None:
    app, estado = _aplicacao()
    chamou_marcar_lida: list[tuple[int, int | None, int]] = []

    def _obter_falso(_servico, id_usuario, id_grupo, id_publicacao):  # type: ignore[no-untyped-def]
        from datetime import datetime

        from luftbase.conteudo.modelos import PublicacaoUsuario

        return PublicacaoUsuario(
            id_publicacao=id_publicacao,
            id_sistema=0,
            tipo="COMUNICADO",
            audiencia="GERAL",
            titulo="Teste Titulo",
            resumo="Resumo",
            conteudo="Conteudo",
            prioridade="NORMAL",
            versao=None,
            fixado=False,
            lida=False,
            exibir_a_partir_de=None,
            expira_em=None,
            data_publicacao=datetime.now(),
        )

    def _marcar_lida_falso(_servico, id_usuario, id_grupo, id_publicacao):  # type: ignore[no-untyped-def]
        chamou_marcar_lida.append((id_usuario, id_grupo, id_publicacao))
        return True

    monkeypatch.setattr(type(estado.publicacoes), "obter_para_usuario", _obter_falso)
    monkeypatch.setattr(type(estado.publicacoes), "marcar_lida", _marcar_lida_falso)

    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/42")
    assert resposta.status_code == 200
    assert "Teste Titulo" in resposta.text
    assert chamou_marcar_lida == [(7, 2, 42)]
