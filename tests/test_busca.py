"""Busca global: provedores registrados pela aplicacao, permissao, prazo e URLs seguras."""

from __future__ import annotations

import time
from typing import Any

import pytest
from flask import Flask, url_for

from luftbase import PlataformaLuft, ProvedorBusca, ResultadoBusca
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.web import busca as modulo


@pytest.fixture(autouse=True)
def _restaura_autorizacao():  # type: ignore[no-untyped-def]
    """Os testes trocam `possui` na classe; devolve o original para nao vazar para outros."""

    from luftbase.autorizacao.servico import ServicoAutorizacao

    original = ServicoAutorizacao.possui
    yield
    ServicoAutorizacao.possui = original  # type: ignore[method-assign]


def _app(buscas: list[ProvedorBusca], permitido: bool | set[str] = True) -> Flask:
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=1,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault.invalid:8200",
        LUFT_LDAP_SERVIDOR="ldap.invalid",
        LUFT_LDAP_DOMINIO="luft",
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria(), buscas=buscas).inicializar(app)

    def possui(_servico: Any, _usuario: Any, chave: str) -> bool:
        return permitido if isinstance(permitido, bool) else chave in permitido

    type(estado.autorizacao).possui = possui  # type: ignore[method-assign]
    app.testing = True
    return app


def _logar(cliente: Any) -> None:
    usuario = UsuarioAutenticado(10, "operador", "Operador", None, 6, "TI")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()


def _provedor(id_: str = "ctcs", **extra: Any) -> ProvedorBusca:
    def buscar(termo: str, limite: int) -> list[ResultadoBusca]:
        return [ResultadoBusca(f"{termo}-{i}", f"/ctc/{i}", "sub") for i in range(10)]

    return ProvedorBusca(id=id_, titulo="CTCs", buscar=buscar, **extra)


def test_sem_login_nao_pesquisa() -> None:
    resposta = _app([_provedor()]).test_client().get("/_luftbase/busca?q=abc")
    assert resposta.status_code in (302, 401)


def test_resultados_agrupados_e_limitados() -> None:
    cliente = _app([_provedor(limite=3)]).test_client()
    _logar(cliente)
    dados = cliente.get("/_luftbase/busca?q=26").get_json()
    assert [g["id"] for g in dados["grupos"]] == ["ctcs"]
    assert len(dados["grupos"][0]["itens"]) == 3
    assert dados["grupos"][0]["itens"][0]["url"] == "/ctc/0"


def test_termo_curto_nao_consulta_o_provedor() -> None:
    chamadas: list[str] = []

    def buscar(termo: str, limite: int) -> list[ResultadoBusca]:
        chamadas.append(termo)
        return []

    provedor = ProvedorBusca(id="x", titulo="X", buscar=buscar, minimo_caracteres=3)
    cliente = _app([provedor]).test_client()
    _logar(cliente)
    assert cliente.get("/_luftbase/busca?q=ab").get_json()["grupos"] == []
    assert chamadas == []
    cliente.get("/_luftbase/busca?q=abc")
    assert chamadas == ["abc"]


def test_provedor_so_aparece_para_quem_tem_permissao() -> None:
    buscas = [_provedor("a", permissao="A.B.C"), _provedor("livre")]
    cliente = _app(buscas, permitido={"OUTRA.COISA"}).test_client()
    _logar(cliente)
    grupos = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"]
    assert [g["id"] for g in grupos] == ["livre"]
    cliente = _app(buscas, permitido={"A.B.C"}).test_client()
    _logar(cliente)
    grupos = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"]
    assert [g["id"] for g in grupos] == ["a", "livre"]


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/x",
        "//evil.example/x",
        "javascript:alert(1)",
        "relativo/sem/barra",
        "/a\\b",
    ],
)
def test_url_fora_do_sistema_e_descartada(url: str) -> None:
    def buscar(termo: str, limite: int) -> list[ResultadoBusca]:
        return [ResultadoBusca("ruim", url), ResultadoBusca("bom", "/ok")]

    cliente = _app([ProvedorBusca(id="x", titulo="X", buscar=buscar)]).test_client()
    _logar(cliente)
    itens = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"][0]["itens"]
    assert [i["titulo"] for i in itens] == ["bom"]


