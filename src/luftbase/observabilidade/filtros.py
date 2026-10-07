"""Peças de filtro compartilhadas pelas consultas da auditoria (navegador e rota).

O filtro de navegador espelha, em SQL, as regras de `identidade.agente_usuario.interpretar_agente`:
clicar em "Chrome" num gráfico deve trazer exatamente os acessos que o gráfico contou como Chrome.
Há um teste que confere os dois lados com os mesmos user-agents.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, false, not_, or_

NAVEGADORES = ("Edge", "Opera", "Firefox", "Samsung Internet", "Chrome", "Safari", "Internet Explorer")

_EDGE = ("Edg/", "EdgA/", "EdgiOS/", "Edge/")
_OPERA = ("OPR/", "OPiOS/")
_FIREFOX = ("Firefox/", "FxiOS/")
_SAMSUNG = ("SamsungBrowser/",)
_CHROME = ("Chrome/", "CriOS/")
_IE = ("MSIE ", "Trident/")


def _qualquer(coluna: Any, trechos: tuple[str, ...]) -> Any:
    return or_(*(coluna.contains(t, autoescape=True) for t in trechos))


def condicao_navegador(coluna: Any, nome: str) -> Any:
    """Cláusula SQL que seleciona linhas cujo user-agent é do navegador `nome`.

    `nome` "Desconhecido" seleciona quem não tem user-agent. Nome fora da lista não casa com nada.
    """

    if nome == "Desconhecido":
        return or_(coluna.is_(None), coluna == "")
    edge, opera, samsung = _qualquer(coluna, _EDGE), _qualquer(coluna, _OPERA), _qualquer(coluna, _SAMSUNG)
    firefox, chrome, ie = _qualquer(coluna, _FIREFOX), _qualquer(coluna, _CHROME), _qualquer(coluna, _IE)
    if nome == "Edge":
        return edge
    if nome == "Opera":
        return and_(not_(edge), opera)
    if nome == "Firefox":
        return and_(not_(edge), not_(opera), firefox)
    if nome == "Samsung Internet":
        return and_(not_(edge), not_(opera), not_(firefox), samsung)
    if nome == "Chrome":
        return and_(not_(edge), not_(opera), not_(firefox), not_(samsung), chrome)
    if nome == "Safari":
        return and_(
            not_(edge), not_(opera), not_(firefox), not_(samsung), not_(chrome),
            coluna.contains("Version/", autoescape=True), coluna.contains("Safari/", autoescape=True),
        )
    if nome == "Internet Explorer":
        return and_(not_(edge), not_(opera), not_(firefox), not_(samsung), not_(chrome), ie)
    return false()


def padrao_rota(rota: str) -> str:
    """Rota normalizada ('/clientes/:id/testar') vira padrão LIKE ('/clientes/%/testar').

    Os caracteres especiais do LIKE no restante do texto são escapados (use `escape="\\\\"`).
    """

    escapado = rota.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escapado.replace(":id", "%")


__all__ = ["NAVEGADORES", "condicao_navegador", "padrao_rota"]
