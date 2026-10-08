"""Módulo de autenticação e gerenciamento de sessão corporativa do LuftBase."""

from __future__ import annotations

import contextlib
import logging
from hmac import compare_digest
from urllib.parse import urlsplit

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from luftbase.identidade import encerrar_sessao_global, iniciar_sessao_usuario
from luftbase.identidade.sessoes import CHAVE_AVISO_ENCERRAMENTO
from luftbase.nucleo.excecoes import ErroAutenticacao, ErroUsuarioBloqueado
from luftbase.observabilidade import EventoDominio, SeveridadeAuditoria
from luftbase.plataforma import obter_luftbase

AutenticacaoBp = Blueprint("Autenticacao", __name__)

# Sem o motivo interno do bloqueio: quem esta do outro lado nao precisa dele para procurar o suporte.
MENSAGEM_BLOQUEADO = "Seu acesso está bloqueado. Procure um administrador."
MENSAGENS_ENCERRAMENTO = {
    "REVOGADA_ADMIN": "Sua sessão foi encerrada por um administrador. Entre novamente.",
    "BLOQUEIO_ADMIN": MENSAGEM_BLOQUEADO,
}


def _destino_seguro(valor: str | None) -> str | None:
    """Aceita somente redirecionamento relativo para evitar Open Redirect."""

    if not valor:
        return None
    partes = urlsplit(valor)
    return valor if not partes.scheme and not partes.netloc and valor.startswith("/") else None


def _validar_csrf() -> None:
    """Valida o token CSRF contra o valor esperado na sessão."""

    esperado = session.get("luftbase_csrf")
    recebido = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not isinstance(esperado, str) or not isinstance(recebido, str):
        abort(403)
    if not compare_digest(esperado, recebido):
        abort(403)


@AutenticacaoBp.route("/login", methods=["GET", "POST"])
def login():  # type: ignore[no-untyped-def]
    """Autentica no LDAP/Active Directory e cria a sessão corporativa revogável."""

    destino = _destino_seguro(request.args.get("next") or request.form.get("next"))
    if current_user.is_authenticated:
        return redirect(destino or f"{request.script_root}/")

    erro = None
    if request.method == "POST":
        _validar_csrf()
        login_informado = (
            request.form.get("login")
            or request.form.get("usuario")
            or request.form.get("username")
            or ""
        ).strip()
        senha_informada = request.form.get("senha") or request.form.get("password") or ""

        estado = obter_luftbase()
        indisponivel = False
        try:
            usuario = estado.autenticacao.autenticar(
                login_informado,
                senha_informada,
            )
        except ErroUsuarioBloqueado:
            with contextlib.suppress(Exception):
                estado.auditoria.registrar_evento(
                    EventoDominio(
                        acao="LOGIN_BLOQUEADO",
                        recurso="AUTENTICACAO",
                        descricao=f"Login recusado: acesso de '{login_informado}' esta bloqueado.",
                        severidade=SeveridadeAuditoria.MEDIA,
                        login_usuario=login_informado or "anonimo",
                    )
                )
            return (
                render_template(
                    "luftbase/login.html", erro=MENSAGEM_BLOQUEADO, destino=destino or ""
                ),
                403,
            )
        except ErroAutenticacao:
            # Diretorio fora do ar ou lento: nao e credencial invalida nem erro 500.
            logging.getLogger("luftbase").warning(
                "Servico de autenticacao indisponivel ao autenticar '%s'.",
                login_informado,
                exc_info=True,
            )
            usuario = None
            indisponivel = True
        if indisponivel:
            erro = (
                "O serviço de autenticação está indisponível no momento. "
                "Tente novamente em instantes."
            )
            return (
                render_template("luftbase/login.html", erro=erro, destino=destino or ""),
                503,
            )
        if usuario is None:
            erro = "Usuário ou senha inválidos."
            with contextlib.suppress(Exception):
                estado.auditoria.registrar_evento(
                    EventoDominio(
                        acao="LOGIN_FALHA",
                        recurso="AUTENTICACAO",
                        descricao=f"Tentativa de login falhou para '{login_informado}'.",
                        severidade=SeveridadeAuditoria.MEDIA,
                        login_usuario=login_informado or "anonimo",
                    )
                )
        else:
            iniciar_sessao_usuario(usuario)
            with contextlib.suppress(Exception):
                estado.auditoria.registrar_evento(
                    EventoDominio(
                        acao="LOGIN_SUCESSO",
                        recurso="AUTENTICACAO",
                        descricao=f"Usuário '{usuario.login}' autenticado com sucesso.",
                        severidade=SeveridadeAuditoria.BAIXA,
                        codigo_usuario=usuario.id_usuario,
                        login_usuario=usuario.login,
                        codigo_grupo=usuario.id_grupo,
                        nome_grupo=usuario.nome_grupo,
                    )
                )
            return redirect(destino or f"{request.script_root}/")

    if erro is None:
        # Aviso gravado quando a sessao foi derrubada por um administrador (ver `InterfaceSessaoCompartilhada`).
        erro = MENSAGENS_ENCERRAMENTO.get(str(session.pop(CHAVE_AVISO_ENCERRAMENTO, "")))
    return render_template("luftbase/login.html", erro=erro, destino=destino or "")


@AutenticacaoBp.route("/logout", methods=["GET", "POST"])
@AutenticacaoBp.route("/sair", methods=["GET", "POST"])
@login_required
def logout():  # type: ignore[no-untyped-def]
    """Revoga a sessão compartilhada e redireciona para a página de login."""

    if request.method == "POST":
        _validar_csrf()
    estado = obter_luftbase()
    login_usuario = getattr(current_user, "login", None)
    codigo_usuario = getattr(current_user, "id_usuario", None)
    codigo_grupo = getattr(current_user, "id_grupo", None)
    nome_grupo = getattr(current_user, "nome_grupo", None)
    with contextlib.suppress(Exception):
        estado.auditoria.registrar_evento(
            EventoDominio(
                acao="LOGOUT",
                recurso="AUTENTICACAO",
                descricao=f"Sessão encerrada para '{login_usuario}'.",
                severidade=SeveridadeAuditoria.BAIXA,
                codigo_usuario=codigo_usuario,
                login_usuario=login_usuario,
                codigo_grupo=codigo_grupo,
                nome_grupo=nome_grupo,
            )
        )
    if codigo_usuario:
        with contextlib.suppress(Exception):
            estado.usuarios_core.registrar_fim_sessao(
                codigo_usuario=codigo_usuario,
                id_sessao="",
                remover_status_online=True,
            )
    encerrar_sessao_global()
    return redirect(url_for("Autenticacao.login"))


sair = logout

__all__ = ["AutenticacaoBp", "_validar_csrf", "login", "logout", "sair"]
