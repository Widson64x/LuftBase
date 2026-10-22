"""Sessoes: piso de 30 minutos, 'lembrar acesso' de 1 dia e encerramento das sessoes vencidas (sem precisar de uso)."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from test_armazenamento_postgresql import _preparar_armazenamento

from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.infraestrutura.variaveis_ambiente import PERMITIDAS, ErroVariavel
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core.sessoes import EventoSessao, Sessao

BASE = {
    "LUFT_SISTEMA_ID": 0,
    "LUFT_AMBIENTE": "desenvolvimento",
    "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
    "LUFT_LDAP_SERVIDOR": "ldap.invalid",
    "LUFT_LDAP_DOMINIO": "luft",
}


# ---------------------------------------------------------------- politica


@pytest.mark.parametrize("configurado", [1, 10, 15, 29])
def test_ttl_abaixo_de_30_minutos_sobe_para_30_e_avisa(configurado: int, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="luftbase.configuracao"):
        configuracao = ConfiguracaoLuftBase.de_mapeamento({**BASE, "LUFT_SESSAO_TTL_MINUTOS": configurado})

    assert configuracao.sessao.ttl_minutos == 30
    assert any("minimo de 30 minutos" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("configurado", [30, 45, 720])
def test_ttl_a_partir_de_30_minutos_nao_muda(configurado: int, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="luftbase.configuracao"):
        configuracao = ConfiguracaoLuftBase.de_mapeamento({**BASE, "LUFT_SESSAO_TTL_MINUTOS": configurado})

    assert configuracao.sessao.ttl_minutos == configurado
    assert not caplog.records


def test_valor_invalido_continua_recusado() -> None:
    from luftbase.nucleo.excecoes import ErroConfiguracao

    with pytest.raises(ErroConfiguracao):
        ConfiguracaoLuftBase.de_mapeamento({**BASE, "LUFT_SESSAO_TTL_MINUTOS": "0"})


def test_padrao_e_60_minutos_e_lembrar_acesso_vale_um_dia() -> None:
    sessao = ConfiguracaoLuftBase.de_mapeamento(BASE).sessao

    assert sessao.ttl_minutos == 60
    assert sessao.ttl_lembrar_dias == 1


def test_painel_nao_aceita_gravar_menos_de_30_minutos() -> None:
    validar = next(v for v in PERMITIDAS if v.chave == "LUFT_SESSAO_TTL_MINUTOS").validar

    assert validar("30") == "30"
    for recusado in ("15", "29", "0", "abc"):
        with pytest.raises(ErroVariavel):
            validar(recusado)


# ---------------------------------------------------------------- varredura das vencidas


def _sessao(armazenamento, nome: str, *, usuario: int | None, login: str | None, ttl: int = 3600):  # type: ignore[no-untyped-def]
    envelope = {"versao": 1, "dados": {"luftbase_usuario": {"id_usuario": usuario, "login": login}} if usuario else {}}
    armazenamento.salvar(f"luft:sessao:{nome}", json.dumps(envelope).encode("utf-8"), ttl)


def _vencer(banco, nome: str, *, horas_ociosa: float = 38.0, prazo_min: int = 60) -> None:  # type: ignore[no-untyped-def]
    """Deixa a sessao como a do caso real: ultima acao ha `horas_ociosa` h e prazo de `prazo_min` min depois dela."""

    ultima = agora_local() - timedelta(hours=horas_ociosa)
    with banco.unidade_trabalho() as s:
        registro = s.get(Sessao, nome)
        registro.ultima_atividade = ultima
        registro.expira_em = ultima + timedelta(minutes=prazo_min)


def test_sessao_vencida_e_encerrada_mesmo_sem_ninguem_usar_o_cookie() -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "rafael", usuario=1, login="rafael.cunha")
    _sessao(armazenamento, "widson", usuario=2, login="widson.araujo")
    _vencer(banco, "rafael", horas_ociosa=38, prazo_min=60)

    encerradas = armazenamento.expirar_vencidas()

    assert encerradas == 1
    with banco.leitura() as s:
        rafael, widson = s.get(Sessao, "rafael"), s.get(Sessao, "widson")
        assert (rafael.status, rafael.motivo_encerramento) == ("EXPIRADA", "TIMEOUT_INATIVIDADE")
        assert rafael.encerrada_em == rafael.expira_em  # terminou quando o prazo venceu, nao quando alguem olhou
        assert rafael.dados_sessao is None  # o payload da sessao nao fica guardado
        assert widson.status == "ATIVA"  # quem esta dentro do prazo nao e tocado
        (evento,) = s.query(EventoSessao).filter_by(id_sessao="rafael", tipo_evento="TIMEOUT").all()
        assert "prazo de 60 min sem acao" in evento.detalhes


def test_varredura_e_idempotente_e_nao_duplica_eventos() -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "a", usuario=1, login="ana")
    _vencer(banco, "a")

    assert armazenamento.expirar_vencidas() == 1
    assert armazenamento.expirar_vencidas() == 0

    with banco.leitura() as s:
        assert s.query(EventoSessao).filter_by(id_sessao="a", tipo_evento="TIMEOUT").count() == 1


def test_sessao_anonima_vencida_tambem_e_encerrada_sem_evento() -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "visitante", usuario=None, login=None)
    _vencer(banco, "visitante")

    assert armazenamento.expirar_vencidas() == 1

    with banco.leitura() as s:
        assert s.get(Sessao, "visitante").status == "EXPIRADA"
        assert s.query(EventoSessao).filter_by(id_sessao="visitante", tipo_evento="TIMEOUT").count() == 0


def test_sessao_expirada_nao_volta_a_ficar_online_por_gravacao_tardia() -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "a", usuario=1, login="ana")
    _vencer(banco, "a")
    armazenamento.expirar_vencidas()

    _sessao(armazenamento, "a", usuario=1, login="ana")  # uma aba esquecida tenta renovar

    with banco.leitura() as s:
        assert s.get(Sessao, "a").status == "EXPIRADA"
    assert armazenamento.listar_usuarios_online() == []


def test_varredura_e_disparada_no_maximo_uma_vez_por_minuto(monkeypatch: pytest.MonkeyPatch) -> None:
    armazenamento, _banco = _preparar_armazenamento()
    chamadas: list[int] = []
    monkeypatch.setattr(armazenamento, "expirar_vencidas", lambda **_k: chamadas.append(1) or 0)

    for _ in range(5):
        armazenamento._varrer_se_for_hora()  # noqa: SLF001

    assert chamadas == [1]


def test_listar_online_ja_nao_traz_quem_venceu() -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "rafael", usuario=1, login="rafael.cunha")
    _sessao(armazenamento, "widson", usuario=2, login="widson.araujo")
    _vencer(banco, "rafael")

    assert [u["login_usuario"] for u in armazenamento.listar_usuarios_online()] == ["widson.araujo"]  # ja escondida pelo prazo
    armazenamento._proxima_varredura = 0.0  # noqa: SLF001 - passou o minuto entre uma varredura e outra
    online = armazenamento.listar_usuarios_online()

    assert [u["login_usuario"] for u in online] == ["widson.araujo"]
    with banco.leitura() as s:
        assert s.get(Sessao, "rafael").status == "EXPIRADA"  # listar tambem limpa a linha, nao so esconde


def test_log_diz_quem_teve_a_sessao_encerrada(caplog: pytest.LogCaptureFixture) -> None:
    armazenamento, banco = _preparar_armazenamento()
    _sessao(armazenamento, "r", usuario=1, login="rafael.cunha")
    _vencer(banco, "r")

    with caplog.at_level(logging.INFO, logger="luftbase.sessoes"):
        armazenamento.expirar_vencidas()

    assert any("1 sessao(oes) vencida(s) por inatividade foram encerradas (rafael.cunha)" in r.getMessage() for r in caplog.records)
