"""Thread de segundo plano que entrega a fila de e-mails (ligada por padrao nos servidores).

Desligue com `LUFT_EMAIL_FILA_ATIVO=false` num servidor que nao deva enviar. Varios servidores podem ficar
ligados: a reserva com `SKIP LOCKED` impede o mesmo e-mail de sair duas vezes. Em comandos de CLI nada sobe;
`luftbase email processar` faz o mesmo ciclo sob demanda ou agendado.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

from luftbase.integracoes.email.fila import FilaEmail

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
    from luftbase.integracoes.email import ServicoEmail

logger = logging.getLogger(__name__)

VARIAVEL_ATIVO = "LUFT_EMAIL_FILA_ATIVO"
VARIAVEL_INTERVALO = "LUFT_EMAIL_FILA_INTERVALO_SEGUNDOS"
VARIAVEL_RETENCAO = "LUFT_EMAIL_FILA_RETENCAO_DIAS"
INTERVALO_PADRAO_SEGUNDOS = 10
INTERVALO_MINIMO_SEGUNDOS = 2
RETENCAO_PADRAO_DIAS = 30
_FALSOS = {"0", "false", "nao", "no"}


def fila_ativa() -> bool:
    valor = (os.environ.get(VARIAVEL_ATIVO) or "true").strip().lower()
    return valor not in _FALSOS


def _inteiro(nome: str, padrao: int, minimo: int) -> int:
    try:
        valor = int(os.environ.get(nome) or padrao)
    except ValueError:
        valor = padrao
    return max(valor, minimo)


class EntregadorEmSegundoPlano:
    """Thread daemon: entrega a fila a cada intervalo e apaga os antigos 1x por hora. Nunca derruba o processo."""

    def __init__(self, fila: FilaEmail, intervalo_segundos: int | None = None) -> None:
        self._fila = fila
        self._intervalo = intervalo_segundos or _inteiro(
            VARIAVEL_INTERVALO, INTERVALO_PADRAO_SEGUNDOS, INTERVALO_MINIMO_SEGUNDOS
        )
        self._retencao = _inteiro(VARIAVEL_RETENCAO, RETENCAO_PADRAO_DIAS, 1)
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None
        self._proxima_limpeza = 0.0

    @property
    def ativo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self) -> None:
        if self.ativo:
            return
        self._parar.clear()
        self._thread = threading.Thread(
            target=self._executar, name="luftbase-fila-email", daemon=True
        )
        self._thread.start()
        logger.info("Fila de e-mail ligada (verifica a cada %ss).", self._intervalo)

    def parar(self) -> None:
        self._parar.set()

    def _executar(self) -> None:
        if self._parar.wait(7):  # nao disputa a inicializacao do servidor
            return
        ultima_falha = ""
        while not self._parar.is_set():
            try:
                self._fila.processar_tudo()
                if time.monotonic() >= self._proxima_limpeza:
                    self._proxima_limpeza = time.monotonic() + 3600
                    self._fila.limpar(dias_enviados=self._retencao)
                ultima_falha = ""
            except Exception as erro:
                texto = f"{type(erro).__name__}: {str(erro).splitlines()[0][:200]}"
                if texto != ultima_falha:  # tabela ausente nao deve encher o log a cada ciclo
                    logger.warning("Fila de e-mail: %s", texto)
                ultima_falha = texto
            self._parar.wait(self._intervalo)


def iniciar_se_ativo(
    bancos: CatalogoBancos, email: ServicoEmail
) -> EntregadorEmSegundoPlano | None:
    if not fila_ativa():
        return None
    entregador = EntregadorEmSegundoPlano(FilaEmail(bancos.core, email))
    entregador.iniciar()
    return entregador


__all__ = ["EntregadorEmSegundoPlano", "fila_ativa", "iniciar_se_ativo"]
