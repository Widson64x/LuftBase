"""Normalizacao dos ambientes reconhecidos pela plataforma."""

from __future__ import annotations

import unicodedata
from enum import StrEnum

from luftbase.nucleo.excecoes import ErroConfiguracao


class Ambiente(StrEnum):
    """Ambientes canonicos usados em configuracao e caminhos do Vault."""

    DESENVOLVIMENTO = "desenvolvimento"
    HOMOLOGACAO = "homologacao"
    PRODUCAO = "producao"


_ALIASES: dict[str, Ambiente] = {
    "dev": Ambiente.DESENVOLVIMENTO,
    "development": Ambiente.DESENVOLVIMENTO,
    "desenvolvimento": Ambiente.DESENVOLVIMENTO,
    "hml": Ambiente.HOMOLOGACAO,
    "homolog": Ambiente.HOMOLOGACAO,
    "homologacao": Ambiente.HOMOLOGACAO,
    "homologation": Ambiente.HOMOLOGACAO,
    "prd": Ambiente.PRODUCAO,
    "prod": Ambiente.PRODUCAO,
    "production": Ambiente.PRODUCAO,
    "producao": Ambiente.PRODUCAO,
}


def _remover_acentos(valor: str) -> str:
    normalizado = unicodedata.normalize("NFKD", valor)
    return "".join(caractere for caractere in normalizado if not unicodedata.combining(caractere))


def normalizar_ambiente(valor: object) -> Ambiente:
    """Converte aliases aceitos no ambiente canonico correspondente."""

    chave = _remover_acentos(str(valor or "").strip().casefold())
    if ambiente := _ALIASES.get(chave):
        return ambiente
    aceitos = ", ".join(ambiente.value for ambiente in Ambiente)
    raise ErroConfiguracao(f"Ambiente invalido: {valor!r}. Use um destes valores: {aceitos}.")
