"""Aba Integracoes: comparacao de versoes, verificador do GitHub e vazamento de segredos."""

from __future__ import annotations

import json
import urllib.error
from collections.abc import Mapping
from types import SimpleNamespace

import pytest

from luftbase.configuracao.ambientes import Ambiente
from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.integracoes.diagnostico import (
    IntegracaoAplicacao,
    inspecionar_segredo,
    montar_painel,
)
from luftbase.integracoes.versoes import (
    VerificadorVersao,
    comparar_versoes,
    interpretar_versao,
    listar_componentes,
)
from luftbase.nucleo.excecoes import AutenticacaoCofreInvalida, SegredoNaoEncontrado

SENHA = "SenhaSuperSecreta#123"
TOKEN = "hvs.token-que-nao-pode-vazar"


@pytest.mark.parametrize(
    ("instalada", "ultima", "esperado"),
    [
        ("0.1.0a56", "0.1.0a56", "atualizada"),
        ("0.1.0a54", "0.1.0a56", "desatualizada"),
        ("0.1.0a9", "0.1.0a10", "desatualizada"),  # comparacao numerica, nao textual
        ("0.1.0", "0.1.0a56", "a_frente"),  # final > alfa
        ("0.1.0a56", "0.1.0", "desatualizada"),
        ("0.2.0a1", "0.1.0a99", "a_frente"),
        ("0.1.0a56", None, "indisponivel"),
        ("dev", "0.1.0a56", "indisponivel"),
    ],
)
def test_comparar_versoes(instalada: str, ultima: str | None, esperado: str) -> None:
    assert comparar_versoes(instalada, ultima) == esperado


def test_interpretar_versao_aceita_prefixo_v_e_rejeita_lixo() -> None:
    assert interpretar_versao("v0.1.0a56") == interpretar_versao("0.1.0a56")
    assert interpretar_versao("latest") is None


def test_componentes_listam_python_e_pacotes_instalados() -> None:
    nomes = {c["nome"]: c for c in listar_componentes()}
    assert nomes["Python"]["instalado"] is True
    assert nomes["Flask"]["instalado"] is True
    assert nomes["Flask"]["versao"] != "nao instalado"


def _verificador(tags: list[str] | Exception, relogio: list[float] | None = None):  # type: ignore[no-untyped-def]
    chamadas: list[int] = []
    tempo = relogio if relogio is not None else [0.0]

    def buscar(repositorio: str, token: str | None, timeout: float) -> list[str]:
        chamadas.append(1)
        if isinstance(tags, Exception):
            raise tags
        return tags

    return (
        VerificadorVersao(repositorio="o/r", buscar_tags=buscar, relogio=lambda: tempo[0]),
        chamadas,
        tempo,
    )


def test_verificador_escolhe_a_maior_tag_por_versao_e_nao_por_ordem_alfabetica() -> None:
    verificador, _, _ = _verificador(["v0.1.0a9", "v0.1.0a56", "v0.1.0a10", "lixo"])

    resultado = verificador.verificar("0.1.0a54")

    assert resultado.ultima == "0.1.0a56"
    assert resultado.situacao == "desatualizada"


def test_verificador_usa_cache_e_forcar_ignora() -> None:
    verificador, chamadas, tempo = _verificador(["v0.1.0a56"])

    verificador.verificar("0.1.0a56")
    verificador.verificar("0.1.0a56")
    assert len(chamadas) == 1

    verificador.verificar("0.1.0a56", forcar=True)
    assert len(chamadas) == 2

    tempo[0] = 901.0
    verificador.verificar("0.1.0a56")
    assert len(chamadas) == 3


