"""Leitura do User-Agent e historico de sessoes do perfil."""

from __future__ import annotations

from pathlib import Path

import pytest

from luftbase import servidor
from luftbase.identidade.agente_usuario import interpretar_agente

RAIZ = Path(servidor.__file__).resolve().parent / "interface"
JS = (RAIZ / "static" / "js" / "perfil.js").read_text(encoding="utf-8")
DRAWER = (RAIZ / "templates" / "luftbase" / "perfil" / "drawer.html").read_text(encoding="utf-8")

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
EDGE = CHROME + " Edg/126.0.2592.81"
FIREFOX = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0"
SAFARI_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
ANDROID = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"


@pytest.mark.parametrize(
    ("agente", "navegador", "sistema", "dispositivo"),
    [
        (CHROME, "Chrome 126", "Windows", "desktop"),
        (EDGE, "Edge 126", "Windows", "desktop"),
        (FIREFOX, "Firefox 128", "Windows", "desktop"),
        (SAFARI_IOS, "Safari 17", "iOS", "mobile"),
        (ANDROID, "Chrome 126", "Android", "mobile"),
    ],
)
def test_interpreta_navegador_sistema_e_dispositivo(agente, navegador, sistema, dispositivo) -> None:
    lido = interpretar_agente(agente)

    assert (lido["navegador"], lido["sistema"], lido["dispositivo"]) == (navegador, sistema, dispositivo)
    assert lido["descricao"] == f"{navegador} em {sistema}"


def test_agente_vazio_nao_quebra() -> None:
    assert interpretar_agente(None)["descricao"] == "Desconhecido"
    assert interpretar_agente("curl/8")["descricao"] == "Navegador desconhecido"


def test_drawer_tem_o_historico_de_acessos() -> None:
    assert "luft-perfil-historico-lista" in DRAWER
    assert "carregarHistoricoSessoes" in JS and "/perfil/sessoes/historico" in JS
