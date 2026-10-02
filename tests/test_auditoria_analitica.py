"""Testes da API e das protecoes do painel analitico de auditoria."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from flask import Flask, render_template

from luftbase.autorizacao import PermissaoLuftBase
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.observabilidade.analise import FiltroAuditoria, PaginaAuditoria
from luftbase.plataforma import PlataformaLuft
from luftbase.web.auditoria import _valor_csv


class ServicoAnaliseFalso:
    def __init__(self) -> None:
        self.incluir_sensiveis: bool | None = None
        self.id_sistema_detalhe: int | None = None
        self.escopo_opcoes: object = "nao chamado"

    def obter_resumo(self, filtro: FiltroAuditoria) -> dict[str, Any]:
        assert filtro.fim >= filtro.inicio
        return {
            "indicadores": {"requisicoes": 12},
            "serie": [],
            "rankings": {"usuarios": [{"rotulo": "operador", "total": 12}]},
        }

    def obter_opcoes(
        self,
        filtro: FiltroAuditoria,
        *,
        id_sistema_escopo: int | None = None,
    ) -> dict[str, Any]:
        self.escopo_opcoes = id_sistema_escopo
        return {"sistemas": [], "usuarios": [], "grupos": []}

    def listar_acessos(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        return {"total": 0, "pagina": pagina.numero, "tamanho": pagina.tamanho, "itens": []}

    def listar_detalhes(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        return {"total": 0, "pagina": pagina.numero, "tamanho": pagina.tamanho, "itens": []}

    def listar_alteracoes(
        self,
        filtro: FiltroAuditoria,
        pagina: PaginaAuditoria,
    ) -> dict[str, Any]:
        return {"total": 0, "pagina": pagina.numero, "tamanho": pagina.tamanho, "itens": []}

    def obter_detalhe(
        self,
        tipo: str,
        identificador: int,
        *,
        incluir_sensiveis: bool,
        id_sistema: int | None = None,
    ) -> dict[str, Any]:
        self.incluir_sensiveis = incluir_sensiveis
        self.id_sistema_detalhe = id_sistema
        return {"tipo": tipo, "id": identificador, "sistema_id": 0}


def _aplicacao(sistema_id: int = 0) -> tuple[Flask, Any]:
    app = Flask(__name__)
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": sistema_id,
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
            "LUFT_LDAP_SERVIDOR": "ldap.invalid",
            "LUFT_LDAP_DOMINIO": "luft",
        }
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app, configuracao)
    app.testing = True
    return app, estado


def _autenticar(cliente: Any) -> None:
    usuario = UsuarioAutenticado(10, "operador", "Operador", None, 6, "DBA")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()


def test_resumo_exige_permissao_e_entrega_capacidades(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao()
    falso = ServicoAnaliseFalso()
    monkeypatch.setattr(modulo, "_servico", lambda: falso)
    cliente = app.test_client()
    _autenticar(cliente)

    estado.autorizacao.possui = lambda *_: False
    assert cliente.get("/configuracoes/api/auditoria/resumo").status_code == 403

    estado.autorizacao.possui = lambda *_: True
    estado.autorizacao.consultar = lambda _usuario, chaves: {chave: True for chave in chaves}
    resposta = cliente.get("/configuracoes/api/auditoria/resumo")

    assert resposta.status_code == 200
    dados = resposta.get_json()["data"]
    assert dados["indicadores"]["requisicoes"] == 12
    assert dados["capacidades"] == {"exportar": True, "ver_sensiveis": True}


def test_periodo_maior_que_noventa_dias_e_rejeitado(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao()
    monkeypatch.setattr(modulo, "_servico", ServicoAnaliseFalso)
    estado.autorizacao.possui = lambda *_: True
    cliente = app.test_client()
    _autenticar(cliente)
    fim = datetime.now()
    inicio = fim - timedelta(days=91)

    resposta = cliente.get(
        "/configuracoes/api/auditoria/resumo",
        query_string={"inicio": inicio.isoformat(), "fim": fim.isoformat()},
    )

    assert resposta.status_code == 400


def test_detalhe_sensivel_depende_de_permissao_especifica(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao()
    falso = ServicoAnaliseFalso()
    monkeypatch.setattr(modulo, "_servico", lambda: falso)
    estado.autorizacao.possui = lambda *_: True
    estado.autorizacao.consultar = lambda _usuario, chaves: {chave: False for chave in chaves}
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/configuracoes/api/auditoria/detalhes/acesso/9")

    assert resposta.status_code == 200
    assert falso.incluir_sensiveis is False
    assert falso.id_sistema_detalhe is None


def test_aplicacao_satelite_limita_consultas_ao_proprio_sistema(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao(sistema_id=7)
    falso = ServicoAnaliseFalso()
    monkeypatch.setattr(modulo, "_servico", lambda: falso)
    estado.autorizacao.possui = lambda *_: True
    estado.autorizacao.consultar = lambda _usuario, chaves: {chave: False for chave in chaves}
    cliente = app.test_client()
    _autenticar(cliente)

    fora_do_escopo = cliente.get(
        "/configuracoes/api/auditoria/resumo",
        query_string={"sistema_id": 8},
    )
    detalhe = cliente.get("/configuracoes/api/auditoria/detalhes/acesso/9")

    assert fora_do_escopo.status_code == 403
    assert detalhe.status_code == 200
    assert falso.id_sistema_detalhe == 7


def test_lista_de_sistemas_do_filtro_so_mostra_o_proprio_fora_do_escopo_global(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    for sistema, esperado in ((0, None), (7, 7)):
        app, estado = _aplicacao(sistema)
        falso = ServicoAnaliseFalso()
        monkeypatch.setattr(modulo, "_servico", lambda falso=falso: falso)
        estado.autorizacao.possui = lambda *_: True
        estado.autorizacao.consultar = lambda _usuario, chaves: {chave: True for chave in chaves}
        cliente = app.test_client()
        _autenticar(cliente)
        resposta = cliente.get("/configuracoes/api/auditoria/resumo?sistema_id=todos")
        assert resposta.status_code == 200
        assert falso.escopo_opcoes == esperado, sistema


def test_exportacao_protege_planilha_contra_formula() -> None:
    assert _valor_csv("=HYPERLINK('x')") == "'=HYPERLINK('x')"
    assert _valor_csv("rota-normal") == "rota-normal"
    assert _valor_csv(10) == 10


def test_fontes_estruturadas_e_brutas_possuem_autorizacoes_distintas(monkeypatch) -> None:
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao()
    falso = ServicoAnaliseFalso()
    monkeypatch.setattr(modulo, "_servico", lambda: falso)
    cliente = app.test_client()
    _autenticar(cliente)

    estado.autorizacao.possui = lambda *_: True
    assert cliente.get("/configuracoes/api/auditoria/detalhes").status_code == 200
    assert cliente.get("/configuracoes/api/auditoria/alteracoes").status_code == 200
    assert cliente.get("/configuracoes/api/auditoria/temporarios").status_code == 200
    assert cliente.get("/configuracoes/api/auditoria/fisicos").status_code == 200

    estado.autorizacao.possui = lambda _usuario, chave, *_: (
        chave == PermissaoLuftBase.AUDITORIA_VISUALIZAR
    )
    assert cliente.get("/configuracoes/api/auditoria/detalhes").status_code == 200
    assert cliente.get("/configuracoes/api/auditoria/temporarios").status_code == 403
    assert cliente.get("/configuracoes/api/auditoria/fisicos").status_code == 403


def test_painel_auditoria_renderiza_como_aba_principal_global() -> None:
    app, _estado = _aplicacao()

    with app.test_request_context("/configuracoes/painel?tab=tab-auditoria"):
        html = render_template(
            "luftbase/seguranca/painel_admin.html",
            sistemas=[],
            is_master=True,
            sistema_atual_id=0,
            pode_ver_seguranca=False,
            pode_ver_ambiente=False,
            pode_editar_ambiente=False,
            pode_ver_comunicados=False,
            pode_ver_atualizacoes=False,
            pode_ver_auditoria=True,
            pode_ver_configuracoes=False,
            pode_exportar_auditoria=True,
            pode_ver_dados_sensiveis_auditoria=False,
            projetos_operacao=[],
            servicos_operacao=[],
        )

    assert "Auditoria & Análise" in html
    assert 'id="luftAuditoria"' in html
    assert 'id="tab-auditoria"' in html
    assert "subpainel-auditoria" not in html
    assert "btnSubAuditoria" not in html
    assert "/configuracoes/api/auditoria/resumo" in html
    assert "/configuracoes/api/auditoria/alteracoes" in html
    assert "/configuracoes/api/auditoria/fisicos" in html
    assert "/_luftbase_compat/static/css/auditoria.css" in html
    assert "/_luftbase_compat/static/js/auditoria.js" in html
