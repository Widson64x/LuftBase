"""Módulo de autenticação e gerenciamento de sessão corporativa do LuftBase."""

from __future__ import annotations

import logging
from hmac import compare_digest
from urllib.parse import urlsplit

from flask import Blueprint, abort, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from luftbase.identidade import encerrar_sessao_global, iniciar_sessao_usuario
from luftbase.nucleo.excecoes import ErroAutenticacao
from luftbase.observabilidade import EventoDominio, SeveridadeAuditoria
from luftbase.plataforma import obter_luftbase

AutenticacaoBp = Blueprint("Autenticacao", __name__)


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
            try:
                estado.auditoria.registrar_evento(
                    EventoDominio(
                        acao="LOGIN_FALHA",
                        recurso="AUTENTICACAO",
                        descricao=f"Tentativa de login falhou para '{login_informado}'.",
                        severidade=SeveridadeAuditoria.MEDIA,
                        login_usuario=login_informado or "anonimo",
                    )
                )
            except Exception:
                pass
        else:
            iniciar_sessao_usuario(usuario)
            try:
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
            except Exception:
                pass
            return redirect(destino or f"{request.script_root}/")

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
    try:
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
    except Exception:
        pass
    if codigo_usuario:
        try:
            estado.usuarios_core.registrar_fim_sessao(
                codigo_usuario=codigo_usuario,
                id_sessao="",
                remover_status_online=True,
            )
        except Exception:
            pass
    encerrar_sessao_global()
    return redirect(url_for("Autenticacao.login"))


sair = logout

__all__ = ["AutenticacaoBp", "_validar_csrf", "login", "logout", "sair"]
