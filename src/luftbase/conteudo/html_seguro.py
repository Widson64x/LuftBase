"""Sanitizador de HTML do editor rico de comunicados (lista fechada, sem dependencias externas).

O editor visual devolve HTML. Nada dele e confiavel: antes de gravar e antes de exibir, o texto passa
por `sanitizar`, que reescreve o documento so com o que esta nas listas abaixo. Tag fora da lista perde
a marcacao (o texto fica), e as de conteudo executavel (`script`, `style`, `iframe`...) somem inteiras.
Atributos de evento (`onclick`...) e URLs `javascript:`/`data:` nunca passam.

Imagens: o editor envia as imagens para a propria plataforma (`/publicacoes/imagem/<id>`). No banco
elas ficam como `luftimg:<id>`, independentes do prefixo da aplicacao; `resolver_imagens` troca pela URL
real so na hora de exibir.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from html import escape, unescape
from html.parser import HTMLParser

_VAZIAS = frozenset({"br", "hr", "img"})
_PERMITIDAS = frozenset(
    {
        "p", "div", "span", "br", "hr", "h2", "h3", "h4", "strong", "em", "u", "s", "sub", "sup",
        "ul", "ol", "li", "blockquote", "a", "img", "code",
        "table", "thead", "tbody", "tr", "th", "td",
    }
)  # fmt: skip
_EQUIVALENTES = {"b": "strong", "i": "em", "strike": "s", "del": "s", "h1": "h2", "h5": "h4", "h6": "h4"}
_DESCARTAR_COM_CONTEUDO = frozenset(
    {"script", "style", "iframe", "object", "embed", "template", "noscript", "svg", "math", "head", "title"}
)
_CLASSES_DIV = frozenset({"pub-callout", "pub-info", "pub-sucesso", "pub-alerta", "pub-perigo"})

_COR = re.compile(
    r"^(#[0-9a-fA-F]{3,8}|rgba?\(\s*\d{1,3}\s*(,\s*\d{1,3}\s*){2}(,\s*(0|1|0?\.\d+)\s*)?\)|[a-zA-Z]{3,20}|transparent)$"
)
_TAMANHO_FONTE = re.compile(r"^(\d{1,2}(\.\d+)?)(px|pt|em|rem|%)$")
_LARGURA = re.compile(r"^(\d{1,4})(px|%)$")
_IMAGEM_INTERNA = re.compile(r"^(?:luftimg:|(?:https?://[^/\s]+)?(?:/[\w.-]+)*/publicacoes/imagem/)(\d{1,18})$")
_IMAGEM_ESTATICA = re.compile(r"^(?:https?://[^/\s]+)?(?:/[\w.-]+)*/static/((?:img|icons)/[\w./-]+)$")
_NUMERO = re.compile(r"^\d{1,2}$")

_LIMITE_FONTE_PX = 72.0


def _estilo_seguro(valor: str, tag: str) -> str:
    saida: list[str] = []
    for trecho in valor.split(";"):
        if ":" not in trecho:
            continue
        nome, _, bruto = trecho.partition(":")
        nome = nome.strip().lower()
        bruto = bruto.strip()
        if not bruto or len(bruto) > 60 or any(c in bruto for c in "\\<>{}\"'@"):
            continue
        if "url(" in bruto.lower() or "expression" in bruto.lower():
            continue
        if nome in {"color", "background-color"} and _COR.match(bruto):
            saida.append(f"{nome}: {bruto}")
        elif nome == "font-size":
            casado = _TAMANHO_FONTE.match(bruto)
            if casado:
                numero = float(casado.group(1))
                unidade = casado.group(3)
                px = numero * {"px": 1, "pt": 1.34, "em": 16, "rem": 16, "%": 0.16}[unidade]
                if 8 <= px <= _LIMITE_FONTE_PX:
                    saida.append(f"font-size: {bruto}")
        elif nome == "text-align" and bruto in {"left", "right", "center", "justify"}:
            saida.append(f"text-align: {bruto}")
        elif nome == "font-weight" and bruto in {"bold", "normal", "600", "700", "800"}:
            saida.append(f"font-weight: {bruto}")
        elif nome == "font-style" and bruto in {"italic", "normal"}:
            saida.append(f"font-style: {bruto}")
        elif nome == "text-decoration" and bruto in {"underline", "line-through", "none"}:
            saida.append(f"text-decoration: {bruto}")
        elif nome in {"width", "max-width"} and tag in {"img", "table", "td", "th"}:
            casado = _LARGURA.match(bruto)
            if casado and 1 <= int(casado.group(1)) <= (100 if casado.group(2) == "%" else 1600):
                saida.append(f"{nome}: {bruto}")
    return "; ".join(saida)


def _href_seguro(valor: str) -> str | None:
    destino = valor.strip()
    if re.match(r"^(https?://|mailto:)[^\s<>\"']+$", destino, re.IGNORECASE):
        return destino
    return None


def _src_imagem(valor: str) -> str | None:
    fonte = valor.strip()
    interna = _IMAGEM_INTERNA.match(fonte)
    if interna:
        return f"luftimg:{interna.group(1)}"
    estatica = _IMAGEM_ESTATICA.match(fonte)
    if estatica and ".." not in estatica.group(1):
        return f"luftbase:{estatica.group(1)}"
    if fonte.startswith("luftbase:") and re.fullmatch(r"luftbase:(?:img|icons)/[\w./-]+", fonte) and ".." not in fonte:
        return fonte
    if re.match(r"^https://[^\s<>\"']+$", fonte):
        return fonte
    return None


class _Limpador(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.saida: list[str] = []
        self._abertas: list[str] = []
        self._descartando = 0
        self._tag_descartada: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._descartando:
            if tag in _DESCARTAR_COM_CONTEUDO and tag not in _VAZIAS:
                self._tag_descartada.append(tag)
                self._descartando += 1
            return
        if tag in _DESCARTAR_COM_CONTEUDO:
            self._descartando = 1
            self._tag_descartada = [tag]
            return
        tag = _EQUIVALENTES.get(tag, tag)
        if tag not in _PERMITIDAS:
            return
        atributos = {nome.lower(): (valor or "") for nome, valor in attrs}
        partes: list[str] = []
        if tag == "a":
            href = _href_seguro(atributos.get("href", ""))
            if href is None:
                return
            partes.append(f' href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer"')
        elif tag == "img":
            fonte = _src_imagem(atributos.get("src", ""))
            if fonte is None:
                return
            partes.append(f' src="{escape(fonte, quote=True)}"')
            partes.append(f' alt="{escape(atributos.get("alt", "")[:200], quote=True)}"')
        elif tag in {"td", "th"}:
            for nome in ("colspan", "rowspan"):
                if _NUMERO.match(atributos.get(nome, "")):
                    partes.append(f' {nome}="{atributos[nome]}"')
        elif tag == "div":
            classes = [c for c in atributos.get("class", "").split() if c in _CLASSES_DIV]
            if classes:
                partes.append(f' class="{" ".join(classes)}"')
        if tag in {"p", "div", "span", "li", "td", "th", "h2", "h3", "h4", "blockquote", "img", "table", "ul", "ol"}:
            estilo = _estilo_seguro(atributos.get("style", ""), tag)
            if estilo:
                partes.append(f' style="{escape(estilo, quote=True)}"')
        self.saida.append(f"<{tag}{''.join(partes)}>")
        if tag not in _VAZIAS:
            self._abertas.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VAZIAS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._descartando:
            if self._tag_descartada and tag == self._tag_descartada[-1]:
                self._tag_descartada.pop()
                self._descartando -= 1
            return
        tag = _EQUIVALENTES.get(tag, tag)
        if tag in _VAZIAS or tag not in self._abertas:
            return
        while self._abertas:
            topo = self._abertas.pop()
            self.saida.append(f"</{topo}>")
            if topo == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._descartando:
            self.saida.append(escape(data, quote=False))

    def concluir(self) -> str:
        while self._abertas:
            self.saida.append(f"</{self._abertas.pop()}>")
        return "".join(self.saida)


def sanitizar(html: str | None) -> str:
    """Reescreve o HTML so com as marcacoes permitidas (idempotente)."""

    limpador = _Limpador()
    limpador.feed((html or "").replace("\x00", ""))
    limpador.close()
    return limpador.concluir()


def resolver_imagens(
    html: str,
    url_imagem: Callable[[int], str],
    estatico: Callable[[str], str] | None = None,
) -> str:
    """Troca `luftimg:<id>` e `luftbase:<caminho>` pela URL real (ao exibir ou ao abrir no editor)."""

    html = re.sub(
        r'src="luftimg:(\d{1,18})"',
        lambda m: f'src="{escape(url_imagem(int(m.group(1))), quote=True)}" loading="lazy"',
        html,
    )
    if estatico is None:
        return html
    return re.sub(
        r'src="luftbase:([\w./-]+)"',
        lambda m: f'src="{escape(estatico(m.group(1)), quote=True)}" loading="lazy"',
        html,
    )


_BLOCOS = re.compile(r"</?(p|div|br|hr|h[1-6]|li|ul|ol|tr|blockquote|table)\b[^>]*>", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


def texto_puro(html: str | None) -> str:
    """Texto corrido do HTML, sem marcacao, para resumos, notificacoes e busca."""

    texto = _BLOCOS.sub(" ", html or "")
    texto = _TAGS.sub("", texto)
    return re.sub(r"\s+", " ", unescape(texto)).strip()


def ids_imagens(html: str | None) -> set[int]:
    """Ids das imagens internas citadas no HTML (para vincular os anexos a publicacao)."""

    return {int(i) for i in re.findall(r'src="luftimg:(\d{1,18})"', html or "")}


__all__ = ["ids_imagens", "resolver_imagens", "sanitizar", "texto_puro"]
