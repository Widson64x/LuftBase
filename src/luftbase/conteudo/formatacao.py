"""Une os dois formatos de conteudo das publicacoes: markdown seguro (legado) e HTML do editor rico."""

from __future__ import annotations

from collections.abc import Callable

from markupsafe import Markup

from luftbase.conteudo.html_seguro import resolver_imagens, sanitizar, texto_puro
from luftbase.conteudo.markdown_seguro import ResolvedorEstatico, renderizar

FORMATO_MARKDOWN = "MARKDOWN"
FORMATO_HTML = "HTML"
FORMATOS = (FORMATO_MARKDOWN, FORMATO_HTML)

_LIMITE_RESUMO = 280


_ASSINATURAS = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def detectar_tipo_imagem(dados: bytes) -> str | None:
    """Tipo MIME pelos bytes iniciais (nunca pelo nome ou pelo tipo declarado pelo navegador)."""

    for assinatura, tipo in _ASSINATURAS:
        if dados.startswith(assinatura):
            return tipo
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return None


def normalizar_conteudo(conteudo: str, formato: str) -> str:
    """Conteudo pronto para gravar: o HTML sempre passa pelo sanitizador."""

    return sanitizar(conteudo) if formato == FORMATO_HTML else conteudo


def renderizar_conteudo(
    conteudo: str | None,
    formato: str,
    estatico: ResolvedorEstatico,
    url_imagem: Callable[[int], str],
) -> Markup:
    """HTML seguro para exibir, qualquer que seja o formato gravado."""

    if formato == FORMATO_HTML:
        corpo = resolver_imagens(sanitizar(conteudo), url_imagem, estatico)
        return Markup(corpo)  # noqa: S704 - saida do sanitizador de lista fechada
    return renderizar(conteudo, estatico)


def resumo_automatico(conteudo: str | None, formato: str, limite: int = _LIMITE_RESUMO) -> str:
    """Texto curto (sem marcacao) para notificacao e listas quando o autor nao escreveu resumo."""

    html = sanitizar(conteudo) if formato == FORMATO_HTML else str(renderizar(conteudo))
    texto = texto_puro(html)
    if len(texto) <= limite:
        return texto
    corte = texto[:limite].rsplit(" ", 1)[0].rstrip(".,;:- ")
    return f"{corte or texto[:limite]}…"


__all__ = [
    "detectar_tipo_imagem",
    "FORMATOS",
    "FORMATO_HTML",
    "FORMATO_MARKDOWN",
    "normalizar_conteudo",
    "renderizar_conteudo",
    "resumo_automatico",
]
