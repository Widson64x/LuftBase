"""Endpoint da busca global: consulta os provedores registrados pela aplicacao."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, wait

from flask import Blueprint, copy_current_request_context, jsonify, request
from flask_login import login_required

from luftbase.autorizacao.web import tem_permissao
from luftbase.interface.busca import (
    _PADRAO_ICONE,
    ProvedorBusca,
    ResultadoBusca,
    url_aceita,
)
from luftbase.plataforma import obter_luftbase

BuscaBp = Blueprint("luftbase_busca", __name__, url_prefix="/_luftbase")

TAMANHO_MAXIMO_TERMO = 80
LIMITE_DE_TEMPO_SEGUNDOS = 4.0
_logger = logging.getLogger("luftbase.busca")


def _icone_valido(icone: str | None) -> str | None:
    return icone if icone and _PADRAO_ICONE.fullmatch(icone) else None


def _executar(provedor: ProvedorBusca, termo: str) -> dict[str, object]:
    itens: list[dict[str, str | None]] = []
    for resultado in provedor.buscar(termo, provedor.limite):
        if not isinstance(resultado, ResultadoBusca):
            continue
        if not url_aceita(resultado.url, permitir_externas=provedor.urls_externas):
            continue
        itens.append(
            {
                "titulo": str(resultado.titulo)[:160],
                "subtitulo": (str(resultado.subtitulo)[:200] if resultado.subtitulo else None),
                "url": resultado.url,
                "icone": _icone_valido(resultado.icone) or provedor.icone,
            }
        )
        if len(itens) >= provedor.limite:
            break
    return {"id": provedor.id, "titulo": provedor.titulo, "icone": provedor.icone, "itens": itens}


@BuscaBp.get("/busca")
@login_required
def pesquisar():  # type: ignore[no-untyped-def]
    """Resultados agrupados por provedor, so dos que o usuario pode usar."""

    termo = " ".join((request.args.get("q") or "").split())[:TAMANHO_MAXIMO_TERMO]
    permitidos = [
        p
        for p in obter_luftbase().buscas
        if len(termo) >= p.minimo_caracteres and (p.permissao is None or tem_permissao(p.permissao))
    ]
    if not permitidos:
        return jsonify({"termo": termo, "grupos": []})

    # Provedores em paralelo e com prazo: uma consulta lenta (ex.: ERP) nao trava as demais.
    grupos: dict[str, dict[str, object]] = {}
    pool = ThreadPoolExecutor(max_workers=min(len(permitidos), 4))
    try:
        futuros = {
            pool.submit(copy_current_request_context(_executar), p, termo): p for p in permitidos
        }
        feitos, pendentes = wait(futuros, timeout=LIMITE_DE_TEMPO_SEGUNDOS)
        for futuro in feitos:
            provedor = futuros[futuro]
            try:
                grupo = futuro.result()
            except Exception:
                _logger.warning("Busca '%s' falhou.", provedor.id, exc_info=True)
                continue
            if grupo["itens"]:
                grupos[provedor.id] = grupo
        for futuro in pendentes:
            _logger.warning("Busca '%s' passou do prazo.", futuros[futuro].id)
            futuro.cancel()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    ordem = [p.id for p in permitidos]
    return jsonify({"termo": termo, "grupos": [grupos[i] for i in ordem if i in grupos]})
