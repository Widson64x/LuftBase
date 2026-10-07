"""Controle administrativo de sessões: encerrar uma sessão, desconectar uma pessoa ou todos.

Quem chama já passou por permissão (`SEGURANCA.SESSOES.REVOGAR`), CSRF e auditoria; aqui ficam as regras:

- só sessões ATIVAS e de pessoas logadas (visitantes não contam);
- a sessão que o próprio administrador está usando nunca é encerrada por aqui (para isso existe "Sair");
- no escopo de um sistema (não o global), vale quem entrou por ele ou o usou nos últimos 15 minutos,
  o mesmo critério do painel "Ao vivo";
- a sessão é identificada por uma referência (hash), nunca pelo identificador cru, que não sai do servidor.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from sqlalchemy import or_, select

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core import Log, Sessao

JANELA_USO = timedelta(minutes=15)
LIMITE_LOTE = 1000
MOTIVO = "REVOGADA_ADMIN"


class ArmazenamentoRevogavel(Protocol):
    def revogar_sessao(self, id_sessao: str, motivo: str = ...) -> bool: ...


def referencia(id_sessao: str) -> str:
    """Identificador público de uma sessão: curto, estável e sem revelar o id real."""

    return hashlib.sha256(id_sessao.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True, slots=True)
class ResultadoEncerramento:
    encerradas: int
    pessoas: int = 0
    login: str | None = None
    motivo_recusa: str | None = None  # "nao_encontrada" | "propria" | None


class ServicoControleSessoes:
    def __init__(self, banco: BancoSQLAlchemy, armazenamento: ArmazenamentoRevogavel) -> None:
        self._banco = banco
        self._armazenamento = armazenamento

    def _ativas(self, *, id_sistema: int | None, codigo_usuario: int | None = None) -> list[Any]:
        agora = agora_local()
        condicoes: list[Any] = [
            Sessao.status == "ATIVA",
            Sessao.codigo_usuario.is_not(None),
            Sessao.expira_em > agora,
        ]
        if codigo_usuario is not None:
            condicoes.append(Sessao.codigo_usuario == codigo_usuario)
        if id_sistema is not None:
            usando = select(Log.codigo_usuario).where(
                Log.id_sistema == id_sistema,
                Log.codigo_usuario.is_not(None),
                Log.data_hora >= agora - JANELA_USO,
            )
            condicoes.append(or_(Sessao.id_sistema == id_sistema, Sessao.codigo_usuario.in_(usando)))
        with self._banco.leitura() as db:
            return list(
                db.execute(
                    select(Sessao.id_sessao, Sessao.codigo_usuario, Sessao.login_usuario)
                    .where(*condicoes)
                    .limit(LIMITE_LOTE)
                ).all()
            )

    def _revogar(self, linhas: list[Any], id_sessao_atual: str) -> tuple[int, set[Any]]:
        total = 0
        pessoas: set[Any] = set()
        for id_sessao, codigo, _login in linhas:
            if id_sessao == id_sessao_atual:
                continue
            if self._armazenamento.revogar_sessao(id_sessao, MOTIVO):
                total += 1
                pessoas.add(codigo)
        return total, pessoas

    def encerrar_sessao(self, ref: str, *, id_sistema: int | None, id_sessao_atual: str) -> ResultadoEncerramento:
        alvo = next(
            (linha for linha in self._ativas(id_sistema=id_sistema) if referencia(linha[0]) == ref),
            None,
        )
        if alvo is None:
            return ResultadoEncerramento(0, motivo_recusa="nao_encontrada")
        if alvo[0] == id_sessao_atual:
            return ResultadoEncerramento(0, login=alvo[2], motivo_recusa="propria")
        total, pessoas = self._revogar([alvo], id_sessao_atual)
        return ResultadoEncerramento(total, len(pessoas), alvo[2], None if total else "nao_encontrada")

    def encerrar_pessoa(self, codigo_usuario: int, *, id_sistema: int | None, id_sessao_atual: str) -> ResultadoEncerramento:
        linhas = self._ativas(id_sistema=id_sistema, codigo_usuario=codigo_usuario)
        if not linhas:
            return ResultadoEncerramento(0, motivo_recusa="nao_encontrada")
        if all(linha[0] == id_sessao_atual for linha in linhas):
            return ResultadoEncerramento(0, login=linhas[0][2], motivo_recusa="propria")
        total, pessoas = self._revogar(linhas, id_sessao_atual)
        return ResultadoEncerramento(total, len(pessoas), linhas[0][2])

    def encerrar_todas(self, *, id_sistema: int | None, id_sessao_atual: str) -> ResultadoEncerramento:
        total, pessoas = self._revogar(self._ativas(id_sistema=id_sistema), id_sessao_atual)
        return ResultadoEncerramento(total, len(pessoas))


__all__ = ["ResultadoEncerramento", "ServicoControleSessoes", "referencia"]
