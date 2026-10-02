"""Geracao da parte `text/plain` a partir do HTML do e-mail."""

from __future__ import annotations

import re
from html.parser import HTMLParser

_TAGS_IGNORADAS = frozenset({"head", "script", "style", "title"})
_TAGS_BLOCO = frozenset(
    {"br", "div", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "li", "p", "table", "tr"}
)
_ESPACOS = re.compile(r"[ \t\f\v\xa0]+")
_ESPACOS_HTML = re.compile(r"[ \t\n\r\f\v]+")
_LINHAS_VAZIAS = re.compile(r"\n{3,}")


class _ExtratorTexto(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._partes: list[str] = []
        self._ignorando = 0
        self._link: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _TAGS_IGNORADAS:
            self._ignorando += 1
        elif tag in _TAGS_BLOCO:
            self._partes.append("\n")
        elif tag == "td":
            self._partes.append(" ")
        elif tag == "a":
            self._link = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag in _TAGS_IGNORADAS:
            self._ignorando = max(0, self._ignorando - 1)
        elif tag in _TAGS_BLOCO:
            self._partes.append("\n")
        elif tag == "a" and self._link:
            # Clientes sem HTML precisam do endereco, que so existia no atributo.
            if self._link.startswith(("http://", "https://")):
                self._partes.append(f" ({self._link})")
            self._link = None

    def handle_data(self, data: str) -> None:
        # Quebras de linha do codigo-fonte nao tem valor em HTML; so as tags de bloco quebram.
        if not self._ignorando:
            self._partes.append(_ESPACOS_HTML.sub(" ", data))

    def texto(self) -> str:
        linhas = (_ESPACOS.sub(" ", linha).strip() for linha in "".join(self._partes).split("\n"))
        return _LINHAS_VAZIAS.sub("\n\n", "\n".join(linhas)).strip()


def gerar_texto_de_html(html: str) -> str:
    """Extrai um texto legivel, preservando paragrafos e o destino dos links."""

    extrator = _ExtratorTexto()
    extrator.feed(html)
    extrator.close()
    return extrator.texto()
