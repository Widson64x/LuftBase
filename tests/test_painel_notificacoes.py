"""O painel de notificacoes: o JS, o HTML e o CSS precisam continuar combinando entre si."""

from __future__ import annotations

import re
from pathlib import Path

import luftbase

RAIZ = Path(luftbase.__file__).resolve().parent / "interface"
JS = (RAIZ / "static/js/notificacoes_v2.js").read_text(encoding="utf-8")
CSS = (RAIZ / "static/css/notificacoes_v2.css").read_text(encoding="utf-8")
DRAWER = (RAIZ / "templates/luftbase/notificacoes/drawer.html").read_text(encoding="utf-8")
BASE = (RAIZ / "templates/luftbase/base.html").read_text(encoding="utf-8")


def test_todo_id_usado_pelo_js_existe_no_drawer() -> None:
    usados = set(re.findall(r"getElementById\('([^']+)'\)", JS)) | set(
        re.findall(r"porId\('([^']+)'\)", JS)
    )
    # `luftbase-notif-config` e o bloco de configuracao, no topo do mesmo template.
    faltando = {i for i in usados if f'id="{i}"' not in DRAWER}

    assert not faltando, f"ids do JS sem elemento no drawer: {sorted(faltando)}"


def test_base_carrega_os_arquivos_novos_e_eles_existem() -> None:
    assert "js/notificacoes_v2.js" in BASE and "css/notificacoes_v2.css" in BASE
    # O arquivo antigo saiu: carrega-lo de novo duplicaria o objeto e os cliques.
    assert "js/notificacoes.js" not in BASE
    assert not (RAIZ / "static/js/notificacoes.js").exists()


def test_chamadas_externas_ao_painel_continuam_existindo() -> None:
    # base.js e o botao do sino chamam estes metodos.
    for metodo in ("abrirDrawer", "fecharDrawer", "atualizarBadge", "marcarComoLida"):
        assert re.search(rf"\b{metodo}:\s*function", JS), metodo
    assert "window.LuftNotificacoes = LuftNotificacoes" in JS


def test_classes_usadas_na_renderizacao_tem_estilo() -> None:
    classes = set(re.findall(r'class="((?:luft-notif-[\w-]+\s?)+)', JS))
    estilizadas = {
        c
        for lista in classes
        for c in lista.split()
        if f".{c}" not in CSS and f".{c}" not in (RAIZ / "static/css/notificacoes.css").read_text(encoding="utf-8")
    }

    assert not estilizadas, f"classes sem CSS: {sorted(estilizadas)}"


def test_links_perigosos_nao_viram_botao() -> None:
    # `_urlSegura` so aceita caminho do proprio site ou http(s).
    corpo = JS[JS.index("_urlSegura: function") : JS.index("_renderizarLista: function")]

    assert "startsWith('/')" in corpo and "https?" in corpo
    assert "javascript" not in corpo.lower()
