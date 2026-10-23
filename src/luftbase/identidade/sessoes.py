"""Sessao Flask compartilhada, assinada e revogavel em armazenamento externo."""

from __future__ import annotations

import contextlib
import hashlib
import json
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from flask import Flask, Request, Response, current_app, request, session
from flask.sessions import SessionInterface, SessionMixin
from flask_login import login_user, logout_user
from itsdangerous import BadSignature, TimestampSigner
from werkzeug.datastructures import CallbackDict

from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.nucleo.excecoes import ErroSessao

_CHAVE_USUARIO = "luftbase_usuario"
# Marca a sessao de quem escolheu "Lembrar acesso": ela tolera bem mais tempo sem atividade.
CHAVE_LEMBRAR = "_lembrar"
# Guardada na sessao nova quando a anterior foi derrubada por um administrador; a tela de entrada a le.
CHAVE_AVISO_ENCERRAMENTO = "_aviso_encerramento"
MOTIVOS_COM_AVISO = frozenset({"REVOGADA_ADMIN", "BLOQUEIO_ADMIN"})
# Chaves que o Flask e o Flask-Login escrevem sozinhos, ate numa requisicao de visitante (ex.: `_fresh` a cada
# `current_user`). Sozinhas, nao dao motivo para criar uma sessao nem para trocar o cookie do navegador.
_CHAVES_INTERNAS = frozenset({"_permanent", "_fresh", "_id", "_remember", "_remember_seconds"})
# Diferenca de relogio aceita entre servidores: o carimbo do cookie e em segundos inteiros, e um servidor
# adiantado em fracao de segundo produziria cookies "do futuro" para os demais.
_TOLERANCIA_RELOGIO_SEGUNDOS = 30
# O cookie so e reenviado quando a sessao e nova, quando o id muda (login) ou quando ele ja tem esta idade:
# reenviar a cada resposta fazia uma resposta atrasada (de uma requisicao iniciada antes do login, por exemplo)
# sobrescrever o cookie novo no navegador. Vale `min(isto, ttl / 10)`, para a validade do cookie acompanhar a da sessao.
_RENOVAR_COOKIE_APOS_SEGUNDOS = 300


class ArmazenamentoSessoes(Protocol):
    """Persistencia minima exigida pela interface de sessao."""

    def obter(self, chave: str) -> bytes | None:
        """Le o payload bruto de uma sessao."""

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> bool | None:
        """Salva o payload com expiracao obrigatoria.

        `False` indica que a sessao ja estava encerrada e a gravacao foi recusada; `None` e `True` valem
        como gravada (armazenamentos que nao distinguem continuam validos).
        """

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
        # O que o navegador ja tem: id e idade (s) do cookie recebido. `None` = nao veio cookie valido.
        self.identificador_cookie: str | None = None
        self.idade_cookie: float | None = None


