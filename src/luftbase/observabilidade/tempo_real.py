"""Painel "ao vivo" da auditoria: quem está online, o que está fazendo e com que navegador.

A consulta (`ServicoTempoReal`) só lê: sessões ativas do core e os acessos HTTP dos últimos minutos.
A consolidação (`consolidar_tempo_real`) é uma função pura, para poder ser testada sem banco.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import desc, or_, select

from luftbase.identidade.agente_usuario import interpretar_agente
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core import Log, Sessao, Sistema, Usuario

JANELA_ONLINE = timedelta(minutes=5)
JANELA_ATIVIDADE = timedelta(minutes=15)
LIMITE_SESSOES = 200
LIMITE_ACESSOS = 400
LIMITE_FEED = 30

# Chamadas automáticas da interface (relógio, sino, presença) não dizem o que a pessoa está fazendo.
_RUIDO = ("/static", "/notificacoes", "/presenca", "/sinaliza", "/_luftbase/perfil/sessoes", "/favicon")


def _ruido(rota: str) -> bool:
    texto = (rota or "").lower()
    return any(trecho in texto for trecho in _RUIDO)


def _nome_sistema(nomes: Mapping[int, str], id_sistema: int | None) -> str:
    """O sistema 0 (Workspace) e valido: nao da para testar o id por "verdadeiro ou falso"."""

    return nomes.get(id_sistema, "—") if id_sistema is not None else "—"


def _segundos(delta: timedelta) -> int:
    return max(int(delta.total_seconds()), 0)


def _nome_navegador(descricao: str) -> str:
    """'Chrome 126' -> 'Chrome' (agrupa versões diferentes do mesmo navegador)."""

    partes = descricao.rsplit(" ", 1)
    return partes[0] if len(partes) == 2 and partes[1].isdigit() else (descricao or "Desconhecido")


def _estado(inativo_s: int) -> str:
    if inativo_s <= 90:
        return "ativo"  # mexendo agora
    if inativo_s <= JANELA_ONLINE.total_seconds():
        return "recente"
    return "ocioso"


def _ranking(contador: Counter[str], total: int, limite: int = 6) -> list[dict[str, Any]]:
    return [
        {"nome": nome, "total": qtd, "percentual": round(qtd * 100 / total, 1) if total else 0.0}
        for nome, qtd in contador.most_common(limite)
    ]


def consolidar_tempo_real(
    sessoes: Sequence[Mapping[str, Any]],
    acessos: Sequence[Mapping[str, Any]],
    *,
    agora: datetime,
    nomes_sistemas: Mapping[int, str] | None = None,
) -> dict[str, Any]:
    """Transforma linhas cruas em indicadores, lista de online (uma linha por pessoa), rankings e feed."""

    nomes_sistemas = nomes_sistemas or {}
    # Sessao sem usuario e de visitante (tela de login, verificacoes de saude): nao e ninguem conectado.
    sessoes = [s for s in sessoes if s.get("codigo_usuario") is not None]
    uteis = [a for a in acessos if not _ruido(str(a.get("rota") or ""))]

    ultimo_por_usuario: dict[int, Mapping[str, Any]] = {}
    for acesso in sorted(uteis, key=lambda a: a["data_hora"], reverse=True):
        codigo = acesso.get("codigo_usuario")
        if codigo is not None and codigo not in ultimo_por_usuario:
            ultimo_por_usuario[codigo] = acesso

    por_pessoa: dict[int, list[Mapping[str, Any]]] = {}
    for sessao in sorted(sessoes, key=lambda s: s["ultima_atividade"], reverse=True):
        por_pessoa.setdefault(sessao["codigo_usuario"], []).append(sessao)

    online: list[dict[str, Any]] = []
    navegadores: Counter[str] = Counter()
    sistemas_op: Counter[str] = Counter()
    dispositivos: Counter[str] = Counter()
    janela = JANELA_ONLINE.total_seconds()
    for codigo, lista in por_pessoa.items():
        for outra in lista:  # os rankings contam cada aparelho/navegador em atividade
            if _segundos(agora - outra["ultima_atividade"]) <= janela:
                ag = interpretar_agente(outra.get("user_agent"))
                navegadores[_nome_navegador(ag["navegador"])] += 1
                sistemas_op[ag["sistema"] or "Desconhecido"] += 1
                dispositivos[ag["dispositivo"]] += 1

        principal = lista[0]  # a sessao mais recente representa a pessoa
        agente = interpretar_agente(principal.get("user_agent"))
        inativo = _segundos(agora - principal["ultima_atividade"])
        ultimo = ultimo_por_usuario.get(codigo)
        outros = {interpretar_agente(o.get("user_agent"))["descricao"] for o in lista[1:]} - {agente["descricao"]}
        online.append(
            {
                "codigo_usuario": codigo,
                "login": principal.get("login") or "—",
                "nome": principal.get("nome") or principal.get("login") or "Usuário",
                "grupo": principal.get("grupo"),
                "sistema": _nome_sistema(
                    nomes_sistemas, ultimo["id_sistema"] if ultimo else principal.get("id_sistema")
                ),
                "ip": principal.get("ip_origem"),
                "navegador": agente["descricao"],
                "dispositivo": agente["dispositivo"],
                "estado": _estado(inativo),
                "inativo_segundos": inativo,
                "conectado_segundos": _segundos(agora - principal["criada_em"]),
                "ultima_atividade": principal["ultima_atividade"].isoformat(),
                "sessoes": len(lista),
                "outros_navegadores": sorted(outros)[:3],
                "fazendo": (
                    {
                        "rota": ultimo["rota"],
                        "metodo": ultimo["metodo"],
                        "status": ultimo["status"],
                        "ha_segundos": _segundos(agora - ultimo["data_hora"]),
                    }
                    if ultimo
                    else None
                ),
            }
        )

    ativos = [o for o in online if o["inativo_segundos"] <= janela]
    sessoes_ativas = sum(len(v) for v in por_pessoa.values())
    em_atividade = sum(
        1 for v in por_pessoa.values() for s in v if _segundos(agora - s["ultima_atividade"]) <= janela
    )
    cinco_min = agora - JANELA_ONLINE
    recentes = [a for a in acessos if a["data_hora"] >= cinco_min]
    duracoes = [a["duracao_ms"] for a in recentes if a.get("duracao_ms") is not None]
    erros = [a for a in acessos if (a.get("status") or 0) >= 500]

    feed = [
        {
            "data_hora": a["data_hora"].isoformat(),
            "login": a.get("login") or "visitante",
            "anonimo": a.get("codigo_usuario") is None,  # ainda sem login (ou acabou de sair)
            "rota": a["rota"],
            "metodo": a["metodo"],
            "status": a["status"],
            "duracao_ms": a.get("duracao_ms"),
            "sistema": _nome_sistema(nomes_sistemas, a.get("id_sistema")),
            "ip": a.get("ip"),
        }
        for a in sorted(uteis, key=lambda a: a["data_hora"], reverse=True)[:LIMITE_FEED]
    ]

    return {
        "gerado_em": agora.isoformat(),
        "kpis": {
            "usuarios_online": len(ativos),
            "sessoes_ativas": sessoes_ativas,
            "sessoes_em_atividade": em_atividade,
            "requisicoes_5min": len(recentes),
            "requisicoes_por_minuto": round(len(recentes) / 5, 1),
            "erros_15min": len(erros),
            "tempo_medio_ms": round(sum(duracoes) / len(duracoes)) if duracoes else 0,
        },
        "online": online,
        "navegadores": _ranking(navegadores, em_atividade),
        "sistemas_operacionais": _ranking(sistemas_op, em_atividade),
        "dispositivos": _ranking(dispositivos, em_atividade),
        "atividade": feed,
    }


class ServicoTempoReal:
    """Lê o core e entrega o retrato do momento (somente leitura)."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def obter(self, *, id_sistema: int | None = None) -> dict[str, Any]:
        """`id_sistema=None` enxerga todos os sistemas (escopo global)."""

        agora = agora_local()
        condicoes_acesso = [Log.data_hora >= agora - JANELA_ATIVIDADE]
        if id_sistema is not None:
            condicoes_acesso.append(Log.id_sistema == id_sistema)

        with self._banco.leitura() as db:
            nomes = {i: n for i, n in db.execute(select(Sistema.id_sistema, Sistema.nome_sistema)).all()}
            linhas_acesso = db.execute(
                select(Log).where(*condicoes_acesso).order_by(desc(Log.data_hora)).limit(LIMITE_ACESSOS)
            ).scalars().all()
            condicoes_sessao = [Sessao.status == "ATIVA", Sessao.expira_em > agora, Sessao.codigo_usuario.is_not(None)]
            if id_sistema is not None:
                # O login e unico (SSO): a sessao nasce no sistema onde a pessoa entrou, nao onde ela esta.
                # Entao, no escopo de um sistema, vale quem o esta usando, nao so quem entrou por ele.
                usando = {a.codigo_usuario for a in linhas_acesso if a.codigo_usuario is not None}
                condicoes_sessao.append(or_(Sessao.id_sistema == id_sistema, Sessao.codigo_usuario.in_(usando)))
            linhas_sessao = db.execute(
                select(Sessao, Usuario.nome_usuario, Usuario.sigla_usuariogrupo)
                .outerjoin(Usuario, Usuario.codigo_usuario == Sessao.codigo_usuario)
                .where(*condicoes_sessao)
                .order_by(desc(Sessao.ultima_atividade))
                .limit(LIMITE_SESSOES)
            ).all()
            sessoes = [
                {
                    "codigo_usuario": s.codigo_usuario,
                    "login": s.login_usuario,
                    "nome": nome,
                    "grupo": grupo,
                    "id_sistema": s.id_sistema,
                    "ip_origem": s.ip_origem,
                    "user_agent": s.user_agent,
                    "criada_em": s.criada_em,
                    "ultima_atividade": s.ultima_atividade,
                }
                for s, nome, grupo in linhas_sessao
            ]
            acessos = [
                {
                    "data_hora": a.data_hora,
                    "codigo_usuario": a.codigo_usuario,
                    "login": a.login_usuario,
                    "rota": a.rota_acessada,
                    "metodo": a.metodo_http,
                    "status": a.status_http,
                    "duracao_ms": a.duracao_ms,
                    "id_sistema": a.id_sistema,
                    "ip": a.ip_origem,
                }
                for a in linhas_acesso
            ]
        return consolidar_tempo_real(sessoes, acessos, agora=agora, nomes_sistemas=nomes)


__all__ = ["ServicoTempoReal", "consolidar_tempo_real"]
