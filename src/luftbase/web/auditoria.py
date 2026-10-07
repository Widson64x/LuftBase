"""API analitica da auditoria incorporada ao Painel de Controle."""

from __future__ import annotations

import csv
import os
import re
from datetime import datetime, timedelta
from io import StringIO
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, abort, jsonify, request
from flask_login import login_required

from luftbase.autorizacao import PermissaoLuftBase
from luftbase.autorizacao.web import consultar_permissoes, exigir_permissao
from luftbase.observabilidade.analise import (
    FiltroAuditoria,
    PaginaAuditoria,
    ServicoAnaliseAuditoria,
)
from luftbase.observabilidade.filtros import NAVEGADORES
from luftbase.observabilidade.insights import ServicoInsights
from luftbase.observabilidade.tempo_real import ServicoTempoReal
from luftbase.plataforma import obter_luftbase
from luftbase.web.escopo import sistema_aplicacao_atual

AuditoriaBp = Blueprint(
    "Auditoria",
    __name__,
    url_prefix="/configuracoes/api/auditoria",
)

_FUSO = ZoneInfo("America/Sao_Paulo")
_SEVERIDADES = frozenset({"BAIXA", "MEDIA", "ALTA", "CRITICA"})
_RESULTADOS = frozenset({"sucesso", "redirecionamento", "cliente", "servidor", "negado"})
_METODOS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_MOTIVOS = frozenset(
    {"LOGOUT_VOLUNTARIO", "TIMEOUT_INATIVIDADE", "ROTACAO_SESSAO", "REVOGADA_ADMIN", "REVOGADA_USUARIO",
     "LIMPEZA_VISITANTE", "ATIVA", "EXPIRADA"}
)
_PADRAO_IP = re.compile(r"^[0-9A-Fa-f:.]{3,45}$")


def _servico() -> ServicoAnaliseAuditoria:
    return ServicoAnaliseAuditoria(obter_luftbase().bancos.core)


def _inteiro_opcional(nome: str) -> int | None:
    valor = request.args.get(nome, "").strip()
    if not valor:
        return None
    try:
        numero = int(valor)
    except ValueError:
        abort(400, description=f"Filtro {nome} invalido.")
    if numero < 0:
        abort(400, description=f"Filtro {nome} nao pode ser negativo.")
    return numero


def _data_opcional(nome: str) -> datetime | None:
    valor = request.args.get(nome, "").strip()
    if not valor:
        return None
    try:
        data = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except ValueError:
        abort(400, description=f"Data {nome} invalida.")
    if data.tzinfo is not None:
        data = data.astimezone(_FUSO).replace(tzinfo=None)
    return data


def _escopo_da_aplicacao() -> int | None:
    """None para o escopo global (sistema 0); nas demais, o proprio sistema."""
    id_sistema_atual = sistema_aplicacao_atual()
    return None if id_sistema_atual == 0 else id_sistema_atual


def _resolver_sistema() -> int | None:
    solicitado = request.args.get("sistema_id", "").strip()
    id_sistema_atual = sistema_aplicacao_atual()
    if solicitado in {"", "todos"}:
        # Escopo global (sistema 0) enxerga todos os sistemas; as demais aplicacoes so veem a si
        # mesmas, entao "todos" vira o proprio sistema (o painel envia "todos" por padrao).
        return None if id_sistema_atual == 0 else id_sistema_atual
    try:
        id_sistema = int(solicitado)
    except ValueError:
        abort(400, description="Filtro sistema_id invalido.")
    if id_sistema < 0:
        abort(400, description="Filtro sistema_id nao pode ser negativo.")
    if id_sistema_atual != 0 and id_sistema != id_sistema_atual:
        abort(403, description="Consulta fora do escopo da aplicacao.")
    return id_sistema


def dados_confiaveis_desde() -> datetime | None:
    """Marco opcional (`LUFT_AUDITORIA_DADOS_DESDE`, ISO 8601): o que veio antes e ignorado nas analises.

    Serve para quando a captura era incompleta (sem IP, sem navegador...) e os numeros antigos so atrapalham,
    sem apagar nada do banco. Vazio ou invalido = sem corte.
    """

    texto = (os.environ.get("LUFT_AUDITORIA_DADOS_DESDE") or "").strip()
    if not texto:
        return None
    try:
        marco = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return marco.astimezone(_FUSO).replace(tzinfo=None) if marco.tzinfo else marco


