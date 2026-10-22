"""Fila de e-mails: quem precisa enviar grava na fila e segue; o envio acontece em segundo plano.

Dar acesso a um grupo de 200 pessoas gerava 200 e-mails dentro da requisicao e a tela ficava carregando. Agora
`enfileirar` so grava linhas em `core.tb_email_fila` (milissegundos) e `processar` entrega em lotes, com nova
tentativa em caso de falha. Varios servidores podem processar ao mesmo tempo: cada lote e reservado com
`FOR UPDATE SKIP LOCKED`, entao nenhum e-mail sai duas vezes.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, or_, select, update

from luftbase.integracoes.email.enderecos import normalizar_enderecos_email
from luftbase.nucleo.excecoes import EmailNaoConfigurado, ErroEmail
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core.email_fila import EmailFila

if TYPE_CHECKING:
    from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
    from luftbase.integracoes.email.servico import ServicoEmail

logger = logging.getLogger(__name__)

# Espera antes da 2a, 3a e 4a tentativa; depois disso o e-mail fica FALHOU (e pode ser reenviado na tela).
ESPERAS_SEGUNDOS = (60, 300, 1800)
MAXIMO_TENTATIVAS = len(ESPERAS_SEGUNDOS) + 1
RESERVA_SEGUNDOS = 600  # um lote "ENVIANDO" parado ha mais que isto (processo morreu) volta para a fila
SITUACOES = ("pendentes", "enviados", "falhas", "todos")
_STATUS_DA_SITUACAO = {
    "pendentes": ("PENDENTE", "ENVIANDO"),
    "enviados": ("ENVIADO",),
    "falhas": ("FALHOU", "CANCELADO"),
}


@dataclass(frozen=True, slots=True)
class ResultadoProcessamento:
    reservados: int = 0
    enviados: int = 0
    reagendados: int = 0
    falhas: int = 0

    def __add__(self, outro: ResultadoProcessamento) -> ResultadoProcessamento:
        return ResultadoProcessamento(
            self.reservados + outro.reservados,
            self.enviados + outro.enviados,
            self.reagendados + outro.reagendados,
            self.falhas + outro.falhas,
        )


def _como_lista(valor: str | Iterable[str] | None) -> list[str]:
    if not valor:
        return []
    return list(normalizar_enderecos_email(valor))


class FilaEmail:
    """Grava e entrega e-mails em lote; quem enfileira so recebe `ErroEmail` por uso incorreto."""

    def __init__(self, banco: BancoSQLAlchemy, email: ServicoEmail) -> None:
        self._banco = banco
        self._email = email

    # ------------------------------------------------------------------ gravar
    def montar(
        self,
        para: str | Iterable[str],
        assunto: str,
        *,
        template: str | None = None,
        contexto: Mapping[str, Any] | None = None,
        html: str | None = None,
        texto: str | None = None,
        copia: str | Iterable[str] = (),
        nome_remetente: str | None = None,
        responder_para: str | None = None,
        origem: str = "GERAL",
        id_sistema: int | None = None,
        criado_por: str | None = None,
    ) -> EmailFila:
        """Valida e monta a linha (sem gravar). Erros de uso viram `ErroEmail` ja aqui, nao na entrega."""

        destinatarios = _como_lista(para)
        if not destinatarios:
            raise ErroEmail("Informe ao menos um destinatario.")
        if not (assunto or "").strip():
            raise ErroEmail("O assunto do e-mail e obrigatorio.")
        if template is not None and html is not None:
            raise ErroEmail("Informe `template` ou `html`, nunca os dois.")
        if template is None and html is None and texto is None:
            raise ErroEmail("A mensagem precisa de `template`, `html` ou `texto`.")
        try:
            contexto_json = json.dumps(dict(contexto), ensure_ascii=False) if contexto else None
        except (TypeError, ValueError) as erro:
            raise ErroEmail("O contexto do e-mail precisa conter so texto, numeros e listas.") from erro
        return EmailFila(
            id_sistema=id_sistema,
            origem=(origem or "GERAL")[:60],
            status="PENDENTE",
            destinatarios=json.dumps(destinatarios),
            copia=json.dumps(_como_lista(copia)) if copia else None,
            assunto=assunto.strip()[:300],
            template=template,
            contexto=contexto_json,
            html=html,
            texto=texto,
            nome_remetente=(nome_remetente or None),
            responder_para=responder_para or None,
            tentativas=0,
            maximo_tentativas=MAXIMO_TENTATIVAS,
            proxima_tentativa=agora_local(),
            criado_por=(criado_por or None),
        )

    def enfileirar(self, para: str | Iterable[str], assunto: str, **opcoes: Any) -> int:
        """Grava um e-mail na fila e devolve o identificador."""

        return self.enfileirar_varios([self.montar(para, assunto, **opcoes)])[0]

    def enfileirar_varios(self, linhas: Sequence[EmailFila]) -> list[int]:
        """Grava varios e-mails numa unica transacao (tudo ou nada)."""

        if not linhas:
            return []
        with self._banco.escrita() as sessao:
            sessao.add_all(linhas)
            sessao.flush()
            return [int(linha.id_email) for linha in linhas]

    # ------------------------------------------------------------------ entregar
    def _reservar(self, limite: int) -> list[dict[str, Any]]:
        agora = agora_local()
        with self._banco.escrita() as sessao:
            consulta = (
                select(EmailFila)
                .where(
                    or_(
                        and_(EmailFila.status == "PENDENTE", EmailFila.proxima_tentativa <= agora),
                        and_(
                            EmailFila.status == "ENVIANDO",
                            EmailFila.bloqueado_ate.is_not(None),
                            EmailFila.bloqueado_ate < agora,
                        ),
                    )
                )
                .order_by(EmailFila.proxima_tentativa, EmailFila.id_email)
                .limit(max(1, limite))
                .with_for_update(skip_locked=True)
            )
            linhas = list(sessao.execute(consulta).scalars())
            itens: list[dict[str, Any]] = []
            for linha in linhas:
                linha.status = "ENVIANDO"
                linha.tentativas = int(linha.tentativas or 0) + 1
                linha.bloqueado_ate = agora + timedelta(seconds=RESERVA_SEGUNDOS)
                linha.atualizado_em = agora
                itens.append(
                    {
                        "id": int(linha.id_email),
                        "tentativas": int(linha.tentativas),
                        "maximo": int(linha.maximo_tentativas or MAXIMO_TENTATIVAS),
                        "para": json.loads(linha.destinatarios),
                        "copia": json.loads(linha.copia) if linha.copia else [],
                        "assunto": linha.assunto,
                        "template": linha.template,
                        "contexto": json.loads(linha.contexto) if linha.contexto else None,
                        "html": linha.html,
                        "texto": linha.texto,
                        "nome_remetente": linha.nome_remetente,
                        "responder_para": linha.responder_para,
                    }
                )
            return itens

    def _concluir(self, id_email: int, **valores: Any) -> None:
        with self._banco.escrita() as sessao:
            sessao.execute(
                update(EmailFila)
                .where(EmailFila.id_email == id_email)
                .values(atualizado_em=agora_local(), bloqueado_ate=None, **valores)
            )

    def processar(self, limite: int = 50) -> ResultadoProcessamento:
        """Entrega um lote (uma sessao SMTP). Falha de um e-mail nao interrompe os demais."""

        itens = self._reservar(limite)
        if not itens:
            return ResultadoProcessamento()
        enviados = reagendados = falhas = 0
        preparados: list[tuple[dict[str, Any], Any]] = []
        try:
            for item in itens:
                try:
                    envio = self._email.preparar(
                        item["para"],
                        item["assunto"],
                        template=item["template"],
                        contexto=item["contexto"],
                        html=item["html"],
                        texto=item["texto"],
                        copia=item["copia"],
                        nome_remetente=item["nome_remetente"],
                        responder_para=item["responder_para"],
                    )
                except EmailNaoConfigurado:
                    raise
                except Exception as erro:  # endereco invalido, template ausente: repetir nao resolve
                    self._concluir(item["id"], status="FALHOU", ultimo_erro=str(erro)[:1000])
                    falhas += 1
                    logger.warning("E-mail #%s nao pode ser montado: %s", item["id"], erro)
                    continue
                preparados.append((item, envio))
            resultados = (
                self._email.enviar_lote([envio for _, envio in preparados]) if preparados else []
            )
        except EmailNaoConfigurado:
            # Sem e-mail configurado nada pode sair: devolve o lote sem gastar tentativa.
            self._devolver([i["id"] for i in itens], "O e-mail nao esta configurado neste ambiente.")
            return ResultadoProcessamento(reservados=len(itens), reagendados=len(itens))
        except Exception as erro:
            logger.exception("Falha inesperada ao entregar o lote da fila de e-mail")
            for item, _ in preparados:
                reagendados, falhas = self._falhar(
                    item, f"{type(erro).__name__}: {erro}", reagendados, falhas
                )
            return ResultadoProcessamento(len(itens), enviados, reagendados, falhas)

        for (item, _), resultado in zip(preparados, resultados, strict=False):
            if resultado.sucesso:
                self._concluir(
                    item["id"], status="ENVIADO", enviado_em=agora_local(), ultimo_erro=None
                )
                enviados += 1
            else:
                reagendados, falhas = self._falhar(
                    item, resultado.erro or "Falha na entrega.", reagendados, falhas
                )
        logger.info(
            "Fila de e-mail: %s enviado(s), %s reagendado(s), %s com falha definitiva (lote de %s).",
            enviados,
            reagendados,
            falhas,
            len(itens),
        )
        return ResultadoProcessamento(len(itens), enviados, reagendados, falhas)

    def _falhar(
        self, item: dict[str, Any], erro: str, reagendados: int, falhas: int
    ) -> tuple[int, int]:
        if item["tentativas"] >= item["maximo"]:
            self._concluir(item["id"], status="FALHOU", ultimo_erro=erro[:1000])
            return reagendados, falhas + 1
        espera = ESPERAS_SEGUNDOS[min(item["tentativas"] - 1, len(ESPERAS_SEGUNDOS) - 1)]
        self._concluir(
            item["id"],
            status="PENDENTE",
            ultimo_erro=erro[:1000],
            proxima_tentativa=agora_local() + timedelta(seconds=espera),
        )
        return reagendados + 1, falhas

    def _devolver(self, ids: list[int], motivo: str) -> None:
        for id_email in ids:
            with self._banco.escrita() as sessao:
                sessao.execute(
                    update(EmailFila)
                    .where(EmailFila.id_email == id_email)
                    .values(
                        status="PENDENTE",
                        tentativas=EmailFila.tentativas - 1,
                        proxima_tentativa=agora_local() + timedelta(minutes=5),
                        bloqueado_ate=None,
                        ultimo_erro=motivo,
                        atualizado_em=agora_local(),
                    )
                )

    def processar_tudo(
        self, *, limite_lote: int = 50, maximo_lotes: int = 20
    ) -> ResultadoProcessamento:
        """Entrega lotes seguidos ate esvaziar a fila (ou atingir `maximo_lotes`)."""

        total = ResultadoProcessamento()
        for _ in range(maximo_lotes):
            parcial = self.processar(limite_lote)
            total = total + parcial
            if parcial.reservados < limite_lote:
                break
        return total

    # ------------------------------------------------------------------ consultar e manter
    def contar(self) -> dict[str, int]:
        with self._banco.leitura() as sessao:
            linhas = dict(
                sessao.execute(
                    select(EmailFila.status, func.count(EmailFila.id_email)).group_by(EmailFila.status)
                ).all()
            )
        pendentes = int(linhas.get("PENDENTE", 0)) + int(linhas.get("ENVIANDO", 0))
        enviados = int(linhas.get("ENVIADO", 0))
        falhas = int(linhas.get("FALHOU", 0)) + int(linhas.get("CANCELADO", 0))
        return {
            "pendentes": pendentes,
            "enviados": enviados,
            "falhas": falhas,
            "todos": pendentes + enviados + falhas,
        }

    def consultar(
        self,
        *,
        situacao: str = "pendentes",
        termo: str | None = None,
        limite: int = 50,
        deslocamento: int = 0,
    ) -> dict[str, Any]:
        if situacao not in SITUACOES:
            raise ValueError("situacao invalida")
        filtros: list[Any] = []
        if situacao != "todos":
            filtros.append(EmailFila.status.in_(_STATUS_DA_SITUACAO[situacao]))
        texto = (termo or "").strip()
        if texto:
            filtros.append(
                or_(
                    *(
                        coluna.icontains(texto, autoescape=True)
                        for coluna in (
                            EmailFila.destinatarios,
                            EmailFila.assunto,
                            EmailFila.origem,
                            EmailFila.ultimo_erro,
                        )
                    )
                )
            )
        with self._banco.leitura() as sessao:
            total = int(sessao.scalar(select(func.count(EmailFila.id_email)).where(*filtros)) or 0)
            linhas = list(
                sessao.execute(
                    select(EmailFila)
                    .where(*filtros)
                    .order_by(EmailFila.id_email.desc())
                    .offset(max(deslocamento, 0))
                    .limit(max(1, min(limite, 200)))
                ).scalars()
            )
        return {
            "itens": [self._serializar(linha) for linha in linhas],
            "total": total,
            "contagens": self.contar(),
        }

    @staticmethod
    def _serializar(linha: EmailFila) -> dict[str, Any]:
        destinos = json.loads(linha.destinatarios)

        def iso(valor: datetime | None) -> str | None:
            return valor.isoformat(timespec="seconds") if valor else None

        return {
            "id_email": linha.id_email,
            "origem": linha.origem,
            "status": linha.status,
            "destinatarios": destinos,
            "resumo_destinatarios": destinos[0]
            + (f" (+{len(destinos) - 1})" if len(destinos) > 1 else ""),
            "assunto": linha.assunto,
            "tentativas": linha.tentativas,
            "maximo_tentativas": linha.maximo_tentativas,
            "proxima_tentativa": iso(linha.proxima_tentativa),
            "ultimo_erro": linha.ultimo_erro,
            "criado_por": linha.criado_por,
            "criado_em": iso(linha.criado_em),
            "enviado_em": iso(linha.enviado_em),
        }

    def reenviar(self, id_email: int) -> bool:
        """Poe de volta na fila um e-mail que falhou (zera as tentativas)."""

        with self._banco.escrita() as sessao:
            resultado = sessao.execute(
                update(EmailFila)
                .where(EmailFila.id_email == id_email, EmailFila.status.in_(("FALHOU", "CANCELADO")))
                .values(
                    status="PENDENTE",
                    tentativas=0,
                    proxima_tentativa=agora_local(),
                    bloqueado_ate=None,
                    atualizado_em=agora_local(),
                )
            )
            return bool(resultado.rowcount)

    def cancelar(self, id_email: int) -> bool:
        """Cancela um e-mail ainda pendente (nao sai mais)."""

        with self._banco.escrita() as sessao:
            resultado = sessao.execute(
                update(EmailFila)
                .where(EmailFila.id_email == id_email, EmailFila.status == "PENDENTE")
                .values(
                    status="CANCELADO",
                    atualizado_em=agora_local(),
                    ultimo_erro="Cancelado manualmente.",
                )
            )
            return bool(resultado.rowcount)

    def limpar(self, *, dias_enviados: int = 30, dias_falhas: int = 90) -> int:
        """Apaga e-mails antigos (enviados depois de `dias_enviados`, falhas/cancelados depois de `dias_falhas`)."""

        agora = agora_local()
        with self._banco.escrita() as sessao:
            resultado = sessao.execute(
                delete(EmailFila).where(
                    or_(
                        and_(
                            EmailFila.status == "ENVIADO",
                            EmailFila.criado_em < agora - timedelta(days=dias_enviados),
                        ),
                        and_(
                            EmailFila.status.in_(("FALHOU", "CANCELADO")),
                            EmailFila.criado_em < agora - timedelta(days=dias_falhas),
                        ),
                    )
                )
            )
            return int(resultado.rowcount or 0)


__all__ = ["ESPERAS_SEGUNDOS", "MAXIMO_TENTATIVAS", "SITUACOES", "FilaEmail", "ResultadoProcessamento"]
