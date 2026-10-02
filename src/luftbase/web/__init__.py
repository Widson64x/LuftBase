"""Módulos web corporativos nativos do LuftBase."""

from __future__ import annotations

from typing import TYPE_CHECKING

from luftbase.web.auditoria import AuditoriaBp
from luftbase.web.autenticacao import AutenticacaoBp
from luftbase.web.busca import BuscaBp
from luftbase.web.configuracoes import AdminBp, ConfiguracoesBp
from luftbase.web.publicacoes import PublicacoesBp
from luftbase.web.seguranca import SegurancaBp

if TYPE_CHECKING:
    from flask import Flask


def registrar_rotas_plataforma(app: Flask) -> None:
    """Registra os blueprints corporativos nativos se ainda não presentes no app."""

    blueprints = (
        AutenticacaoBp,
        ConfiguracoesBp,
        AdminBp,
        AuditoriaBp,
        BuscaBp,
        SegurancaBp,
        PublicacoesBp,
    )
    for bp in blueprints:
        if bp.name not in app.blueprints:
            app.register_blueprint(bp)


__all__ = [
    "AdminBp",
    "AutenticacaoBp",
    "AuditoriaBp",
    "BuscaBp",
    "ConfiguracoesBp",
    "PublicacoesBp",
    "SegurancaBp",
    "registrar_rotas_plataforma",
]
