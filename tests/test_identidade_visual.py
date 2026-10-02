"""A identidade visual (marca, sidebar) deve seguir o tema ativo, nao um azul fixo."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest

INTERFACE = Path(__file__).parents[1] / "src" / "luftbase" / "interface"
CSS = INTERFACE / "static" / "css"
TEMPLATES = INTERFACE / "templates"

# Arquivos que DEFINEM a marca ou sao paletas por design (nao devem ser tokenizados).
ARQUIVOS_DE_DEFINICAO = {"themes.css", "luft.css", "luft-esg.css"}
AZUL_FIXO = re.compile(r"(?<!, )#(?:1d63d8|2563eb|3b82f6|1f4f99|2b66bf|0875d7)\b", re.I)


def _css_dos_componentes() -> list[Path]:
    return [p for p in CSS.rglob("*.css") if p.name not in ARQUIVOS_DE_DEFINICAO]


@pytest.mark.parametrize("arquivo", _css_dos_componentes(), ids=lambda p: p.name)
def test_css_de_componentes_nao_usa_azul_de_marca_fixo(arquivo: Path) -> None:
    fixos = AZUL_FIXO.findall(arquivo.read_text(encoding="utf-8"))

    assert fixos == [], f"{arquivo.name} usa azul fixo; use var(--luft-brand, ...)"


def test_tokens_de_marca_tem_valor_padrao_e_nao_sao_circulares() -> None:
    themes = (CSS / "themes.css").read_text(encoding="utf-8")

    assert re.search(r"--luft-brand:\s+#1d63d8;", themes)
    assert re.search(r"--luft-brand-rgb:\s+29, 99, 216;", themes)
    assert "--luft-brand: var(--luft-brand" not in themes


def test_todo_tema_registrado_define_a_marca_no_claro_e_no_escuro() -> None:
    from luftbase.interface.servico import criar_registro_padrao
    from luftbase.persistencia.core.preferencias import ModoTema

    for manifesto in criar_registro_padrao().listar():
        nome = manifesto.url_css.rsplit("/", 1)[-1]
        css = (CSS / "temas" / nome).read_text(encoding="utf-8")
        if ModoTema.ESCURO in manifesto.modos:
            regras = re.findall(r"([^{}]+)\{([^{}]*)\}", re.sub(r"/\*.*?\*/", "", css, flags=re.S))
            escuras = [
                corpo
                for seletor, corpo in regras
                if 'data-theme="dark"' in seletor or 'data-luft-mode="escuro"' in seletor
            ]
            assert any("--luft-brand:" in corpo for corpo in escuras), (
                f"{nome} nao redefine --luft-brand no escuro (marca ficaria ilegivel)"
            )


def _ambiente() -> jinja2.Environment:
    ambiente = jinja2.Environment(loader=jinja2.FileSystemLoader(str(TEMPLATES)))
    ambiente.globals["url_for"] = lambda endpoint, **kw: f"/{endpoint}/{kw.get('filename', '')}"
    return ambiente


def test_macro_sidebar_brand_usa_classes_de_tema_e_sem_cor_inline() -> None:
    html = _ambiente().from_string(
        '{% import "luftbase/components.html" as ui %}{{ ui.sidebar_brand("LUFT-TESTE", "T") }}'
    ).render()

    assert "LUFT-TESTE" in html
    assert "luft-logo-titulo" in html
    assert "luft-logo-subtitulo" in html
    assert "luft-logo-Dark.png" not in html or "icons/luft-logo-150x150-Dark.png" in html
    assert "color:" not in html  # a cor vem do CSS (tokens), nunca inline
    assert '<span class="text-main">T</span>' in html


def test_css_da_marca_da_sidebar_le_os_tokens_do_tema() -> None:
    css = (CSS / "sidebar.css").read_text(encoding="utf-8")

    assert "var(--luft-text-main" in css.split(".luft-logo-titulo")[1].split("}")[0]
    assert "var(--luft-brand" in css.split(".luft-logo-subtitulo")[1].split("}")[0]


@pytest.mark.parametrize(
    "template",
    [p.relative_to(TEMPLATES).as_posix() for p in TEMPLATES.rglob("*.html")],
)
def test_templates_continuam_com_sintaxe_jinja_valida(template: str) -> None:
    _ambiente().parse(
        (TEMPLATES / template).read_text(encoding="utf-8"),
        name=template,
    )