def _montar_drill() -> dict[str, object]:
    """Recortes que vem de cliques nos graficos e tabelas; tudo validado antes de virar filtro."""

    dados: dict[str, object] = {}
    rota = request.args.get("rota", "").strip()[:300]
    if rota:
        dados["rota"] = rota
    metodo = request.args.get("metodo", "").strip().upper()
    if metodo:
        if metodo not in _METODOS:
            abort(400, description="Metodo HTTP invalido.")
        dados["metodo"] = metodo
    ip = request.args.get("ip", "").strip()
    if ip:
        if not _PADRAO_IP.fullmatch(ip):
            abort(400, description="IP invalido.")
        dados["ip"] = ip
    login = request.args.get("login", "").strip()[:100]
    if login:
        dados["login"] = login
    grupo = request.args.get("grupo", "").strip()[:100]
    if grupo:
        dados["grupo_nome"] = grupo
    navegador = request.args.get("navegador", "").strip()
    if navegador:
        if navegador not in (*NAVEGADORES, "Desconhecido"):
            abort(400, description="Navegador invalido.")
        dados["navegador"] = navegador
    for nome, minimo, maximo, chave in (("hora", 0, 23, "hora"), ("dia_semana", 0, 6, "dia_semana")):
        valor = request.args.get(nome, "").strip()
        if valor:
            try:
                numero = int(valor)
            except ValueError:
                abort(400, description=f"Filtro {nome} invalido.")
            if not minimo <= numero <= maximo:
                abort(400, description=f"Filtro {nome} fora do intervalo.")
            dados[chave] = numero
    motivo = request.args.get("motivo", "").strip().upper()
    if motivo:
        if motivo not in _MOTIVOS:
            abort(400, description="Motivo invalido.")
        dados["motivo"] = motivo
    return dados


def _montar_filtro() -> FiltroAuditoria:
    agora = datetime.now(_FUSO).replace(tzinfo=None)
    fim = _data_opcional("fim") or agora
    inicio = _data_opcional("inicio") or (fim - timedelta(hours=24))
    marco = dados_confiaveis_desde()
    if marco is not None and inicio < marco:
        inicio = min(marco, fim)
    if fim < inicio:
        abort(400, description="O fim do periodo deve ser posterior ao inicio.")
    if fim - inicio > timedelta(days=90):
        abort(400, description="O periodo maximo para analise e de 90 dias.")
    if fim > agora + timedelta(minutes=5):
        abort(400, description="O fim do periodo nao pode estar no futuro.")

    resultado = request.args.get("resultado", "").strip().lower() or None
    if resultado not in _RESULTADOS and resultado is not None:
        abort(400, description="Resultado HTTP invalido.")
    severidade = request.args.get("severidade", "").strip().upper() or None
    if severidade not in _SEVERIDADES and severidade is not None:
        abort(400, description="Severidade invalida.")
    termo = request.args.get("termo", "").strip()[:100] or None
    drill = _montar_drill()

    return FiltroAuditoria(
        inicio=inicio,
        fim=fim,
        id_sistema=_resolver_sistema(),
        codigo_usuario=_inteiro_opcional("usuario_id"),
        codigo_grupo=_inteiro_opcional("grupo_id"),
        termo=termo,
        resultado_http=resultado,
        severidade=severidade,
        **drill,
    )


def _montar_pagina() -> PaginaAuditoria:
    try:
        numero = max(int(request.args.get("pagina", "1")), 1)
        tamanho = min(max(int(request.args.get("tamanho", "50")), 10), 100)
    except ValueError:
        abort(400, description="Paginacao invalida.")
    return PaginaAuditoria(numero=numero, tamanho=tamanho)


@AuditoriaBp.get("/resumo")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_resumo():  # type: ignore[no-untyped-def]
    """Entrega KPIs, serie temporal, rankings e opcoes de filtro."""

    filtro = _montar_filtro()
    servico = _servico()
    decisoes = consultar_permissoes(
        (
            PermissaoLuftBase.AUDITORIA_EXPORTAR,
            PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,
        )
    )
    return jsonify(
        {
            "status": "success",
            "data": {
                **servico.obter_resumo(filtro),
                "opcoes": servico.obter_opcoes(
                    filtro,
                    id_sistema_escopo=_escopo_da_aplicacao(),
                ),
                "capacidades": {
                    "exportar": bool(decisoes.get(PermissaoLuftBase.AUDITORIA_EXPORTAR)),
                    "ver_sensiveis": bool(
                        decisoes.get(PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR)
                    ),
                },
            },
        }
    )


@AuditoriaBp.get("/insights")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_insights():  # type: ignore[no-untyped-def]
    """Comparativo, mapa de calor, desempenho, seguranca e sessoes do recorte filtrado."""

    dados = ServicoInsights(obter_luftbase().bancos.core).obter(
        _montar_filtro(), desde=dados_confiaveis_desde()
    )
    return jsonify({"status": "success", "data": dados})


@AuditoriaBp.get("/sessoes")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_sessoes():  # type: ignore[no-untyped-def]
    """Sessoes do recorte (quem entrou, de onde, com que navegador e como terminou)."""

    dados = ServicoInsights(obter_luftbase().bancos.core).listar_sessoes(_montar_filtro(), _montar_pagina())
    return jsonify({"status": "success", "data": dados})


@AuditoriaBp.get("/tempo-real")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_tempo_real():  # type: ignore[no-untyped-def]
    """Retrato do momento: quem esta online, o que faz, navegadores e atividade recente."""

    dados = ServicoTempoReal(obter_luftbase().bancos.core).obter(id_sistema=_resolver_sistema())
    resposta = jsonify({"status": "success", "data": dados})
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