def test_urls_externas_so_com_opt_in_e_so_http() -> None:
    def buscar(termo: str, limite: int) -> list[ResultadoBusca]:
        return [
            ResultadoBusca("web", "https://hub.exemplo.com.br/app/"),
            ResultadoBusca("js", "javascript:alert(1)"),
            ResultadoBusca("ftp", "ftp://x/y"),
        ]

    for permitir, esperado in ((False, []), (True, ["web"])):
        provedor = ProvedorBusca(id="x", titulo="X", buscar=buscar, urls_externas=permitir)
        cliente = _app([provedor]).test_client()
        _logar(cliente)
        grupos = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"]
        titulos = [i["titulo"] for g in grupos for i in g["itens"]]
        assert titulos == esperado


def test_provedor_com_erro_nao_derruba_os_outros() -> None:
    def quebra(termo: str, limite: int) -> list[ResultadoBusca]:
        raise RuntimeError("falhou")

    buscas = [ProvedorBusca(id="ruim", titulo="Ruim", buscar=quebra), _provedor("bom")]
    cliente = _app(buscas).test_client()
    _logar(cliente)
    resposta = cliente.get("/_luftbase/busca?q=zz")
    assert resposta.status_code == 200
    assert [g["id"] for g in resposta.get_json()["grupos"]] == ["bom"]


def test_provedor_lento_e_ignorado_no_prazo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo, "LIMITE_DE_TEMPO_SEGUNDOS", 0.3)

    def lento(termo: str, limite: int) -> list[ResultadoBusca]:
        time.sleep(1.5)
        return [ResultadoBusca("tarde", "/t")]

    buscas = [ProvedorBusca(id="lento", titulo="Lento", buscar=lento), _provedor("rapido")]
    cliente = _app(buscas).test_client()
    _logar(cliente)
    inicio = time.monotonic()
    grupos = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"]
    assert time.monotonic() - inicio < 1.2
    assert [g["id"] for g in grupos] == ["rapido"]


def test_url_for_funciona_dentro_do_provedor() -> None:
    def buscar(termo: str, limite: int) -> list[ResultadoBusca]:
        return [ResultadoBusca("um", url_for("destino", n=1))]

    app = _app([ProvedorBusca(id="u", titulo="U", buscar=buscar)])

    @app.get("/destino/<int:n>", endpoint="destino")
    def destino(n: int) -> str:
        return str(n)

    cliente = app.test_client()
    _logar(cliente)
    grupos = cliente.get("/_luftbase/busca?q=zz").get_json()["grupos"]
    assert grupos[0]["itens"][0]["url"] == "/destino/1"


def test_definicao_invalida_e_recusada() -> None:
    nada = lambda termo, limite: []  # noqa: E731
    with pytest.raises(ErroConfiguracao):
        ProvedorBusca(id="Maiuscula", titulo="X", buscar=nada)
    with pytest.raises(ErroConfiguracao):
        ProvedorBusca(id="x", titulo=" ", buscar=nada)
    with pytest.raises(ErroConfiguracao):
        ProvedorBusca(id="x", titulo="X", buscar=nada, icone="fa-solid fa-x")
    with pytest.raises(ErroConfiguracao):
        ProvedorBusca(id="x", titulo="X", buscar=nada, limite=0)


def test_pagina_traz_a_busca_ligada_ao_endpoint() -> None:
    from flask_login import login_required

    app = _app([])

    @app.get("/pagina")
    @login_required
    def pagina() -> str:
        from flask import render_template

        return render_template("luftbase/base.html")

    cliente = app.test_client()
    _logar(cliente)
    html = cliente.get("/pagina").get_data(as_text=True)
    assert 'data-busca-url="/_luftbase/busca"' in html
    assert "js/busca.js" in html and "css/busca.css" in html
