"""Testes do catalogo declarativo de aplicacoes, do exigir_ajax e das URLs sob prefixo."""

from __future__ import annotations

import pytest
from flask import Flask

from luftbase import (
    CatalogoAplicacao,
    DefinicaoModulo,
    PermissaoAplicacao,
    SistemaAplicacao,
    exigir_ajax,
)
from luftbase.autorizacao.catalogo_aplicacao import ErroCatalogo, sincronizar_catalogo_aplicacao

_MODULOS = (
    DefinicaoModulo("APP", "Plataforma", "Acesso.", "ph-cube", 0),
    DefinicaoModulo("VENDAS", "Vendas", "Pedidos.", "ph-cart", 10),
)


def _catalogo(*permissoes: PermissaoAplicacao) -> CatalogoAplicacao:
    return CatalogoAplicacao(
        sistema=SistemaAplicacao(nome="Luft Vendas", descricao="Pedidos."),
        modulos=_MODULOS,
        permissoes=permissoes,
    )


_RAIZ = PermissaoAplicacao("APP.SISTEMA.ADMINISTRAR", "Tudo.", sensivel=True)
_ACESSO = PermissaoAplicacao(
    "APP.SISTEMA.ACESSAR", "Acesso.", pai="APP.SISTEMA.ADMINISTRAR", acesso_sistema=True
)


def test_catalogo_valido_deriva_modulo_recurso_e_acao() -> None:
    pedido = PermissaoAplicacao("VENDAS.PEDIDOS.VISUALIZAR", "Ver.", pai=_RAIZ.chave)
    catalogo = _catalogo(_RAIZ, _ACESSO, pedido)

    catalogo.validar()

    assert (pedido.modulo, pedido.recurso, pedido.acao) == ("VENDAS", "PEDIDOS", "VISUALIZAR")


@pytest.mark.parametrize(
    ("permissoes", "trecho"),
    [
        ((_RAIZ, _ACESSO, PermissaoAplicacao("VENDAS.PEDIDOS.DELETAR", "x")), "acao"),
        ((_RAIZ, _ACESSO, PermissaoAplicacao("vendas.pedidos.editar", "x")), "MODULO.RECURSO"),
        ((_RAIZ, _ACESSO, PermissaoAplicacao("ESTOQUE.ITENS.EDITAR", "x")), "modulo"),
        ((_RAIZ, _ACESSO, PermissaoAplicacao("VENDAS.PEDIDOS.EDITAR", "x", pai="X.Y.Z")), "pai"),
        ((_RAIZ, _ACESSO, _ACESSO), "duas vezes"),
        ((_RAIZ,), "acesso"),
    ],
)
def test_catalogo_invalido_e_recusado(
    permissoes: tuple[PermissaoAplicacao, ...], trecho: str
) -> None:
    with pytest.raises(ErroCatalogo, match=trecho):
        _catalogo(*permissoes).validar()


def test_sistema_zero_nao_e_sincronizado_por_aplicacao() -> None:
    with pytest.raises(ErroCatalogo, match="sistema 0"):
        sincronizar_catalogo_aplicacao(None, 0, _catalogo(_RAIZ, _ACESSO))  # type: ignore[arg-type]


def test_exigir_ajax_recusa_navegacao_direta() -> None:
    app = Flask(__name__)

    @app.get("/api")
    @exigir_ajax
    def api() -> str:
        return "ok"

    cliente = app.test_client()

    assert cliente.get("/api").status_code == 404
    assert cliente.get("/api", headers={"X-Requested-With": "XMLHttpRequest"}).data == b"ok"
    assert cliente.get("/api", json={}).data == b"ok"


def test_aplicacao_sob_prefixo_preserva_a_raiz_no_login() -> None:
    from flask_login import login_required

    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria

    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)

    @app.get("/privado")
    @login_required
    def privado() -> str:
        return "ok"

    cliente = app.test_client()
    prefixo = {"SCRIPT_NAME": "/Luft-ConnectAir"}

    resposta = cliente.get("/privado", environ_overrides=prefixo)
    login = cliente.get("/login", environ_overrides=prefixo)

    assert resposta.status_code == 302
    assert resposta.location.startswith("/Luft-ConnectAir/login")
    assert "next=/Luft-ConnectAir/privado" in resposta.location
    assert '"raiz": "/Luft-ConnectAir"' in login.get_data(as_text=True)


def test_mensagens_de_flash_viram_toasts_do_luftbase() -> None:
    from flask import flash

    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria

    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)

    @app.get("/importar")
    def importar() -> str:
        flash("Arquivo importado.", "success")
        flash("Linha 3 ignorada.", "error")
        return "ok"

    cliente = app.test_client()
    cliente.get("/importar")
    comandos = cliente.get("/_luftbase/mensagens").json["comandos"]
    repetido = cliente.get("/_luftbase/mensagens").json["comandos"]

    assert [(c["tipo"], c["mensagem"]) for c in comandos] == [
        ("success", "Arquivo importado."),
        ("danger", "Linha 3 ignorada."),
    ]
    assert repetido == []


