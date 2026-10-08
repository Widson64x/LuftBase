"""Roda o avaliador de alertas em uma thread de segundo plano (opt-in por `LUFT_ALERTAS_ATIVO`).

Ligue **so em um sistema** (o Workspace): a trava em `tb_alerta_controle` ja impede dois avaliadores ao mesmo
tempo, mas um so basta, porque a trilha de auditoria (`tb_logs`) e compartilhada por todos os sistemas.
Sem a variavel, nada roda; o comando `luftbase alertas avaliar` faz o mesmo ciclo sob demanda ou agendado.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

from luftbase.observabilidade.alertas import avaliar

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
    from luftbase.integracoes.email import ServicoEmail

logger = logging.getLogger(__name__)

VARIAVEL_ATIVO = "LUFT_ALERTAS_ATIVO"
VARIAVEL_INTERVALO = "LUFT_ALERTAS_INTERVALO_SEGUNDOS"
INTERVALO_PADRAO_SEGUNDOS = 60
INTERVALO_MINIMO_SEGUNDOS = 15


def alertas_ativos() -> bool:
    return (os.environ.get(VARIAVEL_ATIVO) or "").strip().lower() in {"1", "true", "sim", "yes"}


def intervalo_configurado() -> int:
    try:
        valor = int(os.environ.get(VARIAVEL_INTERVALO) or INTERVALO_PADRAO_SEGUNDOS)
    except ValueError:
        valor = INTERVALO_PADRAO_SEGUNDOS
    return max(valor, INTERVALO_MINIMO_SEGUNDOS)


class AvaliadorEmSegundoPlano:
    """Thread daemon que chama `avaliar` a cada intervalo; nunca derruba o processo."""

    def __init__(
        self, bancos: CatalogoBancos, email: ServicoEmail, intervalo_segundos: int | None = None
    ) -> None:
        self._bancos = bancos
        self._email = email
        self._intervalo = intervalo_segundos or intervalo_configurado()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def ativo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self) -> None:
        if self.ativo:
            return
        self._parar.clear()
        self._thread = threading.Thread(
            target=self._executar, name="luftbase-alertas", daemon=True
        )
        self._thread.start()
        logger.info("Avaliador de alertas ligado (a cada %ss).", self._intervalo)

    def parar(self) -> None:
        self._parar.set()

    def _executar(self) -> None:
        # Primeiro ciclo logo depois da subida do servidor, sem disputar a inicializacao.
        if self._parar.wait(5):
            return
        ultima_falha = ""
        while not self._parar.is_set():
            try:
                resultado = avaliar(self._bancos, self._email)
                falha = "; ".join(e.splitlines()[0][:200] for e in resultado.erros)
                if falha and falha != ultima_falha:
                    # So avisa quando a falha muda: uma tabela ausente nao deve encher o log a cada ciclo.
                    logger.warning("Alertas: %s", falha)
                ultima_falha = falha
            except Exception as erro:
                texto = f"{type(erro).__name__}: {str(erro).splitlines()[0][:200]}"
                if texto != ultima_falha:
                    logger.exception("Falha inesperada no avaliador de alertas")
                ultima_falha = texto
            self._parar.wait(self._intervalo)


def iniciar_se_ativo(bancos: CatalogoBancos, email: ServicoEmail) -> AvaliadorEmSegundoPlano | None:
    """Liga o avaliador quando `LUFT_ALERTAS_ATIVO=true`; senao devolve None."""

    if not alertas_ativos():
        return None
    avaliador = AvaliadorEmSegundoPlano(bancos, email)
    avaliador.iniciar()
    return avaliador


__all__ = [
    "AvaliadorEmSegundoPlano",
    "alertas_ativos",
    "intervalo_configurado",
    "iniciar_se_ativo",
]
