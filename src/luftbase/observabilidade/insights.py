"""Visões analíticas da auditoria: comparativo, mapa de calor, desempenho, segurança e sessões.

As consultas só leem o core. A montagem dos números (`montar_*`, `consolidar_sessoes`,
`gerar_destaques`) é feita em funções puras para poder ser testada sem banco.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from luftbase.identidade.agente_usuario import interpretar_agente
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.observabilidade.analise import FiltroAuditoria, ServicoAnaliseAuditoria
from luftbase.persistencia.core import Log, LogEvento, Sessao, Sistema

DIAS_SEMANA = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
_NUMERO_NA_ROTA = re.compile(r"/\d+(?=/|$)")
_UUID_NA_ROTA = re.compile(r"/[0-9a-fA-F]{8}-[0-9a-fA-F-]{27}(?=/|$)")
LIMITE_SESSOES = 3000


def normalizar_rota(rota: str) -> str:
    """'/clientes/42/testar' e '/clientes/7/testar' viram a mesma rota: '/clientes/:id/testar'."""

    caminho = (rota or "").split("?", 1)[0]
    return _NUMERO_NA_ROTA.sub("/:id", _UUID_NA_ROTA.sub("/:id", caminho)) or "/"


def _como_data(valor: Any) -> datetime | None:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, str) and valor:
        try:
            return datetime.fromisoformat(valor)
        except ValueError:
            return None
    return None


def _iso(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor else None


def _variacao(atual: float, anterior: float) -> float | None:
    """Variação percentual; None quando não há base de comparação."""

    if not anterior:
        return None if not atual else 100.0
    return round((atual - anterior) * 100 / anterior, 1)


# ----------------------------------------------------------------------------- funções puras


def montar_mapa_calor(horas: Sequence[tuple[Any, int]]) -> dict[str, Any]:
    """Matriz dia da semana x hora (7 x 24) a partir de totais por hora cheia."""

    matriz = [[0] * 24 for _ in range(7)]
    for instante, total in horas:
        quando = _como_data(instante)
        if quando is not None:
            matriz[quando.weekday()][quando.hour] += int(total or 0)
    maximo = max((max(linha) for linha in matriz), default=0)
    por_hora = [sum(matriz[d][h] for d in range(7)) for h in range(24)]
    por_dia = [sum(linha) for linha in matriz]
    return {
        "dias": list(DIAS_SEMANA),
        "matriz": matriz,
        "maximo": maximo,
        "por_hora": por_hora,
        "por_dia": por_dia,
        "hora_pico": por_hora.index(max(por_hora)) if any(por_hora) else None,
        "dia_pico": DIAS_SEMANA[por_dia.index(max(por_dia))] if any(por_dia) else None,
    }


def agrupar_rotas(linhas: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Junta rotas que só diferem pelo identificador e recalcula média e máximo."""

    grupos: dict[tuple[str, str], dict[str, Any]] = {}
    for linha in linhas:
        chave = (linha["metodo"], normalizar_rota(linha["rota"]))
        g = grupos.setdefault(chave, {"total": 0, "soma_ms": 0.0, "max_ms": 0, "erros_5xx": 0, "erros_4xx": 0})
        g["total"] += linha["total"]
        g["soma_ms"] += float(linha["media_ms"] or 0) * linha["total"]
        g["max_ms"] = max(g["max_ms"], int(linha["max_ms"] or 0))
        g["erros_5xx"] += linha.get("erros_5xx", 0)
        g["erros_4xx"] += linha.get("erros_4xx", 0)
    return [
        {
            "metodo": metodo,
            "rota": rota,
            "total": g["total"],
            "media_ms": round(g["soma_ms"] / g["total"]) if g["total"] else 0,
            "max_ms": g["max_ms"],
            "erros_5xx": g["erros_5xx"],
            "erros_4xx": g["erros_4xx"],
        }
        for (metodo, rota), g in grupos.items()
    ]