def _core_sqlite():  # type: ignore[no-untyped-def]
    from typing import cast

    from sqlalchemy import CheckConstraint, MetaData, Table, create_engine

    from luftbase.persistencia.core.seguranca import Modulo, Permissao, Sistema

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        execution_options={"schema_translate_map": {"core": None}},
    )
    # Copias sem os CHECK com regex do PostgreSQL, que o SQLite nao interpreta.
    metadados = MetaData()
    for modelo in (Sistema, Modulo, Permissao):
        tabela = cast(Table, modelo.__table__).to_metadata(metadados)
        for restricao in [c for c in tabela.constraints if isinstance(c, CheckConstraint)]:
            tabela.constraints.discard(restricao)
        for indice in [
            i for i in tabela.indexes if i.dialect_options["postgresql"]["where"] is not None
        ]:
            tabela.indexes.discard(indice)
    metadados.create_all(engine)
    return engine


def _gravar(conexao, id_sistema: int, catalogo: CatalogoAplicacao) -> None:  # type: ignore[no-untyped-def]
    """Grava o catalogo com INSERT simples (SQLite nao tem o ON CONFLICT do PostgreSQL)."""

    from sqlalchemy import insert

    from luftbase.persistencia.core.seguranca import Modulo, Permissao, Sistema

    conexao.execute(insert(Sistema).values(id_sistema=id_sistema, nome_sistema="Vendas"))
    ids_modulo = {}
    for modulo in catalogo.modulos:
        ids_modulo[modulo.codigo] = conexao.execute(
            insert(Modulo).values(
                id_sistema=id_sistema,
                codigo_modulo=modulo.codigo,
                nome_modulo=modulo.nome,
                descricao_modulo=modulo.descricao,
                icone=modulo.icone,
                ordem_exibicao=modulo.ordem,
            )
        ).inserted_primary_key[0]
    ids = {}
    for p in catalogo.permissoes:
        ids[p.chave] = conexao.execute(
            insert(Permissao).values(
                id_sistema=id_sistema,
                id_modulo=ids_modulo[p.modulo],
                id_permissao_pai=ids.get(p.pai) if p.pai else None,
                chave_permissao=p.chave,
                recurso=p.recurso,
                acao=p.acao,
                descricao_permissao=p.descricao,
                sensivel=p.sensivel,
                eh_acesso_sistema=p.acesso_sistema,
                ordem_exibicao=p.ordem,
            )
        ).inserted_primary_key[0]


def test_pendencias_vazias_quando_core_ja_esta_em_dia() -> None:
    from luftbase.autorizacao.catalogo_aplicacao import pendencias_catalogo

    pedido = PermissaoAplicacao("VENDAS.PEDIDOS.VISUALIZAR", "Ver.", pai=_RAIZ.chave)
    catalogo = _catalogo(_RAIZ, _ACESSO, pedido)
    engine = _core_sqlite()
    with engine.begin() as conexao:
        _gravar(conexao, 5, catalogo)
        assert pendencias_catalogo(conexao, 5, catalogo) == []


def test_pendencias_apontam_o_que_falta_e_o_que_divergiu() -> None:
    from luftbase.autorizacao.catalogo_aplicacao import pendencias_catalogo

    pedido = PermissaoAplicacao("VENDAS.PEDIDOS.VISUALIZAR", "Ver.", pai=_RAIZ.chave)
    engine = _core_sqlite()
    with engine.begin() as conexao:
        _gravar(conexao, 5, _catalogo(_RAIZ, _ACESSO, pedido))
        novo = _catalogo(
            _RAIZ,
            _ACESSO,
            PermissaoAplicacao("VENDAS.PEDIDOS.VISUALIZAR", "Ver pedidos.", pai=_RAIZ.chave),
            PermissaoAplicacao("VENDAS.PEDIDOS.EXCLUIR", "Excluir.", pai=_RAIZ.chave),
        )
        assert pendencias_catalogo(conexao, 5, novo) == [
            "permissao VENDAS.PEDIDOS.VISUALIZAR divergente",
            "permissao VENDAS.PEDIDOS.EXCLUIR ausente",
        ]


def test_modulo_explicito_mantem_acesso_no_modulo_plataforma() -> None:
    acesso = PermissaoAplicacao(
        "VENDAS.SISTEMA.ACESSAR", "Acesso.", acesso_sistema=True, modulo_codigo="PLATAFORMA"
    )
    catalogo = CatalogoAplicacao(
        modulos=(DefinicaoModulo("PLATAFORMA", "Plataforma", "Acesso.", "ph-cube", 0),),
        permissoes=(acesso,),
    )

    catalogo.validar()

    assert (acesso.modulo, acesso.recurso, acesso.acao) == ("PLATAFORMA", "SISTEMA", "ACESSAR")


def test_plataforma_recusa_catalogo_no_sistema_zero() -> None:
    import pytest as _pytest

    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
    from luftbase.nucleo import ErroInicializacao

    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    plataforma = PlataformaLuft(FabricaInfraestruturaMemoria(), catalogo=_catalogo(_RAIZ, _ACESSO))

    with _pytest.raises(ErroInicializacao, match="sistema 0"):
        plataforma.inicializar(app)
