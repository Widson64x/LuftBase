"""Preferencias individuais e revisoes monotonicamente crescentes de cache."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, String, text
from sqlalchemy.orm import Mapped, mapped_column

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS


class ModoTema(StrEnum):
    """Preferencia de luminosidade independente da familia visual."""

    CLARO = "CLARO"
    ESCURO = "ESCURO"
    SISTEMA = "SISTEMA"


class RevisaoCache(BaseLuft):
    """Contador persistente usado para invalidacao barata de caches distribuidos."""

    __tablename__ = "tb_revisaocache"
    __table_args__ = (
        CheckConstraint(
            "revisao >= 0",
            name="ck_core_revisaocache_nao_negativa",
        ),
    )

    namespace: Mapped[str] = mapped_column(String(100), primary_key=True)
    revisao: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    data_atualizacao: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS,
        nullable=False,
        server_default=DATA_HORA_LOCAL,
        server_onupdate=DATA_HORA_LOCAL,
    )
