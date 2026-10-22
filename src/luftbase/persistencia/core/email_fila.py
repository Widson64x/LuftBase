"""Fila de e-mails (`tb_email_fila`): quem precisa enviar so grava; um servico em segundo plano entrega."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.comum import DATA_HORA_LOCAL, TIMESTAMP_MILISSEGUNDOS

STATUS_EMAIL_FILA = ("PENDENTE", "ENVIANDO", "ENVIADO", "FALHOU", "CANCELADO")


class EmailFila(BaseLuft):
    """Um e-mail a enviar. Guarda a *intencao* (template + contexto ou html), nao a mensagem pronta.

    O servico de envio monta a mensagem na hora de entregar; assim o modo teste, o remetente e o layout
    valem como estao naquele momento e nada pesado (anexo, imagem) fica no banco.
    """

    __tablename__ = "tb_email_fila"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDENTE', 'ENVIANDO', 'ENVIADO', 'FALHOU', 'CANCELADO')",
            name="ck_core_email_fila_status",
        ),
        Index("ix_core_email_fila_status", "status", "proxima_tentativa"),
        Index("ix_core_email_fila_criado", "criado_em"),
    )

    id_email: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    id_sistema: Mapped[int | None] = mapped_column(Integer)
    origem: Mapped[str] = mapped_column(String(60), nullable=False, default="GERAL")
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDENTE")
    destinatarios: Mapped[str] = mapped_column(Text, nullable=False)  # lista JSON
    copia: Mapped[str | None] = mapped_column(Text)  # lista JSON
    assunto: Mapped[str] = mapped_column(String(300), nullable=False)
    template: Mapped[str | None] = mapped_column(String(200))
    contexto: Mapped[str | None] = mapped_column(Text)  # objeto JSON
    html: Mapped[str | None] = mapped_column(Text)
    texto: Mapped[str | None] = mapped_column(Text)
    nome_remetente: Mapped[str | None] = mapped_column(String(120))
    responder_para: Mapped[str | None] = mapped_column(String(200))
    tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximo_tentativas: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    proxima_tentativa: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS, nullable=False, server_default=DATA_HORA_LOCAL
    )
    bloqueado_ate: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    ultimo_erro: Mapped[str | None] = mapped_column(String(1000))
    criado_por: Mapped[str | None] = mapped_column(String(100))
    criado_em: Mapped[datetime] = mapped_column(
        TIMESTAMP_MILISSEGUNDOS, nullable=False, server_default=DATA_HORA_LOCAL
    )
    atualizado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)
    enviado_em: Mapped[datetime | None] = mapped_column(TIMESTAMP_MILISSEGUNDOS)


__all__ = ["STATUS_EMAIL_FILA", "EmailFila"]
