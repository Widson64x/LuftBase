"""Categorias de sistema do catalogo: fonte unica para banco, validacao, CLI e tela.

A categoria diz **o que o sistema e** (agrupamento e selo no catalogo). Como o usuario chega ate ele
e se ele usa o LuftBase sao campos a parte (`tipo_acesso`, `integra_luftbase`).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategoriaSistema:
    codigo: str
    rotulo: str
    descricao: str
    icone: str
    selo: str  # sufixo de classe `luft-badge-<selo>`


CATEGORIAS_SISTEMA: tuple[CategoriaSistema, ...] = (
    CategoriaSistema(
        "APLICACAO",
        "Aplicação web",
        "Sistema com telas, usado pelas pessoas no navegador.",
        "ph-bold ph-app-window",
        "primary",
    ),
    CategoriaSistema(
        "API",
        "API",
        "Serviço de dados sem interface, consumido por outros sistemas.",
        "ph-bold ph-plugs-connected",
        "info",
    ),
    CategoriaSistema(
        "SERVICO",
        "Serviço / Daemon",
        "Rotina que roda em segundo plano, sem tela.",
        "ph-bold ph-gear-six",
        "gray",
    ),
    CategoriaSistema(
        "FERRAMENTA",
        "Ferramenta / Executável",
        "Programa instalado no computador, entregue por download.",
        "ph-bold ph-desktop",
        "success",
    ),
    CategoriaSistema(
        "RELATORIO",
        "Relatórios e painéis",
        "Dashboards e relatórios de consulta (BI).",
        "ph-bold ph-chart-bar",
        "info",
    ),
    CategoriaSistema(
        "INTEGRACAO",
        "Integração / Conector",
        "Troca de dados entre sistemas, ERPs e parceiros.",
        "ph-bold ph-arrows-left-right",
        "danger",
    ),
    CategoriaSistema(
        "HUB",
        "Hub / Portal central",
        "Ponto de entrada que reúne e leva aos demais sistemas.",
        "ph-bold ph-squares-four",
        "warning",
    ),
)

CODIGOS_CATEGORIA: tuple[str, ...] = tuple(c.codigo for c in CATEGORIAS_SISTEMA)
CATEGORIA_PADRAO = "APLICACAO"
_POR_CODIGO = {c.codigo: c for c in CATEGORIAS_SISTEMA}


def obter_categoria(codigo: str | None) -> CategoriaSistema:
    """Categoria pelo codigo; desconhecida ou vazia cai na padrao, para o card nunca quebrar."""

    return _POR_CODIGO.get((codigo or "").upper(), _POR_CODIGO[CATEGORIA_PADRAO])


def restricao_sql() -> str:
    """Texto do CHECK de `tb_sistema.categoria`, igual no modelo e na migracao."""

    lista = ", ".join(f"'{codigo}'" for codigo in CODIGOS_CATEGORIA)
    return f"categoria IN ({lista})"