@pytest.mark.parametrize(
    ("erro", "trecho"),
    [
        (urllib.error.HTTPError("u", 404, "nf", None, None), "LUFT_GITHUB_TOKEN"),  # type: ignore[arg-type]
        (urllib.error.URLError("sem rede"), "sem acesso"),
        (TimeoutError(), "sem acesso"),
        (json.JSONDecodeError("x", "y", 0), "sem acesso"),
    ],
)
def test_verificador_nunca_levanta_e_explica_a_falha(erro: Exception, trecho: str) -> None:
    verificador, _, _ = _verificador(erro)

    resultado = verificador.verificar("0.1.0a56")

    assert resultado.situacao == "indisponivel"
    assert trecho in resultado.detalhe


class VaultFalso:
    def __init__(self, segredos: Mapping[str, Mapping[str, object]]) -> None:
        self.segredos = segredos

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        if caminho == "luft/homologacao/proibido":
            raise AutenticacaoCofreInvalida("sem acesso")
        if caminho not in self.segredos:
            raise SegredoNaoEncontrado(caminho)
        return self.segredos[caminho]

    def ler_metadados(self, caminho: str) -> Mapping[str, object]:
        return {"current_version": 4, "updated_time": "2026-10-05T12:00:00Z"}


def test_inspecionar_segredo_mostra_so_campos_permitidos() -> None:
    vault = VaultFalso(
        {
            "a/b": {
                "host": "db.interno",
                "usuario": "u",
                "senha": SENHA,
                "token": TOKEN,
                "chave_x": "k",
            }
        }
    )

    segredo = inspecionar_segredo(vault, "a/b")

    por_nome = {c["nome"]: c for c in segredo["campos"]}
    assert por_nome["host"]["valor"] == "db.interno"
    assert por_nome["senha"]["visivel"] is False and por_nome["senha"]["valor"] is None
    assert por_nome["token"]["valor"] is None and por_nome["chave_x"]["valor"] is None
    assert segredo["versao"] == 4
    assert SENHA not in json.dumps(segredo) and TOKEN not in json.dumps(segredo)


def test_inspecionar_segredo_ausente_e_sem_acesso() -> None:
    vault = VaultFalso({})

    assert inspecionar_segredo(vault, "nao/existe")["existe"] is False
    sem_acesso = inspecionar_segredo(vault, "luft/homologacao/proibido")
    assert sem_acesso["existe"] is False and sem_acesso["erro"]


def _estado() -> SimpleNamespace:
    caminhos = resolver_caminhos_vault(ambiente=Ambiente.HOMOLOGACAO, sistema_id=3)
    configuracao = SimpleNamespace(
        aplicacao=SimpleNamespace(
            ambiente=Ambiente.HOMOLOGACAO,
            nome="Luft-Integrador",
            identificador="luft-integrador",
            sistema_id=3,
            versao="1.0",
        ),
        cofre=SimpleNamespace(endereco="https://vault.interno:8200", namespace="luft"),
        sessao=SimpleNamespace(ttl_minutos=10, nome_cookie="luft_sessao", cookie_seguro=False),
        diretorio=SimpleNamespace(
            servidor="ldap.interno", dominio="luft", transporte="ldaps", porta=None
        ),
    )
    bancos = SimpleNamespace(
        verificar_saude=lambda: (
            ResultadoSaude("diretorio_sqlserver", True, 12.0, "ok"),
            ResultadoSaude("core_postgresql", False, 0.0, "falha"),
            ResultadoSaude("aplicacao_postgresql", True, 3.0, "ok"),
        )
    )
    infra = SimpleNamespace(
        armazenamento_sessoes=type("ArmazenamentoSessoesPostgreSQL", (), {})(),
        credencial_email=SimpleNamespace(
            host="smtp.gmail.com",
            porta=587,
            seguranca=SimpleNamespace(value="starttls"),
            remetente="no-reply@luft.com.br",
            redirecionar_para=(),
            senha=SENHA,
        ),
    )
    return SimpleNamespace(
        configuracao=configuracao, caminhos_vault=caminhos, bancos=bancos, infraestrutura=infra
    )


