"""Contratos HTTP autenticados de notificacoes e publicacoes."""

from __future__ import annotations

import json
from collections.abc import Iterable

from flask import Blueprint, Flask, Response, abort, jsonify, request
from flask_login import current_user

from luftbase.conteudo.modelos import NotificacaoUsuario, PublicacaoUsuario
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.interface.web import validar_csrf_requisicao
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado, ErroConteudo


def _usuario_atual() -> UsuarioAutenticado:
    usuario = current_user._get_current_object()
    if not isinstance(usuario, UsuarioAutenticado):
        abort(401)
    return usuario


def _inteiro_consulta(nome: str, *, padrao: int | None = None) -> int | None:
    bruto = request.args.get(nome)
    if bruto is None:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        abort(400, description=f"{nome} deve ser um numero inteiro.")
    if valor < 0:
        abort(400, description=f"{nome} nao pode ser negativo.")
    return valor


def _cursor_sse() -> int:
    bruto = request.headers.get("Last-Event-ID") or request.args.get("cursor") or "0"
    try:
        cursor = int(bruto)
    except ValueError:
        abort(400, description="O cursor SSE deve ser um numero inteiro.")
    if cursor < 0:
        abort(400, description="O cursor SSE nao pode ser negativo.")
    return cursor


def _resposta_sse(evento: str, itens: Iterable[object]) -> Response:
    blocos = ["retry: 5000\n\n"]
    encontrou = False
    for item in itens:
        encontrou = True
        if isinstance(item, NotificacaoUsuario):
            identificador = item.id_notificacao
            dados = item.como_dict()
        elif isinstance(item, PublicacaoUsuario):
            identificador = item.id_publicacao
            dados = item.como_dict()
        else:
            continue
        carga = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
        blocos.append(f"id: {identificador}\nevent: {evento}\ndata: {carga}\n\n")
    if not encontrou:
        blocos.append(": sem novos eventos\n\n")
    return Response(
        "".join(blocos),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


def registrar_rotas_conteudo(app: Flask) -> None:
    """Registra feed, leitura e SSE sem aceitar modelos fornecidos pela aplicacao."""

    bp = Blueprint("luftbase_conteudo", __name__, url_prefix="/_luftbase")

    @bp.get("/notificacoes")
    def listar_notificacoes():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        cursor = _inteiro_consulta("cursor")
        limite = _inteiro_consulta("limite", padrao=30)
        apenas_nao_lidas = request.args.get("apenas_nao_lidas", "").strip().lower() in {
            "true",
            "1",
            "s",
            "sim",
        }
        assert limite is not None
        try:
            from luftbase.plataforma import obter_luftbase

            pagina = obter_luftbase().notificacoes.listar_para_usuario(
                usuario.id_usuario,
                usuario.id_grupo,
                cursor=cursor,
                limite=limite,
                apenas_nao_lidas=apenas_nao_lidas,
            )
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        dados_resposta = pagina.como_dict()
        dados_resposta["dados"] = dados_resposta["itens"]
        dados_resposta["status"] = "success"
        return jsonify(dados_resposta)

    @bp.route("/notificacoes/<int:id_notificacao>/leitura", methods=["PUT", "POST"])
    @bp.route("/notificacoes/<int:id_notificacao>/lida", methods=["PATCH", "PUT", "POST"])
    def marcar_notificacao_lida(id_notificacao: int):  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        validar_csrf_requisicao()
        try:
            from luftbase.plataforma import obter_luftbase

            alterada = obter_luftbase().notificacoes.marcar_lida(
                usuario.id_usuario,
                usuario.id_grupo,
                id_notificacao,
            )
            pagina_restante = obter_luftbase().notificacoes.listar_para_usuario(
                usuario.id_usuario,
                usuario.id_grupo,
                limite=100,
                apenas_nao_lidas=True,
            )
            contagem = len(pagina_restante.itens)
        except ConteudoNaoEncontrado:
            abort(404)
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return {
            "status": "success",
            "alterada": alterada,
            "contagem": contagem,
        }, 200

    @bp.route("/notificacoes/leitura-todas", methods=["PUT", "POST"])
    @bp.route("/notificacoes/marcar-todas", methods=["POST", "PUT"])
    def marcar_todas_notificacoes_lidas():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        validar_csrf_requisicao()
        try:
            from luftbase.plataforma import obter_luftbase

            total = obter_luftbase().notificacoes.marcar_todas_lidas(
                usuario.id_usuario,
                usuario.id_grupo,
            )
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return {
            "status": "success",
            "total_lidas": total,
            "contagem": 0,
        }, 200

    @bp.route("/notificacoes/<int:id_notificacao>/ocultar", methods=["POST", "DELETE"])
    def ocultar_notificacao(id_notificacao: int):  # type: ignore[no-untyped-def]
        """Limpa UMA notificacao so da lista de quem pediu; ela continua no banco para as demais pessoas."""

        usuario = _usuario_atual()
        validar_csrf_requisicao()
        try:
            from luftbase.plataforma import obter_luftbase

            servico = obter_luftbase().notificacoes
            alterada = servico.ocultar(usuario.id_usuario, usuario.id_grupo, id_notificacao)
            contagem = servico.contar_nao_lidas(usuario.id_usuario, usuario.id_grupo)
        except ConteudoNaoEncontrado:
            abort(404)
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return {"status": "success", "alterada": alterada, "contagem": contagem}, 200

    @bp.route("/notificacoes/ocultar-todas", methods=["POST"])
    def ocultar_todas_notificacoes():  # type: ignore[no-untyped-def]
        """Limpa a lista da pessoa. Com `?apenas_lidas=1`, so as ja lidas."""

        usuario = _usuario_atual()
        validar_csrf_requisicao()
        apenas_lidas = request.args.get("apenas_lidas", "").strip().lower() in {"1", "true", "s"}
        try:
            from luftbase.plataforma import obter_luftbase

            servico = obter_luftbase().notificacoes
            total = servico.ocultar_todas(
                usuario.id_usuario, usuario.id_grupo, apenas_lidas=apenas_lidas
            )
            contagem = servico.contar_nao_lidas(usuario.id_usuario, usuario.id_grupo)
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return {"status": "success", "total_ocultadas": total, "contagem": contagem}, 200

    @bp.get("/notificacoes/eventos")
    def eventos_notificacoes():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        cursor = _cursor_sse()
        from luftbase.plataforma import obter_luftbase

        pagina = obter_luftbase().notificacoes.listar_para_usuario(
            usuario.id_usuario,
            usuario.id_grupo,
            cursor=cursor,
            limite=100,
        )
        return _resposta_sse("notificacao", pagina.itens)

    @bp.get("/publicacoes")
    def listar_publicacoes():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        cursor = _inteiro_consulta("cursor")
        limite = _inteiro_consulta("limite", padrao=30)
        assert limite is not None
        try:
            from luftbase.plataforma import obter_luftbase

            pagina = obter_luftbase().publicacoes.listar_para_usuario(
                usuario.id_usuario,
                usuario.id_grupo,
                cursor=cursor,
                limite=limite,
            )
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return jsonify(pagina.como_dict())

    @bp.get("/publicacoes/<int:id_publicacao>")
    def obter_publicacao(id_publicacao: int):  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        try:
            from luftbase.plataforma import obter_luftbase

            publicacao = obter_luftbase().publicacoes.obter_para_usuario(
                usuario.id_usuario,
                usuario.id_grupo,
                id_publicacao,
            )
        except ConteudoNaoEncontrado:
            abort(404)
        return jsonify(publicacao.como_dict())

    @bp.put("/publicacoes/<int:id_publicacao>/leitura")
    def marcar_publicacao_lida(id_publicacao: int):  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        validar_csrf_requisicao()
        try:
            from luftbase.plataforma import obter_luftbase

            alterada = obter_luftbase().publicacoes.marcar_lida(
                usuario.id_usuario,
                usuario.id_grupo,
                id_publicacao,
            )
        except ConteudoNaoEncontrado:
            abort(404)
        except ErroConteudo as erro:
            abort(400, description=str(erro))
        return {"alterada": alterada}, 200

    @bp.get("/publicacoes/eventos")
    def eventos_publicacoes():  # type: ignore[no-untyped-def]
        usuario = _usuario_atual()
        cursor = _cursor_sse()
        from luftbase.plataforma import obter_luftbase

        pagina = obter_luftbase().publicacoes.listar_para_usuario(
            usuario.id_usuario,
            usuario.id_grupo,
            cursor=cursor,
            limite=100,
        )
        return _resposta_sse("publicacao", pagina.itens)

    app.register_blueprint(bp)
