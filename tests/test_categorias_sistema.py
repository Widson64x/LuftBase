"""Categorias de sistema: lista unica, CHECK do banco e o seletor visual da tela."""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

import luftbase
from luftbase.persistencia.core.categorias_sistema import (
    CATEGORIAS_SISTEMA,
    CODIGOS_CATEGORIA,
    obter_categoria,
    restricao_sql,
)
from luftbase.persistencia.core.seguranca import Sistema
from luftbase.web.configuracoes import validar_payload_novo_sistema

TEMPLATES = Path(luftbase.__file__).parent / "interface" / "templates"


def _ambiente() -> Environment:
    return Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)


def test_codigos_sao_unicos_e_o_padrao_existe() -> None:
    assert len(set(CODIGOS_CATEGORIA)) == len(CODIGOS_CATEGORIA)
    assert {"APLICACAO", "API", "SERVICO", "FERRAMENTA", "HUB"} <= set(CODIGOS_CATEGORIA)


def test_cada_categoria_tem_texto_icone_e_selo_validos() -> None:
    for categoria in CATEGORIAS_SISTEMA:
        assert categoria.rotulo and categoria.descricao
        assert categoria.icone.startswith("ph-bold ph-")
        assert categoria.selo in {"primary", "success", "danger", "warning", "info", "gray"}


def test_categoria_desconhecida_cai_na_padrao() -> None:
    assert obter_categoria("XYZ").codigo == "APLICACAO"
    assert obter_categoria(None).codigo == "APLICACAO"
    assert obter_categoria("api").codigo == "API"


def test_check_do_modelo_aceita_exatamente_as_categorias_da_lista() -> None:
    texto = next(
        str(c.sqltext)
        for c in Sistema.__table__.constraints
        if getattr(c, "name", "") == "ck_core_sistema_categoria"
    )

    assert texto == restricao_sql()
    for codigo in CODIGOS_CATEGORIA:
        assert f"'{codigo}'" in texto


@pytest.mark.parametrize("codigo", CODIGOS_CATEGORIA)
def test_validador_do_cadastro_aceita_toda_categoria_da_lista(codigo: str) -> None:
    valores, erros = validar_payload_novo_sistema({"Nome": "Teste", "Categoria": codigo})

    assert "Categoria" not in erros and valores["categoria"] == codigo


def test_validador_recusa_categoria_fora_da_lista() -> None:
    _, erros = validar_payload_novo_sistema({"Nome": "Teste", "Categoria": "OUTRA"})

    assert "Categoria" in erros


def test_seletor_renderiza_um_cartao_por_categoria_e_marca_a_primeira() -> None:
    html = (
        _ambiente()
        .get_template("luftbase/seguranca/_seletor_categoria.html")
        .render(prefixo="novoSys", categorias_sistema=CATEGORIAS_SISTEMA)
    )

    assert html.count('role="radio"') == len(CATEGORIAS_SISTEMA)
    assert html.count("<option ") == len(CATEGORIAS_SISTEMA)
    assert 'id="novoSysCategoria"' in html and 'data-campo="Categoria"' in html
    assert html.count('aria-checked="true"') == 1
    assert "escolherCategoria('novoSys', 'FERRAMENTA', true)" in html


def test_seletor_do_modal_de_edicao_nao_usa_data_campo() -> None:
    html = (
        _ambiente()
        .get_template("luftbase/seguranca/_seletor_categoria.html")
        .render(prefixo="editSys", categorias_sistema=CATEGORIAS_SISTEMA)
    )

    assert 'id="editSysCategoria"' in html and "data-campo" not in html


def test_painel_admin_compila_e_inclui_os_dois_seletores() -> None:
    origem = (TEMPLATES / "luftbase" / "seguranca" / "painel_admin.html").read_text(
        encoding="utf-8"
    )
    _ambiente().get_template("luftbase/seguranca/painel_admin.html")  # erro de sintaxe falha aqui

    assert origem.count("_seletor_categoria.html") == 2
    assert "prefixo = 'novoSys'" in origem and "prefixo = 'editSys'" in origem
    assert "function escolherCategoria(" in origem and "function navegarCategoria(" in origem
    assert origem.count('<option value="APLICACAO"') == 0  # os selects antigos foram removidos
