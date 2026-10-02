"""Tipos e expressoes compartilhados pelos modelos do core."""

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import TIMESTAMP

DATA_HORA_LOCAL = text("(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')")
TIMESTAMP_MILISSEGUNDOS = TIMESTAMP(timezone=False, precision=3)
