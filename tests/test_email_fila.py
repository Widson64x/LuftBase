"""Fila de e-mails: enfileirar, entregar em lote, tentar de novo, reservar sem duplicar e manter."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pytest
from core_sqlite import motor_sqlite as _motor
from sqlalchemy import select, update

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.integracoes.email.fila import (
    ESPERAS_SEGUNDOS,
    MAXIMO_TENTATIVAS,
    FilaEmail,
)
from luftbase.nucleo.excecoes import EmailNaoConfigurado, ErroEmail
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.email_fila import EmailFila


@dataclass
class EmailFalso:
    configurado: bool = True
    falhar_para: set[str] = field(default_factory=set)
    sem_configuracao: bool = False
    preparados: list[dict[str, Any]] = field(default_factory=list)
    lotes: list[int] = field(default_factory=list)

    def preparar(self, para: Any, assunto: str, **opcoes: Any) -> dict[str, Any]:
        if self.sem_configuracao:
            raise EmailNaoConfigurado("sem e-mail")
        if "invalido" in str(para):
            raise ErroEmail("endereco invalido")
        item = {"para": list(para), "assunto": assunto, **opcoes}
        self.preparados.append(item)
        return item

    def enviar_lote(self, envios: list[dict[str, Any]]) -> list[Any]:
        self.lotes.append(len(envios))
        return [
            type(
                "R",
                (),
                {"sucesso": e["para"][0] not in self.falhar_para, "erro": "smtp fora"},
            )()
            for e in envios
        ]


@pytest.fixture
def banco() -> BancoSQLAlchemy:
    return BancoSQLAlchemy("core", _motor(BaseLuft, "core"))


def _fila(banco: BancoSQLAlchemy, email: EmailFalso | None = None) -> tuple[FilaEmail, EmailFalso]:
    email = email or EmailFalso()
    return FilaEmail(banco, email), email  # type: ignore[arg-type]


def _linhas(banco: BancoSQLAlchemy) -> list[EmailFila]:
    with banco.leitura() as s:
        return list(s.execute(select(EmailFila).order_by(EmailFila.id_email)).scalars())


def test_enfileirar_so_grava_e_nao_envia(banco: BancoSQLAlchemy) -> None:
    fila, email = _fila(banco)
    ids = fila.enfileirar_varios(
        [
            fila.montar(
                f"p{i}@luft.com", "Oi", template="t.html", contexto={"nome": f"P{i}"}, origem="TESTE"
            )
            for i in range(200)
        ]
    )
    assert len(ids) == 200
    assert email.preparados == [] and email.lotes == []
    assert fila.contar() == {"pendentes": 200, "enviados": 0, "falhas": 0, "todos": 200}
    primeira = _linhas(banco)[0]
    assert json.loads(primeira.destinatarios) == ["p0@luft.com"]
    assert json.loads(primeira.contexto or "{}") == {"nome": "P0"} and primeira.status == "PENDENTE"


def test_validacao_de_uso_acontece_ao_enfileirar(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco)
    with pytest.raises(ErroEmail):
        fila.montar([], "Oi", texto="x")
    with pytest.raises(ErroEmail):
        fila.montar("a@luft.com", "  ", texto="x")
    with pytest.raises(ErroEmail):
        fila.montar("a@luft.com", "Oi")
    with pytest.raises(ErroEmail):
        fila.montar("a@luft.com", "Oi", template="t", html="<p>x</p>")
    with pytest.raises(ErroEmail):
        fila.montar("a@luft.com", "Oi", template="t", contexto={"x": object()})


def test_processar_entrega_em_lote_e_marca_como_enviado(banco: BancoSQLAlchemy) -> None:
    fila, email = _fila(banco)
    fila.enfileirar_varios([fila.montar(f"p{i}@luft.com", "Oi", texto="x") for i in range(7)])

    resultado = fila.processar_tudo(limite_lote=3)

    assert resultado.enviados == 7 and resultado.falhas == 0
    assert email.lotes == [3, 3, 1]  # varias conexoes SMTP pequenas, nunca uma por e-mail
    assert fila.contar()["pendentes"] == 0 and fila.contar()["enviados"] == 7
    assert all(linha.enviado_em is not None for linha in _linhas(banco))


def test_falha_reagenda_com_espera_e_depois_fica_falhou(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco, EmailFalso(falhar_para={"x@luft.com"}))
    fila.enfileirar("x@luft.com", "Oi", texto="x")
    fila.enfileirar("ok@luft.com", "Oi", texto="x")

    primeira = fila.processar()
    assert (primeira.enviados, primeira.reagendados, primeira.falhas) == (1, 1, 0)
    ruim = next(linha for linha in _linhas(banco) if "x@luft.com" in linha.destinatarios)
    assert ruim.status == "PENDENTE" and ruim.tentativas == 1 and ruim.ultimo_erro == "smtp fora"
    assert ruim.proxima_tentativa > agora_local() + timedelta(seconds=ESPERAS_SEGUNDOS[0] - 5)

    # ainda nao e hora: nada a entregar
    assert fila.processar().reservados == 0

    for _tentativa in range(2, MAXIMO_TENTATIVAS + 1):
        with banco.escrita() as s:
            s.execute(
                update(EmailFila)
                .where(EmailFila.id_email == ruim.id_email)
                .values(proxima_tentativa=agora_local())
            )
        fila.processar()
    final = next(linha for linha in _linhas(banco) if linha.id_email == ruim.id_email)
    assert final.status == "FALHOU" and final.tentativas == MAXIMO_TENTATIVAS
    assert fila.contar()["falhas"] == 1

    assert fila.reenviar(final.id_email) is True
    reposto = next(linha for linha in _linhas(banco) if linha.id_email == final.id_email)
    assert reposto.status == "PENDENTE" and reposto.tentativas == 0


def test_endereco_invalido_falha_na_hora_sem_repetir(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco)
    fila.enfileirar("invalido@x.com", "Oi", texto="x")  # a validacao do formato e do servico, na entrega
    fila.enfileirar("ok@luft.com", "Oi", texto="x")
    resultado = fila.processar()
    assert resultado.enviados == 1 and resultado.falhas == 1
    linhas = _linhas(banco)
    assert linhas[0].status == "FALHOU" and "invalido" in (linhas[0].ultimo_erro or "")


def test_sem_email_configurado_devolve_o_lote_sem_gastar_tentativa(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco, EmailFalso(sem_configuracao=True))
    fila.enfileirar("a@luft.com", "Oi", texto="x")
    resultado = fila.processar()
    assert resultado.reservados == 1 and resultado.enviados == 0
    (linha,) = _linhas(banco)
    assert linha.status == "PENDENTE" and linha.tentativas == 0
    assert "nao esta configurado" in (linha.ultimo_erro or "")


def test_lote_travado_ha_muito_tempo_volta_para_a_fila(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco)
    fila.enfileirar("a@luft.com", "Oi", texto="x")
    with banco.escrita() as s:  # um processo reservou e morreu antes de entregar
        s.execute(
            update(EmailFila).values(
                status="ENVIANDO", tentativas=1, bloqueado_ate=agora_local() - timedelta(minutes=1)
            )
        )
    assert fila.processar().enviados == 1


def test_reserva_em_andamento_nao_e_entregue_de_novo(banco: BancoSQLAlchemy) -> None:
    fila, email = _fila(banco)
    fila.enfileirar("a@luft.com", "Oi", texto="x")
    with banco.escrita() as s:  # outro processo esta entregando agora
        s.execute(
            update(EmailFila).values(
                status="ENVIANDO", tentativas=1, bloqueado_ate=agora_local() + timedelta(minutes=5)
            )
        )
    assert fila.processar().reservados == 0 and email.lotes == []


def test_cancelar_consultar_e_limpar(banco: BancoSQLAlchemy) -> None:
    fila, _ = _fila(banco)
    a = fila.enfileirar("ana@luft.com", "Acesso liberado", texto="x", origem="ACESSO_LIBERADO")
    fila.enfileirar("bia@luft.com", "Alerta", texto="x", origem="ALERTA")
    assert fila.cancelar(a) is True and fila.cancelar(a) is False
    pend = fila.consultar(situacao="pendentes")
    assert pend["total"] == 1 and pend["itens"][0]["resumo_destinatarios"] == "bia@luft.com"
    assert fila.consultar(situacao="falhas")["total"] == 1
    assert fila.consultar(situacao="todos", termo="ana")["total"] == 1
    with pytest.raises(ValueError):
        fila.consultar(situacao="nada")

    fila.processar()
    with banco.escrita() as s:
        s.execute(update(EmailFila).values(criado_em=agora_local() - timedelta(days=100)))
    assert fila.limpar(dias_enviados=30, dias_falhas=90) == 2
    assert fila.contar()["todos"] == 0
