"""Sessao Flask compartilhada, assinada e revogavel em armazenamento externo."""

from __future__ import annotations

import contextlib
import hashlib
import json
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol

from flask import Flask, Request, Response, current_app, session
from flask.sessions import SessionInterface, SessionMixin
from flask_login import login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from werkzeug.datastructures import CallbackDict

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroSessao

_CHAVE_USUARIO = "luftbase_usuario"


class ArmazenamentoSessoes(Protocol):
    """Persistencia minima exigida pela interface de sessao."""

    def obter(self, chave: str) -> bytes | None:
        """Le o payload bruto de uma sessao."""

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        """Salva o payload com expiracao obrigatoria."""

    def remover(self, chave: str) -> None:
        """Revoga definitivamente a chave informada."""

    def verificar_saude(self) -> bool:
        """Confirma disponibilidade sem revelar detalhes da conexao."""


class SessaoServidor(CallbackDict[str, Any], SessionMixin):
    """Sessao que transporta no navegador apenas um identificador assinado."""

    def __init__(
        self,
        dados: Mapping[str, Any] | None = None,
        *,
        identificador: str,
        nova: bool,
    ) -> None:
        def alterar(_: object) -> None:
            self.modified = True

        super().__init__(dados, alterar)
        self.identificador = identificador
        self.new = nova
        self.modified = False
        self.permanent = True


