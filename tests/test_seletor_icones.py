"""Seletor de icones: catalogo coerente e marcacao do componente."""

from __future__ import annotations

import re
from pathlib import Path

import luftbase

ESTATICOS = Path(luftbase.__file__).parent / "interface" / "static"
JS = (ESTATICOS / "js" / "base.js").read_text(encoding="utf-8")
CSS = (ESTATICOS / "css" / "components.css").read_text(encoding="utf-8")
ITENS = re.findall(
    r"\{ value: '(ph-bold ph-[a-z0-9-]+)', label: '([^']+)', tags: '([^']+)', categoria: '([a-z]+)' \}",
    JS,
)
# Nomes que ja apareceram no catalogo mas nao existem no Phosphor Web 2.1.2 (carregado pelo
# phosphor-icons.js): o cartao ficava vazio. A conferencia completa exige a biblioteca (rede).
INEXISTENTES_CONHECIDOS = {
    "ph-bold ph-forklift",
    "ph-bold ph-safe",
    "ph-bold ph-server",
    "ph-bold ph-gears",
    "ph-bold ph-thumbs-up-bold",
}


def test_catalogo_nao_tem_icone_repetido_nem_inexistente_conhecido() -> None:
    valores = [valor for valor, *_ in ITENS]

    assert len(valores) > 200
    assert len(set(valores)) == len(valores)
    assert not INEXISTENTES_CONHECIDOS & set(valores)


def test_toda_categoria_do_catalogo_tem_nome_e_icone() -> None:
    usadas = {categoria for *_, categoria in ITENS}
    nomes = set(re.findall(r"^\s+'([a-z]+)': '[^']+',?$", _bloco("_categoriaNomes"), re.M))
    icones = set(
        re.findall(r"^\s+'([a-z]+)': 'ph-bold ph-[a-z-]+',?$", _bloco("_categoriaIcones"), re.M)
    )

    assert usadas <= nomes and (usadas | {"todos"}) <= icones


def _bloco(nome: str) -> str:
    inicio = JS.index(f"{nome}: {{")
    return JS[inicio : JS.index("},", inicio)]


def test_subtitulo_usa_a_contagem_real_e_nao_um_numero_fixo() -> None:
    assert "Mais de 240" not in JS
    assert "${total} ícones prontos" in JS


def test_cartoes_sao_botoes_acessiveis_e_nao_usam_estilo_inline_de_selecao() -> None:
    assert 'role="option"' in JS and 'aria-selected="${selecionado}"' in JS
    assert "onmouseover" not in JS[JS.index("_filtrarERenderizarIcones") :]
    for classe in (
        ".luft-picker-busca",
        ".luft-picker-pills",
        ".luft-icon-picker-card.selecionado",
    ):
        assert classe in CSS


def test_categorias_quebram_linha_em_vez_de_rolar_na_horizontal() -> None:
    bloco = CSS[CSS.index(".luft-picker-pills {") :].split("}", 1)[0]

    assert "flex-wrap: wrap" in bloco and "overflow-x" not in bloco


def test_busca_ignora_acento_e_aceita_varias_palavras() -> None:
    assert "normalize('NFD')" in JS
    assert "palavras.every(" in JS
    # A faixa de acentos combinantes tem de estar escrita como escape, nao com os caracteres soltos.
    linha = next(linha for linha in JS.splitlines() if "const normalizar = texto" in linha)
    assert all(ord(c) < 0x300 for c in linha)
