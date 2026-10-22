"""A tela de Auditoria v2: filtros que se aplicam sozinhos, tempo real e a aba de alertas (conferidos no codigo-fonte)."""

from pathlib import Path

import luftbase

RAIZ = Path(luftbase.__file__).parent / "interface"
JS = (RAIZ / "static" / "js" / "auditoria.js").read_text(encoding="utf-8")
HTML = (RAIZ / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "css" / "auditoria.css").read_text(encoding="utf-8")
AO_VIVO = (RAIZ / "static" / "js" / "auditoria_ao_vivo.js").read_text(encoding="utf-8")


def test_consulta_nova_cancela_a_anterior_e_botao_ignora_cache() -> None:
    assert "AbortController" in JS and "estado.controle?.abort()" in JS
    assert "AbortError" in JS
    assert "p.set('fresco', '1')" in JS
    assert "p.set('opcoes', '0')" in JS  # listas pesadas so quando muda periodo ou sistema


def test_filtros_se_aplicam_sozinhos_e_tem_limpar_e_mais_filtros() -> None:
    assert "aplicarDepois" in JS and "limparFiltros" in JS
    for ident in ("auditBtnLimpar", "auditBtnMais", "auditMaisContagem", "auditTempoReal"):
        assert f'id="{ident}"' in HTML
    assert "audit-field-extra" in HTML and ".audit-filters.mais .audit-field-extra" in CSS


def test_tempo_real_so_com_aba_visivel() -> None:
    assert "setInterval" in JS and "document.hidden" in JS and "luftAuditoriaTempoReal" in JS


def test_aba_de_alertas_na_barra_de_registros() -> None:
    assert 'data-log-tab="alertas"' in HTML and 'id="auditAlertaSituacoes"' in HTML
    for situacao in ("abertos", "silenciados", "resolvidos", "todos"):
        assert f'data-situacao="{situacao}"' in HTML
    assert "data-alertas-url" in HTML and "data-silenciar-alerta-url" in HTML
    assert "data-kpi=\"alertas_abertos\"" in HTML and 'id="auditNavAlertas"' in HTML
    assert "X-CSRF-Token" in JS and "data-silenciar" in JS


def test_alertas_so_para_quem_ve_dados_sensiveis() -> None:
    trecho = HTML.split('data-log-tab="alertas"')[0].rsplit("{%", 1)[-1]
    assert "pode_ver_dados_sensiveis_auditoria" in trecho


def test_ao_vivo_mostra_quando_a_sessao_expira() -> None:
    assert "expira_em_segundos" in AO_VIVO
