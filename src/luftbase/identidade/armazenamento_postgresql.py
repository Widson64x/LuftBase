"""Armazenamento de sessoes corporativas no PostgreSQL (schema core).

Centraliza sessoes ativas, controle de usuarios online, historico de eventos,
renovacoes de inatividade por interacao na tela e encerramento voluntario ou timeout.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from flask import current_app, has_request_context, request
from sqlalchemy import func, select, update

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.tempo import agora_local
from luftbase.persistencia.core.sessoes import EventoSessao, Sessao
from luftbase.persistencia.core.usuario import Usuario

logger = logging.getLogger("luftbase.sessoes")


class ArmazenamentoSessoesPostgreSQL:
    """Implementa ArmazenamentoSessoes usando o banco core PostgreSQL."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    @staticmethod
    def _eh_chave_sessao(chave: str) -> bool:
        """Filtra chaves que nao pertencem ao subsistema de sessoes (ex: caches)."""
        return not (chave.startswith("luft:") and not chave.startswith("luft:sessao:"))

    @staticmethod
    def _limpar_chave(chave: str) -> str:
        return chave.removeprefix("luft:sessao:").strip()

    @staticmethod
    def _atualizar_usuario_ao_ativar(
        sessao_db: Any,
        codigo_usuario: int,
        id_sessao: str,
        agora: datetime,
        ip_origem: str | None,
        user_agent: str | None,
        novo_login: bool = False,
    ) -> None:
        try:
            usuario = sessao_db.get(Usuario, codigo_usuario)
            if usuario is not None:
                if novo_login:
                    # So um login de verdade (sessao nova) conta; renovacao nao.
                    usuario.total_logins = (usuario.total_logins or 0) + 1
                usuario.status_online = True
                usuario.id_sessao_atual = id_sessao
                usuario.ultimo_acesso = agora
                if ip_origem:
                    usuario.ultimo_ip = ip_origem
                if user_agent:
                    usuario.ultimo_user_agent = user_agent
        except Exception as erro:
            logger.debug("Nao foi possivel atualizar status do usuario ao ativar sessao: %s", erro)

    @staticmethod
    def _atualizar_usuario_ao_encerrar(
        sessao_db: Any,
        codigo_usuario: int,
        id_sessao: str,
        agora: datetime,
        logout_voluntario: bool = False,
    ) -> None:
        try:
            if logout_voluntario:
                # Logout voluntario: finaliza qualquer sessao ativa remanescente e marca o usuario como offline
                sessao_db.execute(
                    update(Sessao)
                    .where(
                        Sessao.codigo_usuario == codigo_usuario,
                        Sessao.status == "ATIVA",
                    )
                    .values(
                        status="FINALIZADA",
                        encerrada_em=agora,
                        motivo_encerramento="LOGOUT_VOLUNTARIO",
                        dados_sessao=None,
                    )
                )
                usuario = sessao_db.get(Usuario, codigo_usuario)
                if usuario is not None:
                    usuario.status_online = False
                    usuario.id_sessao_atual = None
                return

            limite_atividade = agora - timedelta(minutes=10)
            outras = (
                sessao_db.execute(
                    select(func.count(Sessao.id_sessao)).where(
                        Sessao.codigo_usuario == codigo_usuario,
                        Sessao.status == "ATIVA",
                        Sessao.id_sessao != id_sessao,
                        Sessao.expira_em > agora,
                        Sessao.ultima_atividade > limite_atividade,
                    )
                ).scalar_one()
                or 0
            )
            usuario = sessao_db.get(Usuario, codigo_usuario)
            if usuario is not None:
                if outras == 0:
                    usuario.status_online = False
                    if usuario.id_sessao_atual == id_sessao:
                        usuario.id_sessao_atual = None
                elif usuario.id_sessao_atual == id_sessao:
                    proxima = (
                        sessao_db.execute(
                            select(Sessao.id_sessao)
                            .where(
                                Sessao.codigo_usuario == codigo_usuario,
                                Sessao.status == "ATIVA",
                                Sessao.id_sessao != id_sessao,
                                Sessao.expira_em > agora,
                            )
                            .order_by(Sessao.ultima_atividade.desc())
                        )
                        .scalars()
                        .first()
                    )
                    usuario.id_sessao_atual = proxima
        except Exception as erro:
            logger.debug(
                "Nao foi possivel atualizar status do usuario ao encerrar sessao: %s", erro
            )

    def motivo_encerramento(self, chave: str) -> str | None:
        """Motivo pelo qual a sessao deixou de estar ativa (None se ativa ou desconhecida)."""

        if not self._eh_chave_sessao(chave):
            return None
        with self._banco.leitura() as sessao_db:
            registro = sessao_db.execute(
                select(Sessao.status, Sessao.motivo_encerramento).where(
                    Sessao.id_sessao == self._limpar_chave(chave)
                )
            ).first()
        if registro is None or registro[0] == "ATIVA":
            return None
        return registro[1]

    def obter(self, chave: str) -> bytes | None:
        """Le o payload da sessao; se expirada, marca timeout e registra evento."""

        if not self._eh_chave_sessao(chave):
            return None

        id_sessao = self._limpar_chave(chave)
        agora = agora_local()

        try:
            with self._banco.unidade_trabalho() as sessao_db:
                registro = sessao_db.execute(
                    select(Sessao).where(Sessao.id_sessao == id_sessao)
                ).scalar_one_or_none()

                if registro is None:
                    return None

                if registro.status != "ATIVA":
                    return None

                # Verificacao de expiracao por inatividade
                if registro.expira_em < agora:
                    registro.status = "EXPIRADA"
                    registro.encerrada_em = agora
                    registro.motivo_encerramento = "TIMEOUT_INATIVIDADE"

                    if registro.codigo_usuario is not None:
                        evento = EventoSessao(
                            id_sessao=id_sessao,
                            id_sistema=registro.id_sistema,
                            codigo_usuario=registro.codigo_usuario,
                            login_usuario=registro.login_usuario,
                            tipo_evento="TIMEOUT",
                            ip_origem=registro.ip_origem,
                            user_agent=registro.user_agent,
                            data_hora=agora,
                            detalhes="Sessao expirada por inatividade (> 10 min sem acao na tela).",
                        )
                        sessao_db.add(evento)
                        self._atualizar_usuario_ao_encerrar(
                            sessao_db, registro.codigo_usuario, id_sessao, agora
                        )
                    sessao_db.commit()
                    return None

                if not registro.dados_sessao:
                    return None

                return registro.dados_sessao.encode("utf-8")
        except Exception as erro:
            logger.error("Erro ao obter sessao PostgreSQL: %s", erro)
            return None

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        """Persiste ou renova a sessao no PostgreSQL."""

        if not self._eh_chave_sessao(chave):
            return

        id_sessao = self._limpar_chave(chave)
        agora = agora_local()
        expira_em = agora + timedelta(seconds=max(ttl_segundos, 1))

        ip_origem: str | None = None
        user_agent: str | None = None
        id_sistema: int | None = None
        codigo_usuario: int | None = None
        login_usuario: str | None = None

        if has_request_context():
            # `remote_addr` ja traz o IP real quando o proxy e confiavel (Waitress/ProxyFix). Ler
            # X-Forwarded-For direto pegaria o 1o item, que o proprio cliente pode forjar.
            ip_origem = (request.remote_addr or "")[:50] or None
            # `bool(request.user_agent)` e False no Werkzeug (so olha o navegador reconhecido).
            user_agent = (request.headers.get("User-Agent") or "")[:500] or None
            with current_app.app_context():
                id_sistema = current_app.config.get("LUFT_SISTEMA_ID")

        # Extrair dados de identidade da sessao se disponivel
        try:
            envelope = json.loads(valor.decode("utf-8"))
            dados = envelope.get("dados", {})
            usuario_info = dados.get("luftbase_usuario")
            if isinstance(usuario_info, dict):
                codigo_usuario = usuario_info.get("id_usuario") or usuario_info.get(
                    "codigo_usuario"
                )
                login_usuario = usuario_info.get("login") or usuario_info.get("login_usuario")
            # `_user_id` sozinho NAO prova autenticacao: o Flask-Login o grava ate quando o
            # carregador nao reconhece o usuario. So `luftbase_usuario` liga a sessao a alguem.
        except Exception:
            pass

        dados_texto = valor.decode("utf-8")

        try:
            with self._banco.unidade_trabalho() as sessao_db:
                # Validar se o usuario existe no PostgreSQL para nao violar a FK fk_core_sessao_usuario
                if codigo_usuario is not None:
                    try:
                        usuario_existe = sessao_db.get(Usuario, codigo_usuario) is not None
                    except Exception:
                        usuario_existe = True
                    if not usuario_existe:
                        codigo_usuario = None
                        login_usuario = None

                registro = sessao_db.execute(
                    select(Sessao).where(Sessao.id_sessao == id_sessao)
                ).scalar_one_or_none()

                if registro is not None and registro.status != "ATIVA":
                    # Sessao ja encerrada (logout, expirada ou revogada): uma gravacao tardia de
                    # outra aba/requisicao em segundo plano NAO pode reativa-la nem devolver o
                    # usuario ao estado online. Um novo login rotaciona o id (sessao nova).
                    logger.debug(
                        "Gravacao ignorada: a sessao %s esta %s.", id_sessao, registro.status
                    )
                    return

                if registro is not None:
                    # Se a sessao legada apontava para um usuario ausente em tb_usuario, sanitizar
                    if registro.codigo_usuario is not None:
                        try:
                            reg_usuario_existe = (
                                sessao_db.get(Usuario, registro.codigo_usuario) is not None
                            )
                        except Exception:
                            reg_usuario_existe = True
                        if not reg_usuario_existe:
                            registro.codigo_usuario = None

                    # Renovacao de sessao existente (usuario mexeu na tela)
                    registro.dados_sessao = dados_texto
                    registro.ultima_atividade = agora
                    registro.expira_em = expira_em
                    registro.total_renovacoes += 1
                    registro.status = "ATIVA"
                    registro.encerrada_em = None
                    registro.motivo_encerramento = None

                    houve_login = False
                    if codigo_usuario is not None and (
                        registro.codigo_usuario is None or registro.codigo_usuario != codigo_usuario
                    ):
                        registro.codigo_usuario = codigo_usuario
                        houve_login = True
                    if login_usuario is not None and (
                        registro.login_usuario is None or registro.login_usuario != login_usuario
                    ):
                        registro.login_usuario = login_usuario[:100]
                    if ip_origem is not None:
                        registro.ip_origem = ip_origem
                    if user_agent is not None:
                        registro.user_agent = user_agent
                    if id_sistema is not None and registro.id_sistema is None:
                        registro.id_sistema = id_sistema

                    if houve_login:
                        evento = EventoSessao(
                            id_sessao=id_sessao,
                            id_sistema=registro.id_sistema,
                            codigo_usuario=registro.codigo_usuario,
                            login_usuario=registro.login_usuario,
                            tipo_evento="INICIO",
                            ip_origem=registro.ip_origem,
                            user_agent=registro.user_agent,
                            data_hora=agora,
                            detalhes="Login autenticado do usuario.",
                        )
                        sessao_db.add(evento)
                    elif registro.codigo_usuario is not None and (
                        registro.total_renovacoes == 1 or registro.total_renovacoes % 10 == 0
                    ):
                        # Evento esparso de renovacao a cada 10 renovacoes para nao inflar a tabela
                        evento = EventoSessao(
                            id_sessao=id_sessao,
                            id_sistema=registro.id_sistema,
                            codigo_usuario=registro.codigo_usuario,
                            login_usuario=registro.login_usuario,
                            tipo_evento="RENOVACAO",
                            ip_origem=registro.ip_origem,
                            user_agent=registro.user_agent,
                            data_hora=agora,
                            detalhes=(
                                "Renovacao por atividade na tela "
                                f"(total={registro.total_renovacoes})."
                            ),
                        )
                        sessao_db.add(evento)

                    if registro.codigo_usuario is not None:
                        self._atualizar_usuario_ao_ativar(
                            sessao_db,
                            registro.codigo_usuario,
                            id_sessao,
                            agora,
                            registro.ip_origem,
                            registro.user_agent,
                            novo_login=houve_login,
                        )
                else:
                    # Nova sessao
                    novo = Sessao(
                        id_sessao=id_sessao,
                        id_sistema=id_sistema,
                        codigo_usuario=codigo_usuario,
                        login_usuario=login_usuario[:100] if login_usuario else None,
                        ip_origem=ip_origem,
                        user_agent=user_agent,
                        dados_sessao=dados_texto,
                        status="ATIVA",
                        total_renovacoes=0,
                        criada_em=agora,
                        ultima_atividade=agora,
                        expira_em=expira_em,
                    )
                    sessao_db.add(novo)
                    sessao_db.flush()

                    if codigo_usuario is not None:
                        evento = EventoSessao(
                            id_sessao=id_sessao,
                            id_sistema=id_sistema,
                            codigo_usuario=codigo_usuario,
                            login_usuario=login_usuario[:100] if login_usuario else None,
                            tipo_evento="INICIO",
                            ip_origem=ip_origem,
                            user_agent=user_agent,
                            data_hora=agora,
                            detalhes="Inicio de sessao autenticada.",
                        )
                        sessao_db.add(evento)
                        self._atualizar_usuario_ao_ativar(
                            sessao_db,
                            codigo_usuario,
                            id_sessao,
                            agora,
                            ip_origem,
                            user_agent,
                            novo_login=True,
                        )

                sessao_db.commit()
        except Exception as erro:
            logger.error("Erro ao salvar sessao PostgreSQL: %s", erro)

    def remover(self, chave: str) -> None:
        """Encerra a sessao marcando como FINALIZADA (logout voluntario ou rotacao)."""

        if not self._eh_chave_sessao(chave):
            return

        id_sessao = self._limpar_chave(chave)
        agora = agora_local()

        try:
            with self._banco.unidade_trabalho() as sessao_db:
                registro = sessao_db.execute(
                    select(Sessao).where(Sessao.id_sessao == id_sessao)
                ).scalar_one_or_none()

                if registro is not None:
                    if registro.codigo_usuario is not None:
                        registro.status = "FINALIZADA"
                        registro.encerrada_em = agora
                        registro.motivo_encerramento = "LOGOUT_VOLUNTARIO"
                        registro.dados_sessao = None

                        evento = EventoSessao(
                            id_sessao=id_sessao,
                            id_sistema=registro.id_sistema,
                            codigo_usuario=registro.codigo_usuario,
                            login_usuario=registro.login_usuario,
                            tipo_evento="LOGOUT",
                            ip_origem=registro.ip_origem,
                            user_agent=registro.user_agent,
                            data_hora=agora,
                            detalhes="Logout voluntario do usuario.",
                        )
                        sessao_db.add(evento)
                        self._atualizar_usuario_ao_encerrar(
                            sessao_db,
                            registro.codigo_usuario,
                            id_sessao,
                            agora,
                            logout_voluntario=True,
                        )
                    else:
                        registro.status = "FINALIZADA"
                        registro.encerrada_em = agora
                        registro.motivo_encerramento = "ROTACAO_SESSAO"
                        registro.dados_sessao = None

                    sessao_db.commit()
        except Exception as erro:
            logger.error("Erro ao remover/encerrar sessao PostgreSQL: %s", erro)

    def verificar_saude(self) -> bool:
        """Verifica a conectividade com o banco core."""

        try:
            with self._banco.unidade_trabalho() as sessao_db:
                sessao_db.execute(select(func.now()))
                return True
        except Exception:
            return False

    def listar_usuarios_online(self, id_sistema: int | None = None) -> list[dict[str, Any]]:
        """Devolve usuarios com sessao ativa e nao expirada."""

        agora = agora_local()
        consulta = select(Sessao).where(
            Sessao.status == "ATIVA",
            Sessao.codigo_usuario.is_not(None),
            Sessao.expira_em > agora,
        )
        if id_sistema is not None:
            consulta = consulta.where(Sessao.id_sistema == id_sistema)

        consulta = consulta.order_by(Sessao.ultima_atividade.desc())

        with self._banco.unidade_trabalho() as sessao_db:
            linhas = sessao_db.execute(consulta).scalars().all()
            return [
                {
                    "id_sessao": s.id_sessao,
                    "id_sistema": s.id_sistema,
                    "codigo_usuario": s.codigo_usuario,
                    "login_usuario": s.login_usuario,
                    "ip_origem": s.ip_origem,
                    "user_agent": s.user_agent,
                    "criada_em": s.criada_em.isoformat() if s.criada_em else None,
                    "ultima_atividade": (
                        s.ultima_atividade.isoformat() if s.ultima_atividade else None
                    ),
                    "expira_em": s.expira_em.isoformat() if s.expira_em else None,
                    "total_renovacoes": s.total_renovacoes,
                }
                for s in linhas
            ]

    def contar_online(self, id_sistema: int | None = None) -> int:
        """Contagem instantanea de sessoes ativas."""

        agora = agora_local()
        consulta = select(func.count(Sessao.id_sessao)).where(
            Sessao.status == "ATIVA",
            Sessao.codigo_usuario.is_not(None),
            Sessao.expira_em > agora,
        )
        if id_sistema is not None:
            consulta = consulta.where(Sessao.id_sistema == id_sistema)

        with self._banco.unidade_trabalho() as sessao_db:
            return int(sessao_db.execute(consulta).scalar_one() or 0)

    def revogar_sessao(self, id_sessao: str, motivo: str = "REVOGADA_ADMIN") -> bool:
        """Revoga forcadamente uma sessao ativa."""

        agora = agora_local()
        with self._banco.unidade_trabalho() as sessao_db:
            registro = sessao_db.execute(
                select(Sessao).where(Sessao.id_sessao == id_sessao)
            ).scalar_one_or_none()
            if registro is None or registro.status != "ATIVA":
                return False

            registro.status = "REVOGADA"
            registro.encerrada_em = agora
            registro.motivo_encerramento = motivo
            registro.dados_sessao = None

            evento = EventoSessao(
                id_sessao=id_sessao,
                id_sistema=registro.id_sistema,
                codigo_usuario=registro.codigo_usuario,
                login_usuario=registro.login_usuario,
                tipo_evento="REVOGACAO",
                ip_origem=registro.ip_origem,
                user_agent=registro.user_agent,
                data_hora=agora,
                detalhes=f"Sessao revogada forcadamente: {motivo}.",
            )
            sessao_db.add(evento)
            if registro.codigo_usuario is not None:
                self._atualizar_usuario_ao_encerrar(
                    sessao_db, registro.codigo_usuario, id_sessao, agora
                )
            sessao_db.commit()
            return True