@AuditoriaBp.get("/acessos")
@AuditoriaBp.get("/logs")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_acessos():  # type: ignore[no-untyped-def]
    """Lista os acessos/logs HTTP do recorte atual."""

    return jsonify(
        {
            "status": "success",
            "data": _servico().listar_acessos(_montar_filtro(), _montar_pagina()),
        }
    )


@AuditoriaBp.get("/detalhes")
@AuditoriaBp.get("/eventos")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_detalhes():  # type: ignore[no-untyped-def]
    """Lista acoes, erros e eventos persistidos."""

    return jsonify(
        {
            "status": "success",
            "data": _servico().listar_detalhes(_montar_filtro(), _montar_pagina()),
        }
    )


@AuditoriaBp.get("/alteracoes")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_alteracoes():  # type: ignore[no-untyped-def]
    """Lista os retratos antes/depois ligados aos detalhes de alteracao."""

    return jsonify(
        {
            "status": "success",
            "data": _servico().listar_alteracoes(_montar_filtro(), _montar_pagina()),
        }
    )


@AuditoriaBp.get("/temporarios")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR)
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_temporarios():  # type: ignore[no-untyped-def]
    """Mostra a raiz temporaria do processo atual."""

    servico = obter_luftbase().auditoria
    limite = min(max(request.args.get("limite", 100, type=int) or 100, 1), 500)
    logs = [
        item.como_dict()
        for item in servico.obter_logs_temporarios(
            limite=limite,
            nivel=request.args.get("nivel"),
            termo=request.args.get("termo", "")[:100] or None,
            codigo_usuario=_inteiro_opcional("usuario_id"),
            codigo_grupo=_inteiro_opcional("grupo_id"),
        )
    ]
    return jsonify(
        {
            "status": "success",
            "data": {
                "total": len(logs),
                "itens": logs,
                "arquivo_raiz": servico.nome_arquivo_temporario(),
                "escopo": "processo_local",
            },
        }
    )


@AuditoriaBp.get("/fisicos")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR)
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_fisicos():  # type: ignore[no-untyped-def]
    """Le arquivos fisicos conhecidos sem aceitar caminhos arbitrarios."""

    servico = obter_luftbase().auditoria
    limite = min(max(request.args.get("limite", 200, type=int) or 200, 1), 500)
    logs = servico.obter_logs_fisicos(
        arquivo=request.args.get("arquivo", "").strip()[:255] or None,
        limite=limite,
        nivel=request.args.get("nivel", "").strip()[:20] or None,
        termo=request.args.get("termo", "").strip()[:100] or None,
    )
    return jsonify(
        {
            "status": "success",
            "data": {
                "total": len(logs),
                "itens": logs,
                "arquivos": servico.listar_arquivos_fisicos(),
                "escopo": "aplicacao_local",
            },
        }
    )


@AuditoriaBp.get("/detalhes/<tipo>/<int:identificador>")
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
def api_detalhe(tipo: str, identificador: int):  # type: ignore[no-untyped-def]
    """Mostra contexto completo, mantendo payloads protegidos por permissao propria."""

    if tipo not in {"acesso", "detalhe", "alteracao", "log", "evento"}:
        abort(404)
    id_sistema_atual = sistema_aplicacao_atual()
    decisoes = consultar_permissoes((PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,))
    detalhe = _servico().obter_detalhe(
        tipo,
        identificador,
        incluir_sensiveis=bool(
            decisoes.get(PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR)
        ),
        id_sistema=None if id_sistema_atual == 0 else id_sistema_atual,
    )
    if detalhe is None:
        abort(404)
    return jsonify({"status": "success", "data": detalhe})


@AuditoriaBp.get("/exportar")
@login_required
@exigir_permissao(PermissaoLuftBase.AUDITORIA_EXPORTAR)
def api_exportar():  # type: ignore[no-untyped-def]
    """Exporta ate cinco mil linhas sem incluir payloads sensiveis."""

    tipo = request.args.get("tipo", "acesso").strip().lower()
    if tipo not in {"acesso", "detalhe", "alteracao", "log", "evento"}:
        abort(400, description="Tipo de exportacao invalido.")
    pagina = PaginaAuditoria(numero=1, tamanho=5_000)
    servico = _servico()
    filtro = _montar_filtro()
    if tipo in {"acesso", "log"}:
        dados = servico.listar_acessos(filtro, pagina)
    elif tipo in {"detalhe", "evento"}:
        dados = servico.listar_detalhes(filtro, pagina)
    else:
        dados = servico.listar_alteracoes(filtro, pagina)
    itens = dados["itens"]
    campos = list(itens[0]) if itens else ["id", "data_hora"]
    arquivo = StringIO(newline="")
    escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
    escritor.writeheader()
    for item in itens:
        escritor.writerow({chave: _valor_csv(valor) for chave, valor in item.items()})
    nome = f"auditoria-{tipo}-{datetime.now(_FUSO):%Y%m%d-%H%M%S}.csv"
    return Response(
        "\ufeff" + arquivo.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _valor_csv(valor: object) -> object:
    """Impede interpretacao de formulas por planilhas."""

    if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")):
        return "'" + valor
    return valor


__all__ = ["AuditoriaBp"]
