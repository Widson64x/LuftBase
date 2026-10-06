"""Le o `User-Agent` do navegador em navegador, sistema e tipo de dispositivo (sem dependencias)."""

from __future__ import annotations

import re

# A ordem importa: Edge, Opera e Chromium de terceiros tambem dizem "Chrome"; todo mundo diz "Safari".
_NAVEGADORES = (
    ("Edge", r"\b(?:Edg|EdgA|EdgiOS|Edge)/([\d.]+)"),
    ("Opera", r"\b(?:OPR|OPiOS)/([\d.]+)"),
    ("Firefox", r"\b(?:Firefox|FxiOS)/([\d.]+)"),
    ("Samsung Internet", r"\bSamsungBrowser/([\d.]+)"),
    ("Chrome", r"\b(?:Chrome|CriOS)/([\d.]+)"),
    ("Safari", r"\bVersion/([\d.]+).*Safari/"),
    ("Internet Explorer", r"\b(?:MSIE |Trident/.*rv:)([\d.]+)"),
)
_SISTEMAS = (
    ("Windows", r"Windows NT"),
    ("Android", r"Android"),
    ("iOS", r"iPhone|iPad|iPod"),
    ("macOS", r"Mac OS X|Macintosh"),
    ("ChromeOS", r"CrOS"),
    ("Linux", r"Linux|X11"),
)


def interpretar_agente(user_agent: str | None) -> dict[str, str]:
    """Devolve `navegador`, `sistema`, `dispositivo` (desktop|mobile|tablet) e `descricao`."""

    texto = (user_agent or "").strip()
    if not texto:
        return {"navegador": "", "sistema": "", "dispositivo": "desktop", "descricao": "Desconhecido"}

    navegador = ""
    for nome, padrao in _NAVEGADORES:
        achado = re.search(padrao, texto)
        if achado:
            navegador = f"{nome} {achado.group(1).split('.')[0]}"
            break
    sistema = next((nome for nome, padrao in _SISTEMAS if re.search(padrao, texto)), "")

    if re.search(r"iPad|Tablet", texto) or (
        "Android" in texto and not re.search(r"Mobile", texto)
    ):
        dispositivo = "tablet"
    elif re.search(r"Mobile|iPhone|iPod", texto):
        dispositivo = "mobile"
    else:
        dispositivo = "desktop"

    partes = [p for p in (navegador, sistema) if p]
    return {
        "navegador": navegador,
        "sistema": sistema,
        "dispositivo": dispositivo,
        "descricao": " em ".join(partes) if partes else "Navegador desconhecido",
    }


__all__ = ["interpretar_agente"]
