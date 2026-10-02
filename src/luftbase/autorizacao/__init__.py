"""API publica de autorizacao sob demanda."""

from luftbase.autorizacao.catalogo import AcaoPermissao, PermissaoLuftBase
from luftbase.autorizacao.servico import ServicoAutorizacao
from luftbase.autorizacao.web import (
    consultar_permissoes,
    exigir_alguma_permissao,
    exigir_permissao,
    tem_permissao,
)

__all__ = [
    "AcaoPermissao",
    "PermissaoLuftBase",
    "ServicoAutorizacao",
    "consultar_permissoes",
    "exigir_alguma_permissao",
    "exigir_permissao",
    "tem_permissao",
]