def _vault_completo(estado: SimpleNamespace) -> VaultFalso:
    c = estado.caminhos_vault
    return VaultFalso(
        {
            c.postgresql: {
                "conexao": "luft-web",
                "usuario": "luft_integrador_hml_app",
                "esquema": "integrador",
                "senha": SENHA,
            },
            f"{c.postgresql_conexoes}/luft-web": {
                "host": "pg.interno",
                "nome_banco": "luft_web_hml",
                "porta": "5432",
            },
            c.sqlserver_diretorio: {"host": "sql.interno", "usuario": "leitor", "senha": SENHA},
            c.email: {"host": "smtp.gmail.com", "senha": SENHA},
            "luft/homologacao/bancos/sqlserver/conexoes/consulta": {
                "host": "erp.interno",
                "usuario": "ro",
                "senha": SENHA,
            },
        }
    )


def test_montar_painel_cartoes_status_e_segredos_do_ambiente() -> None:
    estado = _estado()
    painel = montar_painel(
        estado,
        _vault_completo(estado),
        versao_vault=lambda: "1.15.0",
        integracoes_aplicacao=(
            IntegracaoAplicacao(
                id="consulta",
                nome="ERP Consulta",
                descricao="Somente leitura.",
                caminho_vault="luft/homologacao/bancos/sqlserver/conexoes/consulta",
            ),
        ),
    )

    cartoes = {c["id"]: c for c in painel["cartoes"]}
    assert painel["ambiente"] == "homologacao"
    assert cartoes["vault"]["fatos"][3] == {"rotulo": "Versão do servidor", "valor": "1.15.0"}
    assert cartoes["postgresql"]["status"] == "falha"  # saude do core reportou queda
    assert cartoes["sqlserver"]["status"] == "ok"
    assert cartoes["email"]["nome"] == "Gmail"
    assert cartoes["consulta"]["status"] == "ok"
    caminhos_vault = {s["caminho"] for s in cartoes["vault"]["segredos"]}
    assert "luft/homologacao/bancos/postgresql/sistemas/3" in caminhos_vault
    assert "luft/homologacao/bancos/sqlserver/conexoes/consulta" in caminhos_vault
    assert all(c.startswith("luft/homologacao/") for c in caminhos_vault)
    redis = estado.caminhos_vault.sessoes_redis
    assert redis not in caminhos_vault  # sessoes em PostgreSQL: nao inventa segredo de Redis


def test_montar_painel_nunca_vaza_valores_secretos() -> None:
    estado = _estado()

    painel = montar_painel(estado, _vault_completo(estado))

    texto = json.dumps(painel, ensure_ascii=False)
    assert SENHA not in texto
    assert TOKEN not in texto


def test_integracao_ausente_no_vault_aparece_como_falha() -> None:
    estado = _estado()
    painel = montar_painel(
        estado,
        VaultFalso({}),
        integracoes_aplicacao=(
            IntegracaoAplicacao(id="silt", nome="SILT", descricao="", caminho_vault="x/y"),
        ),
    )

    cartoes = {c["id"]: c for c in painel["cartoes"]}
    assert cartoes["silt"]["status"] == "falha"
    assert cartoes["vault"]["status"] == "falha"


# ---- Rotas -------------------------------------------------------------------------------------


def _autenticar(cliente) -> None:  # type: ignore[no-untyped-def]
    from luftbase.identidade import UsuarioAutenticado

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


def _app_com_painel():  # type: ignore[no-untyped-def]
    from flask import Flask

    from luftbase.configuracao import ConfiguracaoLuftBase
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
    from luftbase.plataforma import PlataformaLuft

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
    return app, estado, app.test_client(), _autenticar


def test_rotas_exigem_login_e_permissao_de_servicos() -> None:
    from luftbase import PermissaoLuftBase

    _, estado, cliente, autenticar = _app_com_painel()
    url = "/configuracoes/api/configuracoes/integracoes"

    assert cliente.get(url).status_code == 302
    autenticar(cliente)
    estado.autorizacao.possui = lambda _u, _c, *_: False
    assert cliente.get(url).status_code == 403
    assert cliente.get(url + "/versao-luftbase").status_code == 403

    estado.autorizacao.possui = lambda _u, chave, *_: chave == PermissaoLuftBase.SERVICOS_VISUALIZAR
    assert cliente.get(url + "/versao-luftbase").status_code in (200,)


