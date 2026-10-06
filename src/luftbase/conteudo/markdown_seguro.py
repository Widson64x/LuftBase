"""Markdown enxuto e seguro para o conteudo de comunicados e notas de atualizacao.

Todo texto e escapado ANTES de virar HTML; so as construcoes abaixo geram marcacao, entao um
conteudo digitado por um administrador nunca injeta `<script>`, atributos ou HTML cru.

Suporta: `#`/`##`/`###`, paragrafos, **negrito**, *italico*, `codigo`, listas (`-` e `1.`),
citacao (`>`), linha (`---`), links `[texto](https://...)`, imagens `![alt](fonte)` e destaques:

    :::sucesso
    Texto do destaque (tambem: info, alerta, perigo)
    :::

    :::cards
    ### Titulo do card
    Texto do card
    ### Outro card
    Texto
    :::

Fontes de imagem aceitas: `https://...` ou `luftbase:caminho/dentro/do/static.svg` (arquivos
estaticos do proprio LuftBase, resolvidos pelo prefixo da aplicacao).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape

from markupsafe import Markup

_DESTAQUES = {
    "info": "ph-info",
    "sucesso": "ph-check-circle",
    "alerta": "ph-warning",
    "perigo": "ph-warning-octagon",
}
_IMAGEM = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_CODIGO = re.compile(r"`([^`]+)`")
_NEGRITO = re.compile(r"\*\*(.+?)\*\*")
_ITALICO = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")
_LISTA = re.compile(r"^(\s*)([-*]|\d+\.)\s+(.*)$")
_CABECALHO = re.compile(r"^(#{1,3})\s+(.*)$")

ResolvedorEstatico = Callable[[str], str]


def _padrao_estatico(caminho: str) -> str:
    return f"/_luftbase/static/{caminho}"


def _fonte_imagem(fonte: str, estatico: ResolvedorEstatico) -> str | None:
    if fonte.startswith("luftbase:"):
        caminho = fonte[len("luftbase:") :].lstrip("/")
        if ".." in caminho or not re.fullmatch(r"[\w./-]+", caminho):
            return None
        return estatico(caminho)
    if fonte.startswith("https://"):
        return fonte
    return None


def _inline(texto: str, estatico: ResolvedorEstatico) -> str:
    """Escapa e aplica a marcacao em linha (a ordem importa: codigo e imagem primeiro)."""

    texto = texto.replace(chr(0), "")
    guardados: list[str] = []

    def guardar(html: str) -> str:
        guardados.append(html)
        return f"\x00{len(guardados) - 1}\x00"

    def imagem(m: re.Match[str]) -> str:
        fonte = _fonte_imagem(m.group(2), estatico)
        if fonte is None:
            return guardar(escape(m.group(0)))
        return guardar(
            f'<img class="md-img" src="{escape(fonte, quote=True)}" '
            f'alt="{escape(m.group(1), quote=True)}" loading="lazy">'
        )

    def link(m: re.Match[str]) -> str:
        return guardar(
            f'<a href="{escape(m.group(2), quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{escape(m.group(1))}</a>'
        )

    # As construcoes que carregam URL/codigo saem do texto antes do escape geral.
    texto = _CODIGO.sub(lambda m: guardar(f"<code>{escape(m.group(1))}</code>"), texto)
    texto = _IMAGEM.sub(imagem, texto)
    texto = _LINK.sub(link, texto)
    texto = escape(texto)
    texto = _NEGRITO.sub(r"<strong>\1</strong>", texto)
    texto = _ITALICO.sub(r"<em>\1</em>", texto)
    return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], texto)


def _blocos_simples(linhas: list[str], estatico: ResolvedorEstatico) -> str:
    saida: list[str] = []
    paragrafo: list[str] = []
    pilha: list[str] = []  # tags de lista abertas

    def fechar_paragrafo() -> None:
        if paragrafo:
            saida.append(f"<p>{_inline(' '.join(paragrafo), estatico)}</p>")
            paragrafo.clear()

    def fechar_listas() -> None:
        while pilha:
            saida.append(f"</{pilha.pop()}>")

    for bruta in linhas:
        linha = bruta.rstrip()
        if not linha.strip():
            fechar_paragrafo()
            fechar_listas()
            continue
        cabecalho = _CABECALHO.match(linha)
        if cabecalho:
            fechar_paragrafo()
            fechar_listas()
            nivel = len(cabecalho.group(1)) + 1  # h2..h4: o h1 e o titulo da publicacao
            saida.append(f"<h{nivel}>{_inline(cabecalho.group(2), estatico)}</h{nivel}>")
            continue
        if re.fullmatch(r"-{3,}", linha.strip()):
            fechar_paragrafo()
            fechar_listas()
            saida.append("<hr>")
            continue
        if linha.startswith(">"):
            fechar_paragrafo()
            fechar_listas()
            saida.append(f"<blockquote>{_inline(linha.lstrip('> ').strip(), estatico)}</blockquote>")
            continue
        item = _LISTA.match(linha)
        if item:
            fechar_paragrafo()
            tag = "ol" if item.group(2)[0].isdigit() else "ul"
            if not pilha or pilha[-1] != tag:
                fechar_listas()
                saida.append(f"<{tag}>")
                pilha.append(tag)
            saida.append(f"<li>{_inline(item.group(3), estatico)}</li>")
            continue
        fechar_listas()
        paragrafo.append(linha.strip())
    fechar_paragrafo()
    fechar_listas()
    return "".join(saida)


def _cards(linhas: list[str], estatico: ResolvedorEstatico) -> str:
    cards: list[tuple[str, list[str]]] = []
    for linha in linhas:
        cabecalho = _CABECALHO.match(linha)
        if cabecalho:
            cards.append((cabecalho.group(2), []))
        elif cards:
            cards[-1][1].append(linha)
    html = []
    for titulo, corpo in cards:
        html.append(
            f'<div class="md-card"><h4>{_inline(titulo, estatico)}</h4>'
            f"{_blocos_simples(corpo, estatico)}</div>"
        )
    return f'<div class="md-cards">{"".join(html)}</div>'


def renderizar(texto: str | None, estatico: ResolvedorEstatico = _padrao_estatico) -> Markup:
    """Converte o texto em HTML seguro (`Markup`)."""

    linhas = (texto or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    saida: list[str] = []
    pendentes: list[str] = []
    i = 0

    def descarregar() -> None:
        if pendentes:
            saida.append(_blocos_simples(pendentes, estatico))
            pendentes.clear()

    while i < len(linhas):
        abertura = re.fullmatch(r":::\s*(\w+)\s*", linhas[i].strip())
        if abertura and (abertura.group(1) in _DESTAQUES or abertura.group(1) == "cards"):
            descarregar()
            tipo = abertura.group(1)
            i += 1
            corpo: list[str] = []
            while i < len(linhas) and linhas[i].strip() != ":::":
                corpo.append(linhas[i])
                i += 1
            i += 1  # consome o fechamento
            if tipo == "cards":
                saida.append(_cards(corpo, estatico))
            else:
                saida.append(
                    f'<div class="md-destaque md-{tipo}"><i class="ph-bold {_DESTAQUES[tipo]}"></i>'
                    f"<div>{_blocos_simples(corpo, estatico)}</div></div>"
                )
            continue
        pendentes.append(linhas[i])
        i += 1
    descarregar()
    return Markup("".join(saida))  # noqa: S704 - todo texto passa por escape() acima


__all__ = ["renderizar"]
