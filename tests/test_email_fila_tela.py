"""Fila de e-mails na tela e na API (conferido no codigo-fonte) e o gatilho do servidor."""

from pathlib import Path

import luftbase
from luftbase.integracoes.email import fila_em_segundo_plano as fundo

RAIZ = Path(luftbase.__file__).parent
JS = (RAIZ / "interface" / "static" / "js" / "auditoria.js").read_text(encoding="utf-8")
HTML = (RAIZ / "interface" / "templates" / "luftbase" / "seguranca" / "_auditoria.html").read_text(encoding="utf-8")
API = (RAIZ / "web" / "auditoria.py").read_text(encoding="utf-8")
SERVIDOR = (RAIZ / "servidor.py").read_text(encoding="utf-8")


def test_aba_da_fila_so_para_quem_ve_dados_sensiveis_e_some_sem_a_tabela() -> None:
    trecho = HTML.split('data-log-tab="fila"')[0].rsplit("{%", 1)[-1]
    assert "pode_ver_dados_sensiveis_auditoria" in trecho
    assert "aba.hidden = !contagens" in JS  # tabela ainda nao migrada: contagem None, aba escondida
    assert "_contagem_fila_email() if ver_sensiveis else None" in API


def test_acoes_da_fila_exigem_csrf_e_permissao_e_sao_auditadas() -> None:
    trecho = API[API.index("def api_acao_fila_email") :]
    trecho = trecho[: trecho.index("@AuditoriaBp")]
    assert "validar_csrf_requisicao()" in trecho and "registrar_alteracao_auditoria(" in trecho
    assert 'acao not in {"reenviar", "cancelar"}' in trecho
    antes = API[: API.index("def api_acao_fila_email")].rsplit("@AuditoriaBp.post", 1)[-1]
    assert "AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR" in antes
    assert "X-CSRF-Token" in JS and "data-fila-acao" in JS


def test_servidor_liga_a_entrega_da_fila() -> None:
    assert "iniciar_fila_email" in SERVIDOR


def test_entrega_em_segundo_plano_liga_por_padrao_e_desliga_por_variavel(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv(fundo.VARIAVEL_ATIVO, raising=False)
    assert fundo.fila_ativa() is True
    for valor in ("false", "0", "nao"):
        monkeypatch.setenv(fundo.VARIAVEL_ATIVO, valor)
        assert fundo.fila_ativa() is False
    monkeypatch.setenv(fundo.VARIAVEL_INTERVALO, "0")
    assert fundo._inteiro(fundo.VARIAVEL_INTERVALO, 10, fundo.INTERVALO_MINIMO_SEGUNDOS) == fundo.INTERVALO_MINIMO_SEGUNDOS