def consolidar_sessoes(sessoes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Logins do período: quem, de onde, com o quê e por quanto tempo."""

    navegadores: Counter[str] = Counter()
    sistemas_op: Counter[str] = Counter()
    dispositivos: Counter[str] = Counter()
    motivos: Counter[str] = Counter()
    ips: dict[str, set[Any]] = defaultdict(set)
    ips_total: Counter[str] = Counter()
    usuarios: set[Any] = set()
    duracoes: list[int] = []
    for s in sessoes:
        agente = interpretar_agente(s.get("user_agent"))
        nome = agente["navegador"].rsplit(" ", 1)[0] if agente["navegador"][-1:].isdigit() else agente["navegador"]
        navegadores[nome or "Desconhecido"] += 1
        sistemas_op[agente["sistema"] or "Desconhecido"] += 1
        dispositivos[agente["dispositivo"]] += 1
        motivos["Em andamento" if s.get("status") == "ATIVA" else (s.get("motivo") or "Encerrada")] += 1
        if s.get("codigo_usuario") is not None:
            usuarios.add(s["codigo_usuario"])
        if s.get("ip"):
            ips[s["ip"]].add(s.get("codigo_usuario"))
            ips_total[s["ip"]] += 1
        fim = s.get("encerrada_em") or s.get("ultima_atividade")
        if fim and s.get("criada_em") and s.get("status") != "ATIVA":
            duracoes.append(max(int((fim - s["criada_em"]).total_seconds()), 0))

    total = len(sessoes)

    def ranking(contador: Counter[str], limite: int = 6) -> list[dict[str, Any]]:
        return [
            {"nome": n, "total": q, "percentual": round(q * 100 / total, 1) if total else 0.0}
            for n, q in contador.most_common(limite)
        ]

    return {
        "total": total,
        "usuarios_unicos": len(usuarios),
        "ips_unicos": len(ips),
        "duracao_media_segundos": round(sum(duracoes) / len(duracoes)) if duracoes else None,
        "navegadores": ranking(navegadores),
        "sistemas_operacionais": ranking(sistemas_op),
        "dispositivos": ranking(dispositivos),
        "motivos": ranking(motivos),
        "ips": [
            {"ip": ip, "sessoes": q, "usuarios": len(ips[ip] - {None})} for ip, q in ips_total.most_common(6)
        ],
    }


def gerar_destaques(
    *,
    comparativo: Mapping[str, Any],
    mapa: Mapping[str, Any],
    rotas_lentas: Sequence[Mapping[str, Any]],
    rotas_erro: Sequence[Mapping[str, Any]],
    negados: int,
    sessoes: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Frases curtas que dizem o que merece atenção, da mais importante para a menos."""

    achados: list[dict[str, str]] = []
    atual = comparativo["atual"]

    if atual["erros_servidor"]:
        var = comparativo["variacao"]["erros_servidor"]
        tendencia = "" if var is None else (f", {abs(var):.0f}% a mais que antes" if var > 0 else f", {abs(var):.0f}% a menos que antes")
        achados.append(
            {
                "tom": "red" if (var or 0) > 0 else "amber",
                "icone": "warning-octagon",
                "titulo": f"{atual['erros_servidor']} erro(s) no servidor",
                "texto": "Houve falhas 5xx no período" + tendencia
                + (f". A rota mais afetada é {rotas_erro[0]['rota']}." if rotas_erro and rotas_erro[0]["erros_5xx"] else "."),
            }
        )
    if negados:
        achados.append(
            {"tom": "amber", "icone": "shield-warning", "titulo": f"{negados} acesso(s) negado(s)",
             "texto": "Pessoas tentaram abrir algo sem permissão. Veja os detalhes na aba Segurança."}
        )
    if rotas_lentas and rotas_lentas[0]["media_ms"] >= 800:
        r = rotas_lentas[0]
        achados.append(
            {"tom": "amber", "icone": "hourglass-medium", "titulo": "Rota lenta",
             "texto": f"{r['metodo']} {r['rota']} leva em média {r['media_ms']} ms ({r['total']} chamadas)."}
        )
    if mapa["hora_pico"] is not None:
        achados.append(
            {"tom": "blue", "icone": "chart-line-up", "titulo": f"Pico às {mapa['hora_pico']:02d}h",
             "texto": f"O dia mais movimentado foi {mapa['dia_pico']}; o horário de maior uso, {mapa['hora_pico']:02d}h."}
        )
    var_req = comparativo["variacao"]["requisicoes"]
    if var_req is not None and abs(var_req) >= 20:
        achados.append(
            {"tom": "violet", "icone": "trend-up" if var_req > 0 else "trend-down",
             "titulo": f"Uso {'subiu' if var_req > 0 else 'caiu'} {abs(var_req):.0f}%",
             "texto": "Comparado com o período anterior de mesma duração."}
        )
    if sessoes["navegadores"]:
        n = sessoes["navegadores"][0]
        achados.append(
            {"tom": "green", "icone": "browsers", "titulo": f"{n['nome']} lidera",
             "texto": f"{n['percentual']:.0f}% dos acessos vêm de {n['nome']}"
             + (f"; {sessoes['sistemas_operacionais'][0]['nome']} é o sistema mais usado." if sessoes["sistemas_operacionais"] else ".")}
        )
    if not achados:
        achados.append({"tom": "green", "icone": "check-circle", "titulo": "Tudo tranquilo",
                        "texto": "Nada fora do comum no período selecionado."})
    return achados


# ----------------------------------------------------------------------------- consultas


def _hora_cheia(sessao: Session, coluna: Any) -> Any:
    if sessao.get_bind().dialect.name == "sqlite":  # os testes rodam em SQLite
        return func.strftime("%Y-%m-%d %H:00:00", coluna)
    return func.date_trunc("hour", coluna)


class ServicoInsights:
    """Entrega, de uma vez, as visões analíticas do recorte filtrado (somente leitura)."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def obter(self, filtro: FiltroAuditoria) -> dict[str, Any]:
        cond = ServicoAnaliseAuditoria._condicoes_acesso(filtro)
        duracao = filtro.fim - filtro.inicio
        anterior = replace(filtro, inicio=filtro.inicio - duracao, fim=filtro.inicio)
        cond_anterior = ServicoAnaliseAuditoria._condicoes_acesso(anterior)

        with self._banco.leitura() as db:
            atual = self._indicadores(db, cond)
            antes = self._indicadores(db, cond_anterior)
            # O rotulo evita o erro do PostgreSQL "deve aparecer no GROUP BY" (date_trunc recebe o literal como parametro).
            hora = _hora_cheia(db, Log.data_hora).label("hora")
            horas = db.execute(select(hora, func.count(Log.id_log)).where(*cond).group_by(hora)).all()
            status = db.execute(
                select(
                    func.count(Log.id_log).filter(Log.status_http < 300),
                    func.count(Log.id_log).filter(Log.status_http >= 300, Log.status_http < 400),
                    func.count(Log.id_log).filter(Log.status_http >= 400, Log.status_http < 500),
                    func.count(Log.id_log).filter(Log.status_http >= 500),
                ).where(*cond)
            ).one()
            rotas = db.execute(
                select(
                    Log.metodo_http,
                    Log.rota_acessada,
                    func.count(Log.id_log),
                    func.avg(Log.duracao_ms),
                    func.max(Log.duracao_ms),
                    func.count(Log.id_log).filter(Log.status_http >= 500),
                    func.count(Log.id_log).filter(Log.status_http >= 400, Log.status_http < 500),
                )
                .where(*cond)
                .group_by(Log.metodo_http, Log.rota_acessada)
                .order_by(desc(func.count(Log.id_log)))
                .limit(600)
            ).all()
            usuarios = db.execute(
                select(
                    Log.login_usuario,
                    func.count(Log.id_log),
                    func.max(Log.data_hora),
                    func.count(func.distinct(Log.rota_acessada)),
                    func.count(func.distinct(Log.id_sistema)),
                    func.count(Log.id_log).filter(Log.status_http >= 400),
                )
                .where(*cond, Log.login_usuario.is_not(None))
                .group_by(Log.login_usuario)
                .order_by(desc(func.count(Log.id_log)))
                .limit(10)
            ).all()
            negados = db.execute(
                select(Log.data_hora, Log.login_usuario, Log.rota_acessada, Log.permissao_exigida, Log.ip_origem, Sistema.nome_sistema)
                .outerjoin(Sistema, Sistema.id_sistema == Log.id_sistema)
                .where(*cond, Log.acesso_permitido.is_(False))
                .order_by(desc(Log.data_hora))
                .limit(12)
            ).all()
            total_negados = db.scalar(select(func.count(Log.id_log)).where(*cond, Log.acesso_permitido.is_(False))) or 0
            criticos = db.execute(
                select(LogEvento.data_hora, LogEvento.login_usuario, LogEvento.acao, LogEvento.recurso, LogEvento.descricao, LogEvento.severidade)
                .where(*ServicoAnaliseAuditoria._condicoes_detalhe(filtro), LogEvento.severidade.in_(("ALTA", "CRITICA")))
                .order_by(desc(LogEvento.data_hora))
                .limit(12)
            ).all()
            sessoes = self._sessoes(db, filtro, cond)

        mapa = montar_mapa_calor([(h, t) for h, t in horas])
        agrupadas = agrupar_rotas(
            [
                {"metodo": m, "rota": r, "total": int(t), "media_ms": float(a or 0), "max_ms": int(mx or 0),
                 "erros_5xx": int(e5), "erros_4xx": int(e4)}
                for m, r, t, a, mx, e5, e4 in rotas
            ]
        )
        lentas = sorted((r for r in agrupadas if r["total"] >= 3), key=lambda r: r["media_ms"], reverse=True)[:8]
        com_erro = sorted(
            (r for r in agrupadas if r["erros_5xx"] or r["erros_4xx"]),
            key=lambda r: (r["erros_5xx"], r["erros_4xx"]),
            reverse=True,
        )[:8]
        comparativo = {
            "atual": atual,
            "anterior": antes,
            "variacao": {chave: _variacao(atual[chave], antes[chave]) for chave in atual},
        }
        resumo_sessoes = consolidar_sessoes(sessoes)
        return {
            "comparativo": comparativo,
            "mapa_calor": mapa,
            "status": {"sucesso": int(status[0]), "redirecionamento": int(status[1]), "erro_cliente": int(status[2]), "erro_servidor": int(status[3])},
            "rotas_lentas": lentas,
            "rotas_com_erro": com_erro,
            "usuarios_ativos": [
                {"login": u[0], "requisicoes": int(u[1]), "ultimo_acesso": _iso(_como_data(u[2])), "rotas": int(u[3]), "sistemas": int(u[4]), "falhas": int(u[5])}
                for u in usuarios
            ],
            "negados": {
                "total": int(total_negados),
                "itens": [
                    {"data_hora": _iso(_como_data(n[0])), "login": n[1] or "anônimo", "rota": n[2], "permissao": n[3], "ip": n[4], "sistema": n[5]}
                    for n in negados
                ],
            },
            "criticos": [
                {"data_hora": _iso(_como_data(c[0])), "login": c[1] or "sistema", "acao": c[2], "recurso": c[3], "descricao": (c[4] or "")[:200], "severidade": c[5]}
                for c in criticos
            ],
            "sessoes": resumo_sessoes,
            "destaques": gerar_destaques(
                comparativo=comparativo, mapa=mapa, rotas_lentas=lentas, rotas_erro=com_erro,
                negados=int(total_negados), sessoes=resumo_sessoes,
            ),
        }

    @staticmethod
    def _indicadores(db: Session, cond: list[Any]) -> dict[str, float]:
        linha = db.execute(
            select(
                func.count(Log.id_log),
                func.count(func.distinct(Log.codigo_usuario)).filter(Log.codigo_usuario.is_not(None)),
                func.count(Log.id_log).filter(Log.status_http >= 500),
                func.coalesce(func.avg(Log.duracao_ms), 0),
            ).where(*cond)
        ).one()
        return {
            "requisicoes": int(linha[0] or 0),
            "usuarios": int(linha[1] or 0),
            "erros_servidor": int(linha[2] or 0),
            "duracao_media_ms": round(float(linha[3] or 0)),
        }

    @staticmethod
    def _sessoes(db: Session, filtro: FiltroAuditoria, cond_acesso: list[Any]) -> list[dict[str, Any]]:
        condicoes = [Sessao.criada_em >= filtro.inicio, Sessao.criada_em <= filtro.fim]
        if filtro.codigo_usuario is not None:
            condicoes.append(Sessao.codigo_usuario == filtro.codigo_usuario)
        if filtro.id_sistema is not None:
            # A sessao e compartilhada entre os sistemas: vale a pessoa que usou este sistema no periodo.
            condicoes.append(
                Sessao.codigo_usuario.in_(select(Log.codigo_usuario).where(*cond_acesso, Log.codigo_usuario.is_not(None)))
            )
        linhas = db.execute(
            select(Sessao).where(*condicoes).order_by(desc(Sessao.criada_em)).limit(LIMITE_SESSOES)
        ).scalars().all()
        return [
            {
                "codigo_usuario": s.codigo_usuario,
                "ip": s.ip_origem,
                "user_agent": s.user_agent,
                "status": s.status,
                "motivo": s.motivo_encerramento,
                "criada_em": s.criada_em,
                "encerrada_em": s.encerrada_em,
                "ultima_atividade": s.ultima_atividade,
            }
            for s in linhas
        ]


__all__ = [
    "ServicoInsights",
    "agrupar_rotas",
    "consolidar_sessoes",
    "gerar_destaques",
    "montar_mapa_calor",
    "normalizar_rota",
]