class InterfaceSessaoCompartilhada(SessionInterface):
    """Implementa sessoes server-side em JSON com cookie assinado e opaco."""

    session_class = SessaoServidor

    def __init__(
        self,
        armazenamento: ArmazenamentoSessoes,
        chave_assinatura: str,
        *,
        prefixo: str = "luft:sessao:",
        ttl_lembrar_segundos: int = 0,
    ) -> None:
        if len(chave_assinatura) < 32:
            raise ErroSessao("A chave de assinatura da sessao deve possuir ao menos 32 caracteres.")
        if not prefixo or any(caractere.isspace() for caractere in prefixo):
            raise ErroSessao("O prefixo de sessao e invalido.")
        self._armazenamento = armazenamento
        self._chave_assinatura = chave_assinatura
        self._prefixo = prefixo
        self._ttl_lembrar_segundos = max(int(ttl_lembrar_segundos), 0)

    def _ttl_segundos(self, app: Flask, dados: Mapping[str, Any]) -> int:
        """Validade sem atividade: a normal, ou a longa para quem marcou "Lembrar acesso"."""

        ttl = max(int(app.permanent_session_lifetime.total_seconds()), 1)
        if dados.get(CHAVE_LEMBRAR) is True:
            return max(ttl, self._ttl_lembrar_segundos)
        return ttl

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

    def _validar_cookie(self, valor: str, ttl_segundos: int) -> tuple[str, float] | None:
        """Devolve `(identificador, idade_em_segundos)` do cookie, ou `None` se ele nao vale."""

        try:
            bruto, assinado_em = self._assinador().unsign(valor, return_timestamp=True)
            identificador = bruto.decode("ascii")
        except (BadSignature, UnicodeDecodeError):
            return None
        # Idade pelo carimbo: velha demais, ou "do futuro" alem da tolerancia entre os relogios dos servidores.
        idade = (datetime.now(UTC) - assinado_em).total_seconds()
        if idade > ttl_segundos or idade < -_TOLERANCIA_RELOGIO_SEGUNDOS:
            return None
        if len(identificador) > 128 or not identificador:
            return None
        return identificador, idade

    def open_session(self, app: Flask, request: Request) -> SessaoServidor:
        """Carrega o JSON externo ou inicia uma sessao vazia em falha segura."""

        ttl = max(int(app.permanent_session_lifetime.total_seconds()), 1)
        # A assinatura so barra cookies abandonados; o prazo real de cada sessao e conferido abaixo.
        ttl_cookie = max(ttl, self._ttl_lembrar_segundos)
        valor_cookie = request.cookies.get(self.get_cookie_name(app))
        lido = self._validar_cookie(valor_cookie, ttl_cookie) if valor_cookie else None
        if lido is None:
            return self.session_class(identificador=self._novo_identificador(), nova=True)
        identificador, idade_cookie = lido
        try:
            bruto = self._armazenamento.obter(self._chave(identificador))
            if bruto is None:
                return self.session_class(
                    self._aviso_de_encerramento(identificador),
                    identificador=self._novo_identificador(),
                    nova=True,
                )
            envelope = json.loads(bruto.decode("utf-8"))
            if envelope.get("versao") != 1 or not isinstance(envelope.get("dados"), dict):
                raise ValueError("Envelope invalido")

            # Valida inatividade estrita baseada na ultima acao do usuario
            ttl = self._ttl_segundos(app, envelope["dados"])
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
            sessao.identificador_cookie = identificador
            sessao.idade_cookie = idade_cookie
            return sessao
        except Exception as erro:
            raise ErroSessao("Nao foi possivel carregar a sessao compartilhada.") from erro

    @staticmethod
    def _cookie_precisa_ser_enviado(sessao: SessaoServidor, ttl_segundos: int) -> bool:
        """So reenvia o cookie quando o navegador precisa de um novo: sessao nova, id trocado ou cookie envelhecendo."""

        if sessao.new or sessao.idade_cookie is None or sessao.identificador != sessao.identificador_cookie:
            return True
        return sessao.idade_cookie >= min(_RENOVAR_COOKIE_APOS_SEGUNDOS, ttl_segundos / 10)

    @staticmethod
    def _tem_conteudo(sessao: SessionMixin) -> bool:
        """Diz se a sessao guarda algo alem do que o Flask e o Flask-Login escrevem sozinhos."""

        return any(chave not in _CHAVES_INTERNAS for chave in sessao)

    def _aviso_de_encerramento(self, identificador: str) -> dict[str, str]:
        """Se a sessao do cookie foi derrubada por um administrador, devolve o aviso para o login.

        So roda quando o cookie e valido mas a sessao nao esta mais ativa (caminho raro). Qualquer
        falha aqui apenas deixa de avisar; nunca impede a requisicao.
        """

        consultar = getattr(self._armazenamento, "motivo_encerramento", None)
        if not callable(consultar):
            return {}
        try:
            motivo = consultar(self._chave(identificador))
        except Exception:
            return {}
        return {CHAVE_AVISO_ENCERRAMENTO: motivo} if motivo in MOTIVOS_COM_AVISO else {}

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

        # Quem chegou sem uma sessao valida (sem cookie, cookie velho de uma sessao ja trocada no login, requisicao em
        # voo de outra aba) so ganha sessao e cookie novos se a requisicao de fato guardou algo nela (ex.: o token
        # CSRF da tela de entrada). Sem isso, qualquer arquivo estatico ou chamada de API sem cookie devolvia um
        # `Set-Cookie` anonimo que, ao chegar no navegador, substituia o cookie bom e derrubava o login em TODOS os
        # sistemas (o cookie e compartilhado). Requisicao de fundo nunca cria sessao.
        if sessao.new and (eh_segundo_plano or not self._tem_conteudo(sessao)):
            return

        ttl = self._ttl_segundos(app, sessao)
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
        gravada = self._armazenamento.salvar(chave, bruto, ttl)
        if gravada is False:
            # A sessao foi encerrada enquanto esta requisicao rodava (ex.: o login trocou o id): o cookie dela nao
            # pode sobrescrever o novo no navegador.
            return
        if not self._cookie_precisa_ser_enviado(sessao, ttl):
            return
        response.set_cookie(
            nome_cookie,
            self._assinar(sessao.identificador),
            expires=datetime.now(UTC) + timedelta(seconds=ttl),
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


def iniciar_sessao_usuario(usuario: UsuarioAutenticado, *, lembrar: bool = False) -> None:
    """Rotaciona a sessao e registra um retrato autenticado no servidor.

    `lembrar=True` (checkbox "Lembrar acesso") estende a validade sem atividade para
    `LUFT_SESSAO_LEMBRAR_DIAS`, em vez de `LUFT_SESSAO_TTL_MINUTOS`.
    """

    rotacionar_sessao()
    session.permanent = True
    if lembrar:
        session[CHAVE_LEMBRAR] = True
    session[_CHAVE_USUARIO] = usuario.como_dict()
    # remember=False: a sessao vive no servidor. O cookie "lembrar" do Flask-Login sobrevivia ao
    # logout e recriava uma sessao autenticada (ver `descartar_cookie_lembrar`).
    if not login_user(usuario, remember=False, fresh=True):
        session.pop(_CHAVE_USUARIO, None)
        raise ErroSessao("O usuario nao esta ativo para iniciar a sessao.")


def encerrar_sessao_global() -> None:
    """Remove a identidade e revoga a chave compartilhada por todas as aplicacoes."""

    logout_user()
    revogar_sessao_atual()
    # revogar_sessao_atual() faz session.clear(), o que apaga a ordem que o logout_user() deixou
    # para o Flask-Login remover o cookie "lembrar". Repete-se a ordem depois da limpeza.
    session["_remember"] = "clear"


def descartar_cookie_lembrar(app: Flask) -> None:
    """Remove o cookie \"lembrar\" do Flask-Login antes que ele possa recriar uma sessao.

    O LuftBase nunca o usa (a sessao e do servidor), mas navegadores que logaram em versoes
    anteriores ainda o carregam por um ano. Com ele, a primeira requisicao depois do logout fazia o
    Flask-Login gravar `_user_id` na sessao anonima, e o usuario voltava a ficar online.
    Roda antes de qualquer outro before_request, pois qualquer acesso a `current_user` o dispararia.
    """

    nome = app.config.get("REMEMBER_COOKIE_NAME", "remember_token")

    def descartar() -> None:
        if request.cookies.get(nome) is not None:
            session["_remember"] = "clear"  # o Flask-Login ignora o cookie e o apaga na resposta

    app.before_request_funcs.setdefault(None, []).insert(0, descartar)
