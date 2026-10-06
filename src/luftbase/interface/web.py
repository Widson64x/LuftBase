"""Integracao Flask obrigatoria do design system."""

from __future__ import annotations

import contextlib
import os
import secrets
from hmac import compare_digest
from typing import Any

from flask import Blueprint, Flask, abort, jsonify, request, session, url_for
from flask_login import current_user

from luftbase.identidade.agente_usuario import interpretar_agente
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.interface.modelos import PreferenciaTema
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema

_CHAVE_PREFERENCIA = "luftbase_preferencia_tema"
_CHAVE_CSRF = "luftbase_csrf"


def id_sessao_atual() -> str:
    """Identificador da sessao corrente (fica no objeto da sessao, nao no dicionario de dados)."""

    return str(getattr(session._get_current_object(), "identificador", "") or "")  # type: ignore[attr-defined]


def _usuario_atual() -> UsuarioAutenticado | None:
    usuario = current_user._get_current_object()
    return usuario if isinstance(usuario, UsuarioAutenticado) else None


def token_csrf() -> str:
    """Cria ou recupera o token CSRF ligado a sessao atual."""

    token = session.get(_CHAVE_CSRF)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        session[_CHAVE_CSRF] = token
    return token


def validar_csrf_requisicao() -> None:
    """Interrompe uma mutacao HTTP sem o token da sessao."""

    token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token") or ""
    if not token and request.is_json:
        dados = request.get_json(silent=True)
        if isinstance(dados, dict):
            token = str(dados.get("csrf_token") or "")
    if not isinstance(token, str) or not compare_digest(token, token_csrf()):
        abort(403, description="Token CSRF ausente ou invalido.")


def _preferencia_sessao() -> PreferenciaTema:
    dados = session.get(_CHAVE_PREFERENCIA)
    if isinstance(dados, dict):
        tema = dados.get("tema")
        modo = dados.get("modo")
        if isinstance(tema, str) and isinstance(modo, str):
            try:
                return PreferenciaTema(tema, ModoTema(modo))
            except ValueError:
                session.pop(_CHAVE_PREFERENCIA, None)
    usuario = _usuario_atual()
    if usuario is None:
        return PreferenciaTema()
    try:
        from luftbase.plataforma import obter_luftbase

        preferencia: PreferenciaTema = obter_luftbase().temas.obter_preferencia(usuario.id_usuario)
        session[_CHAVE_PREFERENCIA] = preferencia.como_dict()
        return preferencia
    except Exception:
        return PreferenciaTema()


def _estado_tema(preferencia: PreferenciaTema) -> dict[str, object]:
    """Serializa a preferencia junto do que o tema permite (modo efetivo e bloqueio)."""

    dados: dict[str, object] = dict(preferencia.como_dict())
    try:
        from luftbase.plataforma import obter_luftbase

        dados.update(obter_luftbase().temas.resolver(preferencia).como_dict())
    except Exception:
        pass
    return dados


