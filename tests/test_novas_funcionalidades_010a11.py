"""Testes completos para as novas funcionalidades e estabilizacoes da versao 0.1.0a11."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from flask import Flask
from werkzeug.exceptions import Forbidden

from luftbase.autorizacao import PermissaoLuftBase
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.conteudo.modelos import (
    ComunicadoExterno,
    NovaPublicacao,
    ProvedorComunicados,
)
from luftbase.conteudo.repositorios import RepositorioNotificacoes, RepositorioPublicacoes
from luftbase.conteudo.servicos import ServicoNotificacoes, ServicoPublicacoes
from luftbase.conteudo.sinalizacao import SinalizadorConteudoRedis
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.observabilidade.servico import ServicoAuditoria
from luftbase.plataforma import PlataformaLuft
from luftbase.web.escopo import (
    eh_sistema_master,
    resolver_escopo_sistema,
    validar_sistema_alteravel_manutencao,
)
from luftbase.web.manutencao import invalidar_cache_manutencao
from luftbase.web.respostas import (
    enfileirar_toast,
    mensagem_erro,
    mensagem_sucesso,
    resposta_api_erro,
    resposta_api_sucesso,
    resposta_json,
)


def _criar_app(sistema_id: int = 0) -> tuple[Flask, Any]:
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

    @app.route("/rota-normal")
    def rota_normal() -> str:
        return "OK"

    return app, estado


def _autenticar(cliente: Any, permissoes: set[str] | None = None) -> None:
    usuario = UsuarioAutenticado(
        id_usuario=10,
        login="operador",
        nome_completo="Operador Teste",
        email="operador@luft.com.br",
        id_grupo=1,
        nome_grupo="Operacoes",
    )
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_csrf"] = "c" * 32
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}


# =========================================================================
# 1. TESTES DE RESPOSTAS PADRONIZADAS
# =========================================================================


def test_respostas_padronizadas_em_contexto() -> None:
    app = Flask(__name__)
    app.secret_key = "segredo-teste"

    with app.test_request_context():
        # Toast
        toast = enfileirar_toast("Mensagem de teste", "success")
        assert toast["tipo"] == "success"
        assert toast["mensagem"] == "Mensagem de teste"

        # Mensagem sucesso / erro
        sucesso = mensagem_sucesso("Tudo certo", chave_popup="teste_ok")
        assert sucesso is not None
        assert sucesso["tipo"] == "success"
        assert sucesso["chave_popup"] == "teste_ok"

        erro = mensagem_erro("Algo falhou", status_http=400)
        assert erro is not None
        assert erro["tipo"] == "warning"

        # Resposta API sucesso
        resp_s, code_s = resposta_api_sucesso({"id": 1}, mensagem="Criado com sucesso")
        assert code_s == 200
        json_s = resp_s.get_json()
        assert json_s["status"] == "success"
        assert json_s["data"] == {"id": 1}
        assert json_s["message"] == "Criado com sucesso"

        # Resposta API erro
        resp_e, code_e = resposta_api_erro("Erro de validacao", status_http=422)
        assert code_e == 422
        json_e = resp_e.get_json()
        assert json_e["status"] == "error"
        assert json_e["message"] == "Erro de validacao"

        # Resposta JSON normalizada
        resp_n = resposta_json({"item": "valor"})
        assert resp_n.get_json()["status"] == "success"


# =========================================================================
# 2. TESTES DE ESCOPO E AUTORIZACAO
# =========================================================================


def test_escopo_resolucao() -> None:
    app, _estado = _criar_app(sistema_id=0)

    with app.test_request_context():
        assert eh_sistema_master() is True
        # Master assume 0 quando vazio e permitido
        assert resolver_escopo_sistema(None, permitir_global_master=True) == 0
        # Master pode especificar qualquer sistema alvo
        assert resolver_escopo_sistema(2) == 2
        assert resolver_escopo_sistema("5") == 5

        # Validacao de manutencao: sistema 0 e protegido contra manutencao
        with pytest.raises(Forbidden, match="protegido"):
            validar_sistema_alteravel_manutencao(0)
        validar_sistema_alteravel_manutencao(3)


def test_escopo_satelite_bloqueia_outros_sistemas() -> None:
    app, _estado = _criar_app(sistema_id=3)

    with app.test_request_context():
        assert eh_sistema_master() is False
        # Satelite assume seu proprio sistema
        assert resolver_escopo_sistema(None) == 3
        assert resolver_escopo_sistema(3) == 3

        # Satelite tentando operar sobre sistema diferente leva 403
        with pytest.raises(Forbidden):
            resolver_escopo_sistema(0)

        with pytest.raises(Forbidden):
            resolver_escopo_sistema(4)

        # Satelite nao pode alterar manutencao do sistema 0
        with pytest.raises(Forbidden):
            validar_sistema_alteravel_manutencao(0)


# =========================================================================
# 3. TESTE AUDITORIA PARA SISTEMA 0 (WORKSPACE)
# =========================================================================


def test_auditoria_habilitada_para_sistema_zero() -> None:
    banco = MagicMock()
    servico = ServicoAuditoria(0, banco)
    assert servico.habilitada is True

    servico_negativo = ServicoAuditoria(-1, banco)
    assert servico_negativo.habilitada is False


# =========================================================================
# 4. TESTES DE ENDPOINTS PROTEGIDOS: LOGS-TEMP E SESSOES
# =========================================================================


def test_logs_temp_exige_autenticacao_e_permissao() -> None:
    app, estado = _criar_app(sistema_id=0)
    cliente = app.test_client()

    # A API web redireciona usuarios anonimos para o login corporativo.
    resp = cliente.get("/configuracoes/api/auditoria/temporarios")
    assert resp.status_code == 302

    # 403 sem a permissao de visualizacao da auditoria.
    _autenticar(cliente)
    estado.autorizacao.possui = lambda _u, _c, *_: False
    resp = cliente.get("/configuracoes/api/auditoria/temporarios")
    assert resp.status_code == 403

    # A fonte bruta exige visualizacao da auditoria e dos dados sensiveis.
    estado.autorizacao.possui = lambda _u, chave, *_: (
        chave
        in {
            PermissaoLuftBase.AUDITORIA_VISUALIZAR,
            PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,
        }
    )
    resp = cliente.get("/configuracoes/api/auditoria/temporarios")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "success"


def test_sessoes_online_e_revogar() -> None:
    app, estado = _criar_app(sistema_id=0)
    cliente = app.test_client()

    # 401 sem login
    resp = cliente.get("/_luftbase/sessoes/online")
    assert resp.status_code == 401

    _autenticar(cliente)

    # 403 sem permissao
    estado.autorizacao.possui = lambda _u, _c, *_: False
    resp = cliente.get("/_luftbase/sessoes/online")
    assert resp.status_code == 403
    assert resp.get_json()["message"] == "Acesso não autorizado."

    # 200 com permissao
    estado.autorizacao.possui = lambda _u, chave, *_: chave == PermissaoLuftBase.SESSOES_VISUALIZAR
    resp = cliente.get("/_luftbase/sessoes/online")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "success"

    # Revogar sem CSRF -> 403
    estado.autorizacao.possui = lambda _u, chave, *_: chave == PermissaoLuftBase.SESSOES_REVOGAR
    resp = cliente.post("/_luftbase/sessoes/revogar", json={"id_sessao": "abc"})
    assert resp.status_code == 403
    # A recusa por token não pode ser confundida com falta de permissão.
    assert "Ctrl+F5" in resp.get_json()["message"]

    # Revogar com CSRF e permissao -> 200
    resp = cliente.post(
        "/_luftbase/sessoes/revogar",
        json={"id_sessao": "abc"},
        headers={"X-CSRF-Token": "c" * 32},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "success"


# =========================================================================
# 5. TESTES DE MIDDLEWARE DE MANUTENCAO
# =========================================================================


def test_manutencao_middleware(monkeypatch: Any) -> None:
    app, estado = _criar_app(sistema_id=2)
    cliente = app.test_client()
    invalidar_cache_manutencao()

    # Sistema fora de manutencao: rota normal responde 200
    monkeypatch.setattr("luftbase.web.manutencao._estado_sistema", lambda _id: (False, True))
    resp = cliente.get("/rota-normal")
    assert resp.status_code == 200

    # Sistema em manutencao: rota normal responde 503
    monkeypatch.setattr("luftbase.web.manutencao._estado_sistema", lambda _id: (True, True))
    resp = cliente.get("/rota-normal")
    assert resp.status_code == 503

    # Rotas isentas respondem normalmente mesmo em manutencao
    resp_saude = cliente.get("/_luftbase/saude")
    assert resp_saude.status_code == 200

    # Operador com permissao de bypass acessa normalmente
    _autenticar(cliente)
    estado.autorizacao.possui = lambda _u, chave, *_: (
        chave
        in {
            PermissaoLuftBase.MANUTENCAO_IGNORAR,
            PermissaoLuftBase.MANUTENCAO_GERENCIAR,
        }
    )
    resp_bypass = cliente.get("/rota-normal")
    assert resp_bypass.status_code == 200


def test_sistema_descontinuado_bloqueia_todos_sem_bypass(monkeypatch: Any) -> None:
    app, estado = _criar_app(sistema_id=2)
    cliente = app.test_client()
    invalidar_cache_manutencao()
    monkeypatch.setattr("luftbase.web.manutencao._estado_sistema", lambda _id: (False, False))

    pagina = cliente.get("/rota-normal")
    api = cliente.get("/rota-normal", headers={"Accept": "application/json"})
    login = cliente.get("/login")

    assert pagina.status_code == 410
    assert "descontinuado" in pagina.get_data(as_text=True).lower()
    assert api.status_code == 410
    assert api.get_json()["code"] == 410
    assert login.status_code == 410
    assert cliente.get("/_luftbase/saude").status_code != 410

    # Nem quem ignora manutencao entra: reativar e decisao do Workspace.
    _autenticar(cliente)
    estado.autorizacao.possui = lambda _u, chave, *_: True
    assert cliente.get("/rota-normal").status_code == 410


# =========================================================================
# 6. TESTES DE CONTEUDO: NOTIFICACOES E PUBLICACOES
# =========================================================================


def test_servico_conteudo_metodos_estabilizados() -> None:
    repo_notif = MagicMock(spec=RepositorioNotificacoes)
    repo_notif.contar_nao_lidas.return_value = 5
    repo_notif.limpar_expiradas.return_value = 3

    sinalizador = MagicMock(spec=SinalizadorConteudoRedis)
    servico_notif = ServicoNotificacoes(1, repo_notif, sinalizador)

    assert servico_notif.contar_nao_lidas(10, 1) == 5
    assert servico_notif.limpar_expiradas() == 3

    repo_pub = MagicMock(spec=RepositorioPublicacoes)
    repo_pub.atualizar_rascunho.return_value = MagicMock(alterada=True)
    repo_pub.arquivar.return_value = True
    repo_pub.listar_administracao.return_value = []
    repo_pub.obter_administracao.return_value = MagicMock()
    repo_pub.criar_rascunho.return_value = MagicMock(id_publicacao=99)

    servico_pub = ServicoPublicacoes(1, repo_pub, sinalizador)

    nova_pub = NovaPublicacao(
        titulo="Comunicado Importante",
        conteudo="Conteudo do comunicado",
        criado_por="Sistema",
    )
    assert servico_pub.atualizar_rascunho(1, nova_pub) is True
    assert servico_pub.arquivar(1) is True
    assert servico_pub.listar_administracao() == []

    # Provedor externo
    class ProvedorFalso(ProvedorComunicados):
        def obter_comunicados(self) -> list[ComunicadoExterno]:
            return [
                ComunicadoExterno(
                    id_externo="ext-1",
                    fonte="GMAIL",
                    titulo="Email Informativo",
                    conteudo="Corpo do email",
                )
            ]

    ids = servico_pub.sincronizar_provedor(ProvedorFalso())
    assert ids == [99]


def test_rotas_espelhamento_e_limpeza_registradas() -> None:
    from luftbase.web.seguranca import SegurancaBp

    app = Flask(__name__)
    app.register_blueprint(SegurancaBp)
    rotas = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/seguranca/api/permissoes/espelhar" in rotas
    assert "/seguranca/api/permissoes/limpar-todas" in rotas
    assert "/seguranca/api/permissoes/resumo-origem" in rotas