class InterfaceSessaoCompartilhada(SessionInterface):
    """Implementa sessoes server-side em JSON com cookie assinado e opaco."""

    session_class = SessaoServidor

    def __init__(
        self,
        armazenamento: ArmazenamentoSessoes,
        chave_assinatura: str,
        *,
        prefixo: str = "luft:sessao:",
    ) -> None:
        if len(chave_assinatura) < 32:
            raise ErroSessao("A chave de assinatura da sessao deve possuir ao menos 32 caracteres.")
        if not prefixo or any(caractere.isspace() for caractere in prefixo):
            raise ErroSessao("O prefixo de sessao e invalido.")
        self._armazenamento = armazenamento
        self._chave_assinatura = chave_assinatura
        self._prefixo = prefixo

    def _assinador(self) -> TimestampSigner:
        return TimestampSigner(
            self._chave_assinatura,
            salt="luftbase-sessao-v1",
            key_derivation="hmac",
            digest_method=hashlib.sha256,
        )

    @staticmethod
    def _novo_identificador() -> str:
        return secrets.token_urlsafe(32)

    def _chave(self, identificador: str) -> str:
        return f"{self._prefixo}{identificador}"

    def _assinar(self, identificador: str) -> str:
        return self._assinador().sign(identificador.encode("ascii")).decode("ascii")

    def _validar_cookie(self, valor: str, ttl_segundos: int) -> str | None:
        try:
            identificador = self._assinador().unsign(valor, max_age=ttl_segundos).decode("ascii")
        except (BadSignature, SignatureExpired, UnicodeDecodeError):
            return None
        if len(identificador) > 128 or not identificador:
            return None
        return identificador

    def open_session(self, app: Flask, request: Request) -> SessaoServidor:
        """Carrega o JSON externo ou inicia uma sessao vazia em falha segura."""

        ttl = max(int(app.permanent_session_lifetime.total_seconds()), 1)
        valor_cookie = request.cookies.get(self.get_cookie_name(app))
        identificador = self._validar_cookie(valor_cookie, ttl) if valor_cookie else None
        if identificador is None:
            return self.session_class(identificador=self._novo_identificador(), nova=True)
        try:
            bruto = self._armazenamento.obter(self._chave(identificador))
            if bruto is None:
                return self.session_class(identificador=self._novo_identificador(), nova=True)
            envelope = json.loads(bruto.decode("utf-8"))
            if envelope.get("versao") != 1 or not isinstance(envelope.get("dados"), dict):
                raise ValueError("Envelope invalido")

            # Valida inatividade estrita baseada na ultima acao do usuario
            salva_em_str = envelope.get("salva_em")
            if salva_em_str:
                with contextlib.suppress(Exception):
                    salva_em = datetime.fromisoformat(salva_em_str)
                    if (datetime.now(UTC) - salva_em).total_seconds() > ttl:
                        self._armazenamento.remover(self._chave(identificador))
                        return self.session_class(
                            identificador=self._novo_identificador(),
                            nova=True,
                        )

            sessao = self.session_class(
                envelope["dados"],
                identificador=identificador,
                nova=False,
            )
            sessao.permanent = True
            return sessao
        except Exception as erro:
            raise ErroSessao("Nao foi possivel carregar a sessao compartilhada.") from erro

    def save_session(self, app: Flask, sessao: SessionMixin, response: Response) -> None:
        """Persiste JSON com TTL e atualiza somente o cookie opaco."""

        if not isinstance(sessao, SessaoServidor):
            raise ErroSessao("O Flask recebeu um tipo de sessao incompativel.")
        nome_cookie = self.get_cookie_name(app)
        chave = self._chave(sessao.identificador)
        if not sessao:
            self._armazenamento.remover(chave)
            response.delete_cookie(
                nome_cookie,
                domain=self.get_cookie_domain(app),
                path=self.get_cookie_path(app),
            )
            return

        # Nao renova inatividade se a requisicao for polling em segundo plano (ex: notificacoes)
        eh_segundo_plano = False
        try:
            from flask import request as req

            eh_segundo_plano = bool(
                req.headers.get("X-Background-Request") == "1"
                or req.path.endswith("/contagem")
                or req.path.endswith("/eventos")
                or req.path.endswith("/_luftbase/mensagens")
                or req.path.startswith("/_luftbase/static/")
            )
        except RuntimeError:
            pass

        if eh_segundo_plano and not sessao.modified and not sessao.new:
            # Requisicao automatica em segundo plano nao renova o tempo de inatividade
            return

        ttl = max(int(app.permanent_session_lifetime.total_seconds()), 1)
        envelope = {
            "versao": 1,
            "salva_em": datetime.now(UTC).isoformat(),
            "dados": dict(sessao),
        }
        try:
            bruto = json.dumps(
                envelope,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as erro:
            raise ErroSessao("A sessao contem um valor que nao pode ser serializado.") from erro
        self._armazenamento.salvar(chave, bruto, ttl)
        response.set_cookie(
            nome_cookie,
            self._assinar(sessao.identificador),
            expires=self.get_expiration_time(app, sessao),
            httponly=self.get_cookie_httponly(app),
            domain=self.get_cookie_domain(app),
            path=self.get_cookie_path(app),
            secure=self.get_cookie_secure(app),
            samesite=self.get_cookie_samesite(app),
        )

    def revogar(self, identificador: str) -> None:
        """Remove uma sessao pelo ID sem depender de requisicao ativa."""

        self._armazenamento.remover(self._chave(identificador))


def rotacionar_sessao() -> None:
    """Troca o ID apos autenticacao para impedir fixacao de sessao."""

    sessao_real = session._get_current_object()  # type: ignore[attr-defined]
    interface = current_app.session_interface
    if not isinstance(sessao_real, SessaoServidor) or not isinstance(
        interface,
        InterfaceSessaoCompartilhada,
    ):
        raise ErroSessao("A sessao compartilhada nao esta instalada nesta aplicacao.")
    interface.revogar(sessao_real.identificador)
    sessao_real.identificador = interface._novo_identificador()
    sessao_real.modified = True


def revogar_sessao_atual() -> None:
    """Revoga o ID atual e limpa todos os dados do contexto Flask."""

    sessao_real = session._get_current_object()  # type: ignore[attr-defined]
    interface = current_app.session_interface
    if isinstance(sessao_real, SessaoServidor) and isinstance(
        interface,
        InterfaceSessaoCompartilhada,
    ):
        interface.revogar(sessao_real.identificador)
    session.clear()


def carregar_usuario_sessao(identificador: str) -> UsuarioAutenticado | None:
    """Carrega o retrato serializado sem consultar banco a cada requisicao."""

    dados = session.get(_CHAVE_USUARIO)
    if not isinstance(dados, dict):
        return None
    try:
        usuario = UsuarioAutenticado.de_dict(dados)
    except ValueError:
        session.pop(_CHAVE_USUARIO, None)
        return None
    if usuario.get_id() != identificador:
        session.pop(_CHAVE_USUARIO, None)
        return None
    return usuario


def iniciar_sessao_usuario(usuario: UsuarioAutenticado) -> None:
    """Rotaciona a sessao e registra um retrato autenticado no servidor."""

    rotacionar_sessao()
    session.permanent = True
    session[_CHAVE_USUARIO] = usuario.como_dict()
    if not login_user(usuario, remember=True, fresh=True):
        session.pop(_CHAVE_USUARIO, None)
        raise ErroSessao("O usuario nao esta ativo para iniciar a sessao.")


def encerrar_sessao_global() -> None:
    """Remove a identidade e revoga a chave compartilhada por todas as aplicacoes."""

    logout_user()
    revogar_sessao_atual()