def formatar_versao_rodape(
    tipo_versao: str | None,
    versao: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Formata o tipo de versao (ambiente) e versao para exibicao no rodape."""
    tipo_limpo = (
        str(tipo_versao).strip() if tipo_versao is not None and str(tipo_versao).strip() else None
    )
    if tipo_limpo:
        tipo_limpo = tipo_limpo.rstrip("- ").strip().upper()

    versao_limpa = str(versao).strip() if versao is not None and str(versao).strip() else None
    if versao_limpa:
        versao_limpa = versao_limpa.lstrip("- ").strip()
        if (
            versao_limpa
            and not versao_limpa.lower().startswith("v")
            and any(c.isdigit() for c in versao_limpa)
        ):
            versao_limpa = f"v{versao_limpa}"

    if tipo_limpo and versao_limpa:
        texto_completo = f"{tipo_limpo} - {versao_limpa}"
    elif tipo_limpo:
        texto_completo = tipo_limpo
    elif versao_limpa:
        texto_completo = versao_limpa
    else:
        texto_completo = None

    return tipo_limpo, versao_limpa, texto_completo


def registrar_interface_web(app: Flask) -> None:
    """Registra assets, contexto e preferencia sem flags de desativacao."""

    bp = Blueprint(
        "luftbase_interface",
        __name__,
        url_prefix="/_luftbase",
        static_folder="static",
        static_url_path="/static",
        template_folder="templates",
    )

    @bp.get("/interface/preferencia")
    def obter_preferencia():  # type: ignore[no-untyped-def]
        if _usuario_atual() is None:
            abort(401)
        return jsonify(_estado_tema(_preferencia_sessao()))

    @bp.put("/interface/preferencia")
    def alterar_preferencia():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        validar_csrf_requisicao()
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            abort(400, description="Corpo JSON obrigatorio.")
        tema = dados.get("tema")
        modo = dados.get("modo")
        if not isinstance(tema, str) or not isinstance(modo, str):
            abort(400, description="tema e modo sao obrigatorios.")
        from luftbase.plataforma import obter_luftbase

        try:
            preferencia = obter_luftbase().temas.alterar_preferencia(
                usuario.id_usuario,
                tema,
                modo,
            )
        except ErroConfiguracao as erro:
            abort(400, description=str(erro))
        session[_CHAVE_PREFERENCIA] = preferencia.como_dict()
        return jsonify(_estado_tema(preferencia))

    @bp.get("/perfil")
    def obter_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        dados = repo.obter_dados_perfil(usuario.id_usuario)
        if dados is None:
            return jsonify(
                {
                    "codigo_usuario": usuario.id_usuario,
                    "login_usuario": usuario.login,
                    "nome_usuario": usuario.nome_completo,
                    "email_usuario": usuario.email,
                    "sigla_usuariogrupo": usuario.nome_grupo,
                    "foto_perfil": usuario.foto_perfil,
                    "status_online": True,
                    "cargo_usuario": usuario.cargo,
                    "departamento_usuario": usuario.departamento,
                    "telefone_usuario": usuario.telefone,
                    "celular_usuario": usuario.celular,
                    "unidade_filial": usuario.unidade_filial,
                    "tema_preferido": usuario.tema_preferido,
                    "modo_tema": usuario.modo_tema,
                    "idioma": usuario.idioma,
                }
            )
        return jsonify(dados)

    @bp.post("/perfil")
    def atualizar_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        validar_csrf_requisicao()
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            abort(400, description="Corpo JSON obrigatorio.")

        # ATENCAO: codigo_usuario e login_usuario sao ESTRITAMENTE IMUTAVEIS
        nome_usuario = dados.get("nome_usuario")
        telefone_usuario = dados.get("telefone_usuario")
        celular_usuario = dados.get("celular_usuario")
        cargo_usuario = dados.get("cargo_usuario")
        departamento_usuario = dados.get("departamento_usuario")
        unidade_filial = dados.get("unidade_filial")
        tema_preferido = dados.get("tema_preferido")
        modo_tema = dados.get("modo_tema")
        idioma = dados.get("idioma")

        from luftbase.plataforma import obter_luftbase

        temas = obter_luftbase().temas
        if tema_preferido is not None and temas.registro.obter(str(tema_preferido).strip()) is None:
            abort(400, description="Tema nao registrado.")
        if modo_tema is not None:
            try:
                ModoTema(str(modo_tema).strip().upper())
            except ValueError:
                abort(400, description="Modo deve ser CLARO, ESCURO ou SISTEMA.")

        repo = obter_luftbase().usuarios_core
        reg = repo.atualizar_perfil(
            codigo_usuario=usuario.id_usuario,
            nome_usuario=str(nome_usuario).strip() if nome_usuario is not None else None,
            telefone_usuario=str(telefone_usuario).strip()
            if telefone_usuario is not None
            else None,
            celular_usuario=str(celular_usuario).strip() if celular_usuario is not None else None,
            cargo_usuario=str(cargo_usuario).strip() if cargo_usuario is not None else None,
            departamento_usuario=str(departamento_usuario).strip()
            if departamento_usuario is not None
            else None,
            unidade_filial=str(unidade_filial).strip() if unidade_filial is not None else None,
            tema_preferido=str(tema_preferido).strip() if tema_preferido is not None else None,
            modo_tema=str(modo_tema).strip().upper() if modo_tema is not None else None,
            idioma=str(idioma).strip() if idioma is not None else None,
        )

        novo_nome = (
            reg.get("nome_usuario")
            if reg
            else (str(nome_usuario).strip() if nome_usuario else usuario.nome_completo)
        )
        novo_usuario = UsuarioAutenticado(
            id_usuario=usuario.id_usuario,
            login=usuario.login,
            nome_completo=novo_nome,
            email=usuario.email,
            id_grupo=usuario.id_grupo,
            nome_grupo=usuario.nome_grupo,
            permissoes=usuario.permissoes,
            foto_perfil=reg.get("foto_perfil") if reg else usuario.foto_perfil,
            status_online=True,
            cargo=reg.get("cargo_usuario") if reg else usuario.cargo,
            departamento=reg.get("departamento_usuario") if reg else usuario.departamento,
            telefone=reg.get("telefone_usuario") if reg else usuario.telefone,
            celular=reg.get("celular_usuario") if reg else usuario.celular,
            unidade_filial=reg.get("unidade_filial") if reg else usuario.unidade_filial,
            tema_preferido=reg.get("tema_preferido") if reg else usuario.tema_preferido,
            modo_tema=reg.get("modo_tema") if reg else usuario.modo_tema,
            idioma=reg.get("idioma") if reg else usuario.idioma,
        )
        session["luftbase_usuario"] = novo_usuario.como_dict()

        if tema_preferido or modo_tema:
            session[_CHAVE_PREFERENCIA] = {
                "tema": novo_usuario.tema_preferido,
                "modo": novo_usuario.modo_tema,
            }

        return jsonify(
            {
                "status": "success",
                "mensagem": "Perfil corporativo atualizado com sucesso!",
                "usuario": {
                    "codigo_usuario": usuario.id_usuario,
                    "login_usuario": usuario.login,
                    "nome_usuario": novo_usuario.nome_completo,
                    "cargo_usuario": novo_usuario.cargo,
                    "departamento_usuario": novo_usuario.departamento,
                    "telefone_usuario": novo_usuario.telefone,
                    "celular_usuario": novo_usuario.celular,
                    "tema_preferido": novo_usuario.tema_preferido,
                    "modo_tema": novo_usuario.modo_tema,
                    "idioma": novo_usuario.idioma,
                },
            }
        )

    @bp.post("/perfil/foto")
    def atualizar_foto_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        validar_csrf_requisicao()

        foto_data = None
        if request.is_json:
            corpo = request.get_json(silent=True) or {}
            foto_data = corpo.get("foto")
        elif "foto" in request.files:
            import base64

            arquivo = request.files["foto"]
            if arquivo and arquivo.filename:
                mime = arquivo.mimetype or "image/png"
                conteudo = arquivo.read()
                if len(conteudo) > 4 * 1024 * 1024:
                    abort(400, description="A imagem deve ter no maximo 4MB.")
                b64 = base64.b64encode(conteudo).decode("ascii")
                foto_data = f"data:{mime};base64,{b64}"

        if not isinstance(foto_data, str) or not foto_data.startswith("data:image/"):
            abort(400, description="Formato de imagem invalido.")

        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        repo.atualizar_foto_perfil(usuario.id_usuario, foto_data)

        dados_sessao = session.get("luftbase_usuario")
        if isinstance(dados_sessao, dict):
            dados_sessao["foto_perfil"] = foto_data
            session["luftbase_usuario"] = dados_sessao
            session.modified = True

        return jsonify(
            {
                "status": "success",
                "mensagem": "Foto de perfil atualizada com sucesso!",
                "foto_perfil": foto_data,
            }
        )

    @bp.delete("/perfil/foto")
    def remover_foto_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        validar_csrf_requisicao()

        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        repo.atualizar_foto_perfil(usuario.id_usuario, None)

        dados_sessao = session.get("luftbase_usuario")
        if isinstance(dados_sessao, dict):
            dados_sessao["foto_perfil"] = None
            session["luftbase_usuario"] = dados_sessao
            session.modified = True

        return jsonify(
            {
                "status": "success",
                "mensagem": "Foto de perfil removida com sucesso.",
            }
        )

    @bp.get("/perfil/sessoes")
    def listar_sessoes_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        sessoes = repo.listar_sessoes_usuario(usuario.id_usuario)
        id_atual = id_sessao_atual()

        for s in sessoes:
            s.update(interpretar_agente(s.get("user_agent")))
            s["is_atual"] = s["id_sessao"] == id_atual
            raw_id = s["id_sessao"]
            s["id_exibicao"] = f"sess_{raw_id[:6]}...{raw_id[-4:]}" if len(raw_id) > 12 else raw_id

        return jsonify(
            {
                "status": "success",
                "sessoes": sessoes,
                "total_ativas": len(sessoes),
            }
        )

    @bp.get("/perfil/sessoes/historico")
    def historico_sessoes_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        itens = repo.listar_historico_sessoes(usuario.id_usuario, limite=30)
        id_atual = id_sessao_atual()
        for s in itens:
            s.update(interpretar_agente(s.get("user_agent")))
            s["is_atual"] = s["id_sessao"] == id_atual
            s.pop("id_sessao", None)
        return jsonify({"status": "success", "historico": itens})

    @bp.post("/perfil/sessoes/revogar-outras")
    def revogar_outras_sessoes_perfil():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        if usuario is None:
            abort(401)
        validar_csrf_requisicao()
        id_atual = id_sessao_atual()
        from luftbase.plataforma import obter_luftbase

        repo = obter_luftbase().usuarios_core
        qtd = repo.revogar_outras_sessoes(usuario.id_usuario, id_atual)
        return jsonify(
            {
                "status": "success",
                "mensagem": f"{qtd} outras sessoes foram revogadas com sucesso.",
                "revogadas": qtd,
            }
        )

    def responder_mensagens():  # type: ignore[no-untyped-def]
        if request.method == "GET":
            from luftbase.web.respostas import consumir_flashes

            comandos = [*session.pop("_luftbase_mensagens_pendentes", []), *consumir_flashes()]
            usuario = _usuario_atual()
            if usuario is not None:
                with contextlib.suppress(Exception):
                    from luftbase.plataforma import obter_luftbase

                    obter_luftbase().usuarios_core.atualizar_presenca(
                        usuario.id_usuario,
                        id_sessao=id_sessao_atual() or None,
                    )
            return jsonify(
                {
                    "status": "success",
                    "situacao": "sucesso",
                    "comandos": comandos,
                    "messages": comandos,
                    "status_online": True,
                }
            )
        payload = request.get_json(silent=True) or {}
        acao = str(payload.get("acao") or payload.get("action") or "").strip().lower()
        if acao in {"iniciar_operacao", "start_operation"}:
            id_operacao = secrets.token_hex(8)
            return jsonify(
                {
                    "status": "success",
                    "situacao": "sucesso",
                    "id_operacao": id_operacao,
                    "operation_id": id_operacao,
                }
            )
        if acao in {"finalizar_operacao", "finish_operation"}:
            return jsonify(
                {
                    "status": "success",
                    "situacao": "sucesso",
                    "finalizada": True,
                    "finished": True,
                }
            )
        return jsonify({"status": "success", "situacao": "sucesso"})

    def contagem_notificacoes():  # type: ignore[no-untyped-def]
        try:
            usuario = _usuario_atual()
            if usuario is None:
                return jsonify({"status": "success", "contagem": 0})
            from luftbase.plataforma import obter_luftbase

            pagina = obter_luftbase().notificacoes.listar_para_usuario(
                usuario.id_usuario,
                usuario.id_grupo,
                cursor=None,
                limite=100,
                apenas_nao_lidas=True,
            )
            return jsonify({"status": "success", "contagem": len(pagina.itens)})
        except Exception:
            return jsonify({"status": "success", "contagem": 0})

    bp.add_url_rule(
        "/mensagens",
        endpoint="mensagens",
        view_func=responder_mensagens,
        methods=["GET", "POST"],
    )
    bp.add_url_rule(
        "/notificacoes/contagem",
        endpoint="notificacoes_contagem",
        view_func=contagem_notificacoes,
        methods=["GET"],
    )

    app.register_blueprint(bp)

    bp_luftbase = Blueprint(
        "luftbase",
        __name__,
        url_prefix="/_luftbase_compat",
        static_folder="static",
        static_url_path="/static",
        template_folder="templates",
    )
    app.register_blueprint(bp_luftbase)

    @app.context_processor
    def contexto_interface() -> dict[str, Any]:
        from luftbase.plataforma import obter_luftbase

        preferencia = _preferencia_sessao()
        estado = obter_luftbase()
        tema_resolvido = (
            estado.temas.resolver(preferencia) if estado and hasattr(estado, "temas") else None
        )
        manifesto = tema_resolvido.manifesto if tema_resolvido else None
        modo_efetivo = (
            tema_resolvido.modo_efetivo.value.lower()
            if tema_resolvido
            else preferencia.modo.value.lower()
        )
        modos_suportados = (
            ",".join(sorted(m.value.lower() for m in manifesto.modos))
            if manifesto
            else "claro,escuro"
        )
        temas_disponiveis = (
            estado.temas.registro.listar() if estado and hasattr(estado, "temas") else ()
        )

        temas_catalogo = [
            {
                "id": t.identificador,
                "nome": t.nome,
                "descricao": t.descricao,
                "modos": sorted(m.value.lower() for m in t.modos),
                "cores": list(t.cores_previa),
            }
            for t in temas_disponiveis
        ]

        ambiente_valor = (
            app.config.get("LUFT_AMBIENTE")
            or app.config.get("APP_ENV")
            or (
                estado.configuracao.aplicacao.ambiente.value
                if estado and getattr(estado, "configuracao", None)
                else None
            )
            or os.getenv("LUFT_AMBIENTE")
            or os.getenv("APP_ENV")
        )
        versao_valor = (
            app.config.get("LUFT_APLICACAO_VERSAO")
            or app.config.get("APP_VERSION")
            or (
                estado.configuracao.aplicacao.versao
                if estado and getattr(estado, "configuracao", None)
                else None
            )
            or os.getenv("LUFT_APLICACAO_VERSAO")
            or os.getenv("APP_VERSION")
        )
        tipo_versao, versao_app, texto_rodape = formatar_versao_rodape(ambiente_valor, versao_valor)

        url_changelog = None
        if "LuftPublicacoes.listar_atualizacoes" in app.view_functions:
            with contextlib.suppress(Exception):
                url_changelog = url_for("LuftPublicacoes.listar_atualizacoes")

        url_busca = ""
        if "luftbase_busca.pesquisar" in app.view_functions:
            with contextlib.suppress(Exception):
                url_busca = url_for("luftbase_busca.pesquisar")

        usuario = _usuario_atual()
        usuario_foto = getattr(usuario, "foto_perfil", None) if usuario else None
        if (
            usuario
            and not usuario_foto
            and hasattr(estado, "usuarios_core")
            and estado.usuarios_core
        ):
            with contextlib.suppress(Exception):
                reg_usr = estado.usuarios_core.obter_por_codigo(usuario.id_usuario)
                if reg_usr and reg_usr.foto_perfil:
                    usuario_foto = reg_usr.foto_perfil
                    dados_sessao = session.get("luftbase_usuario")
                    if isinstance(dados_sessao, dict):
                        dados_sessao["foto_perfil"] = usuario_foto
                        session["luftbase_usuario"] = dados_sessao
                        session.modified = True

        return {
            "luft_tema": preferencia.tema,
            "luft_modo_tema": modo_efetivo,
            "luft_modo_preferido": preferencia.modo.value.lower(),
            "luft_modo_bloqueado": bool(tema_resolvido and tema_resolvido.modo_bloqueado),
            "luft_modos_suportados": modos_suportados,
            "luft_tema_manifesto": manifesto,
            "luft_temas_disponiveis": temas_disponiveis,
            "luft_temas_catalogo": temas_catalogo,
            "luft_csrf_token": token_csrf(),
            "luft_nome_app": app.config.get("LUFT_APLICACAO_NOME", "Luft-WorkSpace"),
            "url_raiz_aplicacao": "/",
            "luft_url_workspace": app.config.get("LUFT_URL_WORKSPACE") or "/",
            "luft_tipo_versao_app": tipo_versao,
            "luft_url_busca": url_busca,
            "luft_app_version_type": tipo_versao,
            "luft_versao_app": versao_app,
            "luft_app_version": versao_app,
            "luft_versao_rodape": texto_rodape,
            "luft_app_version_text": texto_rodape,
            "luft_url_changelog": url_changelog,
            "luft_usuario_foto": usuario_foto,
        }
