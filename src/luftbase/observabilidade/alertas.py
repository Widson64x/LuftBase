"""Alertas para o desenvolvedor: erros 5xx, rajadas de 4xx, eventos criticos, lentidao e sistema parado.

O avaliador (`avaliar`) olha a trilha de auditoria (`tb_logs`, `tb_logevento`), abre ou atualiza um alerta por
problema (`tb_alerta`) e manda **um unico e-mail por ciclo** com o que merece aviso. Regras de antirruido:

- um problema que continua acontecendo soma no MESMO alerta e so volta a avisar depois do intervalo de silencio;
- o alerta fecha sozinho quando para de ocorrer;
- uma trava no banco impede dois executores ao mesmo tempo (thread do app e/ou comando agendado).

O aviso traz so quem, onde e quantas vezes (login, IP, rota normalizada, status, contagem, janela e id de
correlacao). Nunca leva parametros de requisicao, corpo, senha ou token.

Os destinatarios ficam **fixos no codigo** (`DESTINATARIOS_ALERTA`), por decisao do desenvolvedor.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from luftbase.nucleo.tempo import agora_local
from luftbase.observabilidade.insights import normalizar_rota
from luftbase.persistencia.core.alertas import Alerta, AlertaControle
from luftbase.persistencia.core.auditoria import Log, LogEvento
from luftbase.persistencia.core.seguranca import Sistema

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.catalogo import CatalogoBancos
    from luftbase.integracoes.email import ServicoEmail

logger = logging.getLogger(__name__)

# Fixo no codigo de proposito: quem recebe os alertas tecnicos da plataforma.
DESTINATARIOS_ALERTA: tuple[str, ...] = ("widson.araujo@luftlogistics.com",)
TEMPLATE_EMAIL = "luftbase/email/alertas.html"
CHAVE_CONTROLE = "avaliador"
LIMITE_LINHAS_POR_CONSULTA = 20_000


class Regra(StrEnum):
    ERRO_5XX = "ERRO_5XX"
    ERRO_4XX_SEQUENCIA = "ERRO_4XX_SEQUENCIA"
    EVENTO_CRITICO = "EVENTO_CRITICO"
    LENTIDAO = "LENTIDAO"
    SISTEMA_SEM_ACESSO = "SISTEMA_SEM_ACESSO"


ROTULOS: dict[str, str] = {
    Regra.ERRO_5XX: "Erro 5xx",
    Regra.ERRO_4XX_SEQUENCIA: "Rajada de erros 4xx",
    Regra.EVENTO_CRITICO: "Evento critico",
    Regra.LENTIDAO: "Lentidao",
    Regra.SISTEMA_SEM_ACESSO: "Sistema sem acessos",
}


@dataclass(frozen=True, slots=True)
class Limites:
    """Limites iniciais (ajustaveis no codigo; viram configuracao na tela de alertas)."""

    janela_4xx_min: int = 5
    minimo_4xx: int = 10
    janela_lentidao_min: int = 10
    p95_lento_ms: int = 3000
    minimo_requisicoes_lentidao: int = 20
    silencio_min: int = 15
    resolver_apos_min: int = 30
    sem_acesso_min: int = 10
    hora_inicio: int = 7
    hora_fim: int = 19
    minimo_requisicoes_24h: int = 100
    primeira_execucao_min: int = 15
    janela_maxima_min: int = 60
    trava_min: int = 3


LIMITES_PADRAO = Limites()


@dataclass(slots=True)
class Ocorrencia:
    """Um problema visto neste ciclo, antes de virar (ou somar em) um alerta."""

    regra: Regra
    id_sistema: int | None
    login: str | None
    rota: str | None
    status_http: int | None
    quantidade: int
    primeira: datetime
    ultima: datetime
    ip: str | None = None
    id_correlacao: str | None = None
    detalhe: str | None = None
    somar: bool = True  # False: a quantidade e da janela inteira (regras de janela deslizante)

    @property
    def chave(self) -> str:
        return "|".join(
            str(parte if parte not in (None, "") else "-")
            for parte in (self.regra, self.id_sistema, self.login or self.ip, self.rota, self.status_http)
        )


@dataclass(frozen=True, slots=True)
class ResultadoCiclo:
    executou: bool = True
    ocorrencias: int = 0
    alertas_abertos: int = 0
    alertas_atualizados: int = 0
    alertas_resolvidos: int = 0
    avisados: int = 0
    email_enviado: bool = False
    erros: tuple[str, ...] = field(default_factory=tuple)


# --------------------------------------------------------------------------- deteccao


def _percentil(valores: list[int], p: float) -> int:
    if not valores:
        return 0
    ordenados = sorted(valores)
    return ordenados[min(len(ordenados) - 1, max(0, round(p / 100 * (len(ordenados) - 1))))]


def _quem(login: str | None, ip: str | None) -> str | None:
    return login or (f"ip:{ip}" if ip else None)


def _erros_5xx(db: Any, desde: datetime, ate: datetime) -> list[Ocorrencia]:
    linhas = db.execute(
        select(
            Log.id_sistema,
            Log.login_usuario,
            Log.ip_origem,
            Log.rota_acessada,
            Log.status_http,
            Log.id_correlacao,
            Log.data_hora,
        )
        .where(Log.status_http >= 500, Log.data_hora > desde, Log.data_hora <= ate)
        .order_by(Log.data_hora)
        .limit(LIMITE_LINHAS_POR_CONSULTA)
    ).all()
    grupos: dict[tuple[Any, ...], Ocorrencia] = {}
    for id_sistema, login, ip, rota, status, correlacao, quando in linhas:
        rota_norm = normalizar_rota(rota)
        chave = (id_sistema, _quem(login, ip), rota_norm, status)
        atual = grupos.get(chave)
        if atual is None:
            grupos[chave] = Ocorrencia(
                Regra.ERRO_5XX,
                id_sistema,
                login,
                rota_norm,
                int(status),
                1,
                quando,
                quando,
                ip=ip,
                id_correlacao=correlacao,
            )
        else:
            atual.quantidade += 1
            atual.ultima = quando
            atual.id_correlacao = correlacao
    return list(grupos.values())


def _rajadas_4xx(db: Any, agora: datetime, limites: Limites) -> list[Ocorrencia]:
    desde = agora - timedelta(minutes=limites.janela_4xx_min)
    linhas = db.execute(
        select(
            Log.id_sistema,
            Log.login_usuario,
            Log.ip_origem,
            Log.rota_acessada,
            Log.status_http,
            Log.id_correlacao,
            Log.data_hora,
        )
        .where(Log.status_http >= 400, Log.status_http < 500, Log.data_hora > desde)
        .where(Log.data_hora <= agora)
        .order_by(Log.data_hora)
        .limit(LIMITE_LINHAS_POR_CONSULTA)
    ).all()
    por_chave: dict[tuple[Any, ...], list[tuple[Any, ...]]] = defaultdict(list)
    for linha in linhas:
        id_sistema, login, ip, _rota, status, _corr, _quando = linha
        quem = _quem(login, ip)
        if quem is not None:
            por_chave[(id_sistema, quem, int(status))].append(linha)
    resultado: list[Ocorrencia] = []
    for (id_sistema, _quem_chave, status), itens in por_chave.items():
        if len(itens) < limites.minimo_4xx:
            continue
        rotas = Counter(normalizar_rota(i[3]) for i in itens)
        ultima = itens[-1]
        resultado.append(
            Ocorrencia(
                Regra.ERRO_4XX_SEQUENCIA,
                id_sistema,
                ultima[1],
                rotas.most_common(1)[0][0],
                status,
                len(itens),
                itens[0][6],
                ultima[6],
                ip=ultima[2],
                id_correlacao=ultima[5],
                detalhe=f"{len(itens)} respostas {status} em {limites.janela_4xx_min} min",
                somar=False,
            )
        )
    return resultado


def _eventos_criticos(db: Any, desde: datetime, ate: datetime) -> list[Ocorrencia]:
    linhas = db.execute(
        select(
            LogEvento.id_sistema,
            LogEvento.login_usuario,
            LogEvento.ip_origem,
            LogEvento.acao,
            LogEvento.recurso,
            LogEvento.descricao,
            LogEvento.id_correlacao,
            LogEvento.data_hora,
        )
        .where(
            LogEvento.severidade.in_(("ALTA", "CRITICA")),
            LogEvento.data_hora > desde,
            LogEvento.data_hora <= ate,
        )
        .order_by(LogEvento.data_hora)
        .limit(LIMITE_LINHAS_POR_CONSULTA)
    ).all()
    grupos: dict[tuple[Any, ...], Ocorrencia] = {}
    for id_sistema, login, ip, acao, recurso, descricao, correlacao, quando in linhas:
        chave = (id_sistema, _quem(login, ip), recurso, acao)
        atual = grupos.get(chave)
        if atual is None:
            grupos[chave] = Ocorrencia(
                Regra.EVENTO_CRITICO,
                id_sistema,
                login,
                f"{recurso}/{acao}",
                None,
                1,
                quando,
                quando,
                ip=ip,
                id_correlacao=correlacao,
                detalhe=(descricao or "")[:200],
            )
        else:
            atual.quantidade += 1
            atual.ultima = quando
            atual.id_correlacao = correlacao
    return list(grupos.values())


def _lentidao(db: Any, agora: datetime, limites: Limites) -> list[Ocorrencia]:
    desde = agora - timedelta(minutes=limites.janela_lentidao_min)
    linhas = db.execute(
        select(Log.id_sistema, Log.duracao_ms, Log.data_hora).where(
            Log.data_hora > desde, Log.data_hora <= agora
        )
    ).all()
    por_sistema: dict[int, list[int]] = defaultdict(list)
    for id_sistema, duracao, _quando in linhas:
        por_sistema[id_sistema].append(int(duracao or 0))
    resultado: list[Ocorrencia] = []
    for id_sistema, duracoes in por_sistema.items():
        if len(duracoes) < limites.minimo_requisicoes_lentidao:
            continue
        p95 = _percentil(duracoes, 95)
        if p95 > limites.p95_lento_ms:
            resultado.append(
                Ocorrencia(
                    Regra.LENTIDAO,
                    id_sistema,
                    None,
                    None,
                    None,
                    len(duracoes),
                    desde,
                    agora,
                    detalhe=(
                        f"p95 de {p95} ms em {len(duracoes)} requisicoes "
                        f"nos ultimos {limites.janela_lentidao_min} min (limite {limites.p95_lento_ms} ms)"
                    ),
                    somar=False,
                )
            )
    return resultado


def _em_horario_comercial(agora: datetime, limites: Limites) -> bool:
    minutos = agora.hour * 60 + agora.minute
    inicio = limites.hora_inicio * 60 + limites.sem_acesso_min
    return agora.weekday() < 5 and inicio <= minutos < limites.hora_fim * 60


def _sistemas_sem_acesso(db: Any, agora: datetime, limites: Limites) -> list[Ocorrencia]:
    if not _em_horario_comercial(agora, limites):
        return []
    corte_recente = agora - timedelta(minutes=limites.sem_acesso_min)
    ativos = db.execute(select(Sistema.id_sistema).where(Sistema.ativo.is_(True))).scalars().all()
    resultado: list[Ocorrencia] = []
    for id_sistema in ativos:
        total_24h = db.execute(
            select(Log.id_log)
            .where(Log.id_sistema == id_sistema, Log.data_hora > agora - timedelta(hours=24))
            .limit(limites.minimo_requisicoes_24h)
        ).all()
        if len(total_24h) < limites.minimo_requisicoes_24h:
            continue  # pouco uso: silencio e normal, alertar seria ruido
        recente = db.execute(
            select(Log.id_log)
            .where(Log.id_sistema == id_sistema, Log.data_hora > corte_recente)
            .limit(1)
        ).first()
        if recente is None:
            resultado.append(
                Ocorrencia(
                    Regra.SISTEMA_SEM_ACESSO,
                    id_sistema,
                    None,
                    None,
                    None,
                    0,
                    corte_recente,
                    agora,
                    detalhe=f"nenhum acesso ha mais de {limites.sem_acesso_min} min em horario comercial",
                    somar=False,
                )
            )
    return resultado


def detectar(
    db: Any, agora: datetime, desde: datetime, limites: Limites = LIMITES_PADRAO
) -> list[Ocorrencia]:
    """Roda todas as regras. `desde` vale para as regras incrementais (5xx e eventos criticos)."""

    return [
        *_erros_5xx(db, desde, agora),
        *_eventos_criticos(db, desde, agora),
        *_rajadas_4xx(db, agora, limites),
        *_lentidao(db, agora, limites),
        *_sistemas_sem_acesso(db, agora, limites),
    ]


# --------------------------------------------------------------------------- estado


def aplicar(
    db: Any, ocorrencias: Iterable[Ocorrencia], agora: datetime, limites: Limites = LIMITES_PADRAO
) -> tuple[int, int, int]:
    """Abre/atualiza alertas e fecha os que pararam. Devolve (abertos, atualizados, resolvidos)."""

    abertos = atualizados = 0
    vistas: set[str] = set()
    for ocorrencia in ocorrencias:
        vistas.add(ocorrencia.chave)
        alerta = db.execute(
            select(Alerta).where(Alerta.chave == ocorrencia.chave, Alerta.status == "ABERTO")
        ).scalar_one_or_none()
        if alerta is None:
            db.add(
                Alerta(
                    chave=ocorrencia.chave,
                    regra=ocorrencia.regra.value,
                    id_sistema=ocorrencia.id_sistema,
                    login_usuario=ocorrencia.login,
                    rota=ocorrencia.rota,
                    status_http=ocorrencia.status_http,
                    ip_origem=ocorrencia.ip,
                    id_correlacao=ocorrencia.id_correlacao,
                    detalhe=ocorrencia.detalhe,
                    status="ABERTO",
                    ocorrencias=ocorrencia.quantidade,
                    ocorrencias_notificadas=0,
                    primeira_ocorrencia=ocorrencia.primeira,
                    ultima_ocorrencia=ocorrencia.ultima,
                    aberto_em=agora,
                )
            )
            abertos += 1
            continue
        alerta.ocorrencias = (
            alerta.ocorrencias + ocorrencia.quantidade
            if ocorrencia.somar
            else max(alerta.ocorrencias, ocorrencia.quantidade)
        )
        alerta.ultima_ocorrencia = ocorrencia.ultima
        alerta.id_correlacao = ocorrencia.id_correlacao or alerta.id_correlacao
        alerta.detalhe = ocorrencia.detalhe or alerta.detalhe
        atualizados += 1
    db.flush()

    limite_resolver = agora - timedelta(minutes=limites.resolver_apos_min)
    resolvidos = 0
    for alerta in db.execute(
        select(Alerta).where(Alerta.status == "ABERTO", Alerta.ultima_ocorrencia < limite_resolver)
    ).scalars():
        if alerta.chave in vistas:
            continue
        alerta.status = "RESOLVIDO"
        alerta.resolvido_em = agora
        resolvidos += 1
    return abertos, atualizados, resolvidos


def _precisa_avisar(alerta: Alerta, agora: datetime, limites: Limites) -> bool:
    if alerta.silenciado_ate is not None and alerta.silenciado_ate > agora:
        return False
    if alerta.ultima_notificacao is None:
        return True
    if alerta.ocorrencias <= alerta.ocorrencias_notificadas:
        return False
    return agora - alerta.ultima_notificacao >= timedelta(minutes=limites.silencio_min)


def pendentes_de_aviso(db: Any, agora: datetime, limites: Limites = LIMITES_PADRAO) -> list[Alerta]:
    abertos = db.execute(
        select(Alerta).where(Alerta.status == "ABERTO").order_by(Alerta.aberto_em)
    ).scalars()
    return [a for a in abertos if _precisa_avisar(a, agora, limites)]


# --------------------------------------------------------------------------- e-mail


def _nome_sistemas(db: Any, ids: Iterable[int | None]) -> dict[int | None, str]:
    validos = {i for i in ids if i is not None}
    nomes: dict[int | None, str] = {None: "-"}
    if validos:
        for id_sistema, nome in db.execute(
            select(Sistema.id_sistema, Sistema.nome_sistema).where(Sistema.id_sistema.in_(validos))
        ):
            nomes[id_sistema] = nome
    return nomes


def montar_itens(alertas: list[Alerta], nomes: dict[int | None, str], agora: datetime) -> list[dict[str, Any]]:
    itens = []
    for a in alertas:
        novas = a.ocorrencias - a.ocorrencias_notificadas
        linhas: list[tuple[str, str]] = [
            ("Sistema", nomes.get(a.id_sistema, str(a.id_sistema))),
            ("Usuario", a.login_usuario or (f"IP {a.ip_origem}" if a.ip_origem else "-")),
        ]
        if a.rota:
            linhas.append(("Rota", a.rota))
        if a.status_http:
            linhas.append(("Status", str(a.status_http)))
        linhas.append(
            (
                "Ocorrencias",
                f"{a.ocorrencias}" + (f" ({novas} desde o ultimo aviso)" if a.ultima_notificacao else ""),
            )
        )
        linhas.append(
            (
                "Janela",
                f"{a.primeira_ocorrencia:%d/%m %H:%M:%S} a {a.ultima_ocorrencia:%d/%m %H:%M:%S}",
            )
        )
        if a.detalhe:
            linhas.append(("Detalhe", a.detalhe))
        if a.id_correlacao:
            linhas.append(("Correlacao", a.id_correlacao))
        itens.append({"titulo": ROTULOS.get(a.regra, a.regra), "linhas": linhas})
    return itens


def _assunto(alertas: list[Alerta], nomes: dict[int | None, str]) -> str:
    primeiro = alertas[0]
    base = f"[LuftBase] {ROTULOS.get(primeiro.regra, primeiro.regra)}"
    quem = primeiro.login_usuario or primeiro.ip_origem
    if quem:
        base += f": {quem}"
    base += f" em {nomes.get(primeiro.id_sistema, primeiro.id_sistema)}"
    if len(alertas) > 1:
        base += f" (+{len(alertas) - 1} alerta(s))"
    return base


# --------------------------------------------------------------------------- ciclo


def _obter_trava(db: Any, agora: datetime, limites: Limites) -> AlertaControle | None:
    controle = db.get(AlertaControle, CHAVE_CONTROLE)
    if controle is None:
        db.add(AlertaControle(chave=CHAVE_CONTROLE))
        db.flush()
    resultado = db.execute(
        update(AlertaControle)
        .where(
            AlertaControle.chave == CHAVE_CONTROLE,
            (AlertaControle.em_execucao_ate.is_(None)) | (AlertaControle.em_execucao_ate < agora),
        )
        .values(em_execucao_ate=agora + timedelta(minutes=limites.trava_min))
    )
    if resultado.rowcount != 1:
        return None
    db.flush()
    db.expire_all()
    return db.get(AlertaControle, CHAVE_CONTROLE)


def avaliar(
    bancos: CatalogoBancos,
    email: ServicoEmail,
    *,
    agora: datetime | None = None,
    limites: Limites = LIMITES_PADRAO,
    destinatarios: Iterable[str] = DESTINATARIOS_ALERTA,
    enviar_email: Callable[..., Any] | None = None,
) -> ResultadoCiclo:
    """Um ciclo do avaliador. Nunca levanta: qualquer falha vira log e `erros`."""

    agora = agora or agora_local()
    erros: list[str] = []
    travou = False
    try:
        # Transacao 1: trava, detecta e atualiza os alertas. O e-mail NAO sai daqui: a auditoria do envio abre
        # outra unidade de trabalho na mesma sessao da thread, e aninhar as duas falha ("transaction is already begun").
        with bancos.core.unidade_trabalho() as db:
            controle = _obter_trava(db, agora, limites)
            if controle is None:
                return ResultadoCiclo(executou=False)
            travou = True
            piso = agora - timedelta(minutes=limites.janela_maxima_min)
            desde = controle.ultima_execucao_ate or (
                agora - timedelta(minutes=limites.primeira_execucao_min)
            )
            desde = max(desde, piso)
            ocorrencias = detectar(db, agora, desde, limites)
            abertos, atualizados, resolvidos = aplicar(db, ocorrencias, agora, limites)
            controle.ultima_execucao_ate = agora
            db.flush()

            pendentes = pendentes_de_aviso(db, agora, limites)
            ids_pendentes = [a.id_alerta for a in pendentes]
            itens: list[dict[str, Any]] = []
            assunto = ""
            if pendentes:
                nomes = _nome_sistemas(db, (a.id_sistema for a in pendentes))
                itens = montar_itens(pendentes, nomes, agora)
                assunto = _assunto(pendentes, nomes)

        enviado = False
        if ids_pendentes:
            enviado = _enviar(email, list(destinatarios), assunto, itens, agora, enviar_email, erros)

        # Transacao 2: registra o aviso e solta a trava (a trava segue valendo durante o envio).
        with bancos.core.unidade_trabalho() as db:
            if enviado:
                for alerta in db.execute(
                    select(Alerta).where(Alerta.id_alerta.in_(ids_pendentes))
                ).scalars():
                    alerta.ultima_notificacao = agora
                    alerta.ocorrencias_notificadas = alerta.ocorrencias
            controle = db.get(AlertaControle, CHAVE_CONTROLE)
            if controle is not None:
                controle.em_execucao_ate = None
            travou = False
        return ResultadoCiclo(
            ocorrencias=len(ocorrencias),
            alertas_abertos=abertos,
            alertas_atualizados=atualizados,
            alertas_resolvidos=resolvidos,
            avisados=len(ids_pendentes) if enviado else 0,
            email_enviado=enviado,
            erros=tuple(erros),
        )
    except Exception as erro:
        logger.debug("Avaliador de alertas falhou", exc_info=True)
        if travou:
            _soltar_trava(bancos)
        return ResultadoCiclo(erros=(f"{type(erro).__name__}: {erro}",))


def _soltar_trava(bancos: CatalogoBancos) -> None:
    """Depois de uma falha, nao deixa a trava presa ate expirar."""

    try:
        with bancos.core.unidade_trabalho() as db:
            controle = db.get(AlertaControle, CHAVE_CONTROLE)
            if controle is not None:
                controle.em_execucao_ate = None
    except Exception:
        logger.debug("Nao foi possivel soltar a trava do avaliador", exc_info=True)


def _enviar(
    email: ServicoEmail,
    destinatarios: list[str],
    assunto: str,
    itens: list[dict[str, Any]],
    agora: datetime,
    enviar_email: Callable[..., Any] | None,
    erros: list[str],
) -> bool:
    if not destinatarios:
        return False
    try:
        if enviar_email is not None:
            resultado = enviar_email(destinatarios, assunto, itens)
        else:
            if not email.configurado:
                erros.append("E-mail nao configurado; os alertas ficam pendentes.")
                return False
            resultado = email.enviar(
                destinatarios,
                assunto,
                template=TEMPLATE_EMAIL,
                contexto={"itens": itens, "gerado_em": f"{agora:%d/%m/%Y %H:%M:%S}"},
            )
        if getattr(resultado, "sucesso", False):
            return True
        erros.append(f"E-mail de alerta nao entregue: {getattr(resultado, 'erro', None)}")
    except Exception as erro:
        logger.exception("Falha ao enviar o e-mail de alerta")
        erros.append(f"{type(erro).__name__}: {erro}")
    return False


# --------------------------------------------------------------------------- consulta (painel/CLI)


def listar_alertas(db: Any, *, somente_abertos: bool = True, limite: int = 100) -> list[dict[str, Any]]:
    consulta = select(Alerta).order_by(Alerta.ultima_ocorrencia.desc()).limit(max(1, min(limite, 500)))
    if somente_abertos:
        consulta = consulta.where(Alerta.status == "ABERTO")
    alertas = list(db.execute(consulta).scalars())
    nomes = _nome_sistemas(db, (a.id_sistema for a in alertas))
    return [
        {
            "id_alerta": a.id_alerta,
            "regra": a.regra,
            "rotulo": ROTULOS.get(a.regra, a.regra),
            "sistema": nomes.get(a.id_sistema),
            "id_sistema": a.id_sistema,
            "login": a.login_usuario,
            "ip": a.ip_origem,
            "rota": a.rota,
            "status_http": a.status_http,
            "ocorrencias": a.ocorrencias,
            "status": a.status,
            "primeira_ocorrencia": a.primeira_ocorrencia.isoformat(timespec="seconds"),
            "ultima_ocorrencia": a.ultima_ocorrencia.isoformat(timespec="seconds"),
            "resolvido_em": a.resolvido_em.isoformat(timespec="seconds") if a.resolvido_em else None,
            "silenciado_ate": a.silenciado_ate.isoformat(timespec="seconds")
            if a.silenciado_ate
            else None,
            "id_correlacao": a.id_correlacao,
            "detalhe": a.detalhe,
        }
        for a in alertas
    ]


def silenciar(db: Any, id_alerta: int, ate: datetime | None) -> bool:
    alerta = db.get(Alerta, id_alerta)
    if alerta is None:
        return False
    alerta.silenciado_ate = ate
    return True


__all__ = [
    "DESTINATARIOS_ALERTA",
    "Limites",
    "Ocorrencia",
    "Regra",
    "ResultadoCiclo",
    "aplicar",
    "avaliar",
    "detectar",
    "listar_alertas",
    "pendentes_de_aviso",
    "silenciar",
]