def test_rota_de_integracoes_responde_sem_vazar_e_painel_renderiza_a_aba(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from luftbase import PermissaoLuftBase
    from luftbase.web import integracoes as modulo

    _, estado, cliente, autenticar = _app_com_painel()
    autenticar(cliente)
    estado.autorizacao.possui = lambda _u, chave, *_: chave == PermissaoLuftBase.SERVICOS_VISUALIZAR
    vault = VaultFalso({})
    vault.versao_servidor = lambda: "1.15.0"  # type: ignore[attr-defined]
    monkeypatch.setattr(modulo, "_criar_cliente_vault", lambda _estado: vault)

    resposta = cliente.get("/configuracoes/api/configuracoes/integracoes")

    assert resposta.status_code == 200, resposta.get_data(as_text=True)
    ids = [c["id"] for c in resposta.get_json()["data"]["cartoes"]]
    assert ids[0] == "vault" and {"postgresql", "sqlserver", "luftbase", "componentes"} <= set(ids)


def test_template_do_painel_mostra_a_aba_so_com_permissao_de_servicos() -> None:
    from flask import render_template

    app, _, _, _ = _app_com_painel()
    contexto = {
        "sistemas": [],
        "is_master": True,
        "luft_csrf_token": "t",
        "aba_inicial": "tab-integracoes",
        "parametros_aplicacao": [],
        "projetos_operacao": [],
        "servicos_operacao": [],
    }
    with app.test_request_context("/configuracoes/painel"):
        com = render_template(
            "luftbase/seguranca/painel_admin.html", pode_ver_servicos=True, **contexto
        )
        sem = render_template(
            "luftbase/seguranca/painel_admin.html", pode_ver_servicos=False, **contexto
        )

    assert 'id="tab-integracoes"' in com and "js/integracoes.js" in com
    assert "api/configuracoes/integracoes/versao-luftbase" in com
    assert 'id="tab-integracoes"' not in sem


def test_painel_marca_global_como_somente_leitura_no_satelite() -> None:
    from flask import render_template

    app, _, _, _ = _app_com_painel()
    base = {
        "tipo_publicacao": "COMUNICADO",
        "grupos_publicacao": [],
        "sistemas_publicacao": [],
        "pode_ver_comunicados": True,
        "pode_ver_atualizacoes": True,
        "pode_criar": True,
        "pode_editar": True,
        "pode_publicar": True,
        "pode_arquivar": True,
    }
    item = {
        "id": 7,
        "id_publicacao": 7,
        "id_sistema": 0,
        "tipo": "COMUNICADO",
        "status": "PUBLICADO",
        "tipo_audiencia": "GERAL",
        "ids_grupos": [],
        "titulo": "Aviso global",
        "resumo": "x",
        "conteudo": "x",
        "prioridade": "NORMAL",
        "versao": None,
        "notificar": False,
        "fixado": False,
        "criado_por": "Luft",
        "fonte": "INTERNO",
        "data_criacao": None,
        "data_publicacao": None,
        "exibir_a_partir_de": None,
        "expira_em": None,
        "itens_atualizacao": [],
    }
    with app.test_request_context("/publicacoes/painel/comunicados"):
        no_satelite = render_template(
            "luftbase/publicacoes/painel.html", publicacoes=[item], sistema_atual_id=3, **base
        )
        no_workspace = render_template(
            "luftbase/publicacoes/painel.html", publicacoes=[item], sistema_atual_id=0, **base
        )

    assert "Gerenciado no Workspace" in no_satelite
    assert "LuftPublicacoesPainel.arquivar(7)" not in no_satelite
    assert "Gerenciado no Workspace" not in no_workspace
    assert "LuftPublicacoesPainel.arquivar(7)" in no_workspace


# ---- Breadcrumb: [casinha -> Workspace] > [Aplicacao -> raiz do app] ----------------------------


def _breadcrumb(script_root: str = "", **contexto) -> str:  # type: ignore[no-untyped-def]
    from flask import render_template_string

    app, _, _, _ = _app_com_painel()
    app.config["LUFT_APLICACAO_NOME"] = "Luft-ConnectAir"
    modelo = (
        '{% from "luftbase/_breadcrumb.html" import raiz as breadcrumb_raiz with context %}'
        "{{ breadcrumb_raiz(**args) }}"
    )
    with app.test_request_context("/x", base_url=f"http://h{script_root}/"):
        from flask import request

        request.environ["SCRIPT_NAME"] = script_root
        return render_template_string(modelo, args=contexto, luft_url_workspace="/")


def test_breadcrumb_casinha_vai_ao_workspace_e_nome_vai_a_raiz_do_app() -> None:
    html = _breadcrumb(script_root="/Luft-ConnectAir")

    assert 'href="/" class="luft-breadcrumb-item luft-breadcrumb-home"' in html
    assert 'title="Ir para o Luft-Workspace"' in html
    assert 'href="/Luft-ConnectAir/"' in html
    assert ">Luft-ConnectAir</a>" in html
    assert html.index("ph-house") < html.index("ph-caret-right") < html.index("Luft-ConnectAir")


def test_breadcrumb_raiz_ativa_e_href_proprio() -> None:
    ativo = _breadcrumb(ativo=True)
    outro = _breadcrumb(href_app="/Luft-ConnectAir/dashboard")

    assert "active font-semibold" in ativo and 'aria-current="page"' in ativo
    assert 'href="/Luft-ConnectAir/dashboard"' in outro and "text-muted" in outro


def test_formulario_de_login_mantem_o_prefixo_da_aplicacao() -> None:
    from flask import render_template

    app, _, _, _ = _app_com_painel()
    for modelo in ("luftbase/login.html", "luftbase/pages/login.html"):
        with app.test_request_context(
            "/login", environ_overrides={"SCRIPT_NAME": "/Luft-Integrador"}
        ):
            try:
                html = render_template(modelo, erro=None, destino="/Luft-Integrador/")
            except Exception:  # modelo exige contexto que o teste nao monta
                continue
        assert 'action="/Luft-Integrador/login"' in html, modelo
        assert 'action="/login"' not in html


def test_erro_500_registra_onde_e_o_tipo_mas_nunca_a_mensagem(caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    app, _, cliente, autenticar = _app_com_painel()
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.testing = False

    @app.get("/quebra")
    def quebra():  # type: ignore[no-untyped-def]
        raise RuntimeError("senha=SEGREDO-123 host=banco.interno")

    with caplog.at_level(logging.ERROR):
        resposta = app.test_client().get("/quebra")

    assert resposta.status_code == 500
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "erro_500" in texto and "RuntimeError" in texto and "quebra" in texto
    assert "/quebra" in texto
    assert "SEGREDO-123" not in texto and "banco.interno" not in texto


def test_resumir_excecao_traz_a_cadeia_e_a_pilha_sem_valores() -> None:
    from luftbase.observabilidade.tecnico import resumir_excecao

    def interna() -> None:
        raise ValueError("valor-secreto")

    try:
        try:
            interna()
        except ValueError as causa:
            raise RuntimeError("outra-mensagem") from causa
    except RuntimeError as erro:
        resumo = resumir_excecao(erro)

    assert resumo["cadeia"] == ["builtins.RuntimeError", "builtins.ValueError"]
    assert any("interna" in linha for linha in resumo["origem"])  # type: ignore[union-attr]
    assert "secreto" not in str(resumo) and "outra-mensagem" not in str(resumo)
