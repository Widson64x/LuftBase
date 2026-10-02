"""Validacao de identificadores usados em infraestrutura."""

from __future__ import annotations

import re

from luftbase.nucleo.excecoes import ErroConfiguracao

_PADRAO_APLICACAO = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_PADRAO_ESQUEMA = re.compile(r"^[a-z][a-z0-9_]{1,62}$")
_ESQUEMAS_RESERVADOS = frozenset({"core", "information_schema", "public"})


def validar_identificador_tecnico(valor: object) -> str:
    """Valida o identificador tecnico estavel usado no caminho do Vault."""

    identificador = str(valor or "").strip()
    if not identificador:
        raise ErroConfiguracao("O identificador tecnico da aplicacao e obrigatorio.")
    if len(identificador) > 63 or not _PADRAO_APLICACAO.fullmatch(identificador):
        raise ErroConfiguracao(
            "O identificador tecnico deve usar letras minusculas, numeros e hifens, "
            "por exemplo: luft-workspace."
        )
    return identificador


def validar_esquema_aplicacao(valor: object) -> str:
    """Valida o schema particular informado pela credencial PostgreSQL."""

    esquema = str(valor or "").strip()
    if not _PADRAO_ESQUEMA.fullmatch(esquema):
        raise ErroConfiguracao(
            "O esquema PostgreSQL deve usar letras minusculas, numeros e underscore."
        )
    if esquema in _ESQUEMAS_RESERVADOS or esquema.startswith("pg_"):
        raise ErroConfiguracao(f"O esquema PostgreSQL {esquema!r} e reservado.")
    return esquema
