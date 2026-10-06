"""Telas e operacoes web de comunicados e notas de atualizacao."""

from __future__ import annotations

import contextlib
from datetime import datetime
from typing import Any

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from werkzeug.exceptions import HTTPException

from luftbase.autorizacao.catalogo import PermissaoLuftBase
from luftbase.autorizacao.web import consultar_permissoes, exigir_permissao
from luftbase.conteudo.markdown_seguro import renderizar as renderizar_markdown
from luftbase.conteudo.modelos import (
    ItemNotaAtualizacao,
    NovaPublicacao,
    PrioridadePublicacao,
    PublicacaoUsuario,
    TipoAudiencia,
    TipoItemAtualizacao,
    TipoPublicacao,
)
from luftbase.interface.web import validar_csrf_requisicao
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado, ErroConteudo
from luftbase.observabilidade import SeveridadeAuditoria, registrar_alteracao_auditoria
from luftbase.persistencia.core.publicacoes import Publicacao
from luftbase.persistencia.core.seguranca import Sistema
from luftbase.plataforma import obter_luftbase

PublicacoesBp = Blueprint("LuftPublicacoes", __name__, url_prefix="/publicacoes")


def _identidade_usuario() -> tuple[int, int | None, str]:
    usuario = current_user._get_current_object()
    return (
        int(getattr(usuario, "id_usuario", 0)),
        getattr(usuario, "id_grupo", None),
        str(
            getattr(usuario, "nome_completo", None) or getattr(usuario, "login", None) or "USUARIO"
        ),
    )


def _data_iso(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _publicacao_feed(item: PublicacaoUsuario) -> dict[str, object]:
    """Adapta o contrato enxuto do dominio ao template visual oficial."""

    return {
        "id": item.id_publicacao,
        "id_publicacao": item.id_publicacao,
        "id_sistema": item.id_sistema,
        "tipo": item.tipo,
        "tipo_publicacao": item.tipo,
        "tipo_audiencia": item.audiencia,
        "titulo": item.titulo,
        "resumo": item.resumo or "",
        "conteudo": item.conteudo or "",
        "prioridade": item.prioridade,
        "versao": item.versao,
        "fixado": item.fixado,
        "lida": item.lida,
        "fonte": "INTERNO",
        "criado_por": "Luft",
        "data_criacao": _data_iso(item.data_publicacao),
        "data_publicacao": _data_iso(item.data_publicacao),
        "exibir_a_partir_de": _data_iso(item.exibir_a_partir_de),
        "expira_em": _data_iso(item.expira_em),
        "itens_atualizacao": [],
        "url_externa": None,
    }


def _publicacao_administracao(item: Publicacao) -> dict[str, object]:
    return {
        "id": item.id_publicacao,
        "id_publicacao": item.id_publicacao,
        "id_sistema": item.id_sistema,
        "tipo": item.tipo_publicacao,
        "tipo_publicacao": item.tipo_publicacao,
        "status": item.status_publicacao,
        "tipo_audiencia": item.tipo_audiencia,
        "ids_grupos": [grupo.id_grupo for grupo in item.grupos],
        "titulo": item.titulo,
        "resumo": item.resumo,
        "conteudo": item.conteudo,
        "prioridade": item.prioridade,
        "versao": item.versao,
        "notificar": item.notificar,
        "fixado": item.fixado,
        "criado_por": item.criado_por,
        "fonte": item.fonte,
        "data_criacao": _data_iso(item.data_criacao),
        "data_publicacao": _data_iso(item.data_publicacao),
        "exibir_a_partir_de": _data_iso(item.exibir_a_partir_de),
        "expira_em": _data_iso(item.expira_em),
        "itens_atualizacao": [
            {
                "tipo": detalhe.tipo_item,
                "titulo": detalhe.titulo,
                "descricao": detalhe.descricao,
                "ordem": detalhe.ordem,
            }
            for detalhe in item.itens_atualizacao
        ],
    }


def _listar_feed(tipo: TipoPublicacao) -> list[dict[str, object]]:
    id_usuario, id_grupo, _nome = _identidade_usuario()
    pagina = obter_luftbase().publicacoes.listar_para_usuario(
        id_usuario,
        id_grupo,
        limite=100,
    )
    return [_publicacao_feed(item) for item in pagina.itens if item.tipo == tipo.value]


def _listar_administracao(tipo: TipoPublicacao) -> list[dict[str, object]]:
    estado = obter_luftbase()
    id_sistema = estado.configuracao.aplicacao.sistema_id
    if id_sistema is None:
        return []
    itens = estado.publicacoes.listar_administracao(tipo=tipo, limite=100)
    return [_publicacao_administracao(item) for item in itens]


def _listar_sistemas() -> list[dict[str, object]]:
    estado = obter_luftbase()
    id_sistema = estado.configuracao.aplicacao.sistema_id
    if id_sistema is None:
        return []
    with estado.infraestrutura.bancos.core.leitura() as sessao:
        if id_sistema == 0:
            sistemas = sessao.scalars(
                select(Sistema).where(Sistema.ativo.is_(True)).order_by(Sistema.id_sistema.asc())
            ).all()
            return [
                {
                    "id": s.id_sistema,
                    "nome": "Todos os sistemas (global)" if s.id_sistema == 0 else s.nome_sistema,
                }
                for s in sistemas
            ]
        sistema = sessao.scalar(select(Sistema).where(Sistema.id_sistema == id_sistema))
        if sistema is None:
            return []
        nome = sistema.nome_sistema
        return [{"id": sistema.id_sistema, "nome": nome}]


def _listar_grupos() -> list[dict[str, object]]:
    estado = obter_luftbase()
    try:
        from luftbase.persistencia.diretorio import GrupoDiretorio

        with estado.infraestrutura.bancos.diretorio.leitura() as sessao:
            grupos = (
                sessao.execute(select(GrupoDiretorio).order_by(GrupoDiretorio.descricao.asc()))
                .scalars()
                .all()
            )
            return [
                {
                    "id": g.id_grupo,
                    "nome": g.descricao or g.sigla or f"Grupo {g.id_grupo}",
                }
                for g in grupos
            ]
    except Exception:
        return []


def _renderizar_feed(tipo: TipoPublicacao) -> str:
    return render_template(
        "luftbase/publicacoes/feed.html",
        tipo_publicacao=tipo.value,
        publicacoes=_listar_feed(tipo),
    )


def _renderizar_painel(tipo: TipoPublicacao) -> str:
    prefixo = (
        "CONTEUDO.COMUNICADOS" if tipo is TipoPublicacao.COMUNICADO else "CONTEUDO.ATUALIZACOES"
    )
    chaves = (
        PermissaoLuftBase.COMUNICADOS_VISUALIZAR,
        PermissaoLuftBase.ATUALIZACOES_VISUALIZAR,
        f"{prefixo}.CRIAR",
        f"{prefixo}.EDITAR",
        f"{prefixo}.PUBLICAR",
        f"{prefixo}.ARQUIVAR",
    )
    decisoes = consultar_permissoes(chaves)
    estado = obter_luftbase()
    return render_template(
        "luftbase/publicacoes/painel.html",
        tipo_publicacao=tipo.value,
        publicacoes=_listar_administracao(tipo),
        grupos_publicacao=_listar_grupos(),
        sistemas_publicacao=_listar_sistemas(),
        sistema_atual_id=estado.configuracao.aplicacao.sistema_id,
        pode_ver_comunicados=bool(decisoes.get(PermissaoLuftBase.COMUNICADOS_VISUALIZAR)),
        pode_ver_atualizacoes=bool(decisoes.get(PermissaoLuftBase.ATUALIZACOES_VISUALIZAR)),
        pode_criar=bool(decisoes.get(f"{prefixo}.CRIAR")),
        pode_editar=bool(decisoes.get(f"{prefixo}.EDITAR")),
        pode_publicar=bool(decisoes.get(f"{prefixo}.PUBLICAR")),
        pode_arquivar=bool(decisoes.get(f"{prefixo}.ARQUIVAR")),
    )


@PublicacoesBp.get("", endpoint="listar")
@PublicacoesBp.get("/atualizacoes", endpoint="listar_atualizacoes")
@login_required
def listar_atualizacoes():  # type: ignore[no-untyped-def]
    """Exibe as notas de atualizacao visiveis para o usuario."""

    return _renderizar_feed(TipoPublicacao.ATUALIZACAO)


@PublicacoesBp.get("/comunicados", endpoint="listar_comunicados")
@login_required
def listar_comunicados():  # type: ignore[no-untyped-def]
    """Exibe os comunicados visiveis para o usuario."""

    return _renderizar_feed(TipoPublicacao.COMUNICADO)


@PublicacoesBp.get("/painel/comunicados", endpoint="painel_comunicados")
@login_required
@exigir_permissao(PermissaoLuftBase.COMUNICADOS_VISUALIZAR)
def painel_comunicados():  # type: ignore[no-untyped-def]
    """Exibe a administracao de comunicados."""

    return _renderizar_painel(TipoPublicacao.COMUNICADO)


@PublicacoesBp.get("/painel/atualizacoes", endpoint="painel_atualizacoes")
@login_required
@exigir_permissao(PermissaoLuftBase.ATUALIZACOES_VISUALIZAR)
def painel_atualizacoes():  # type: ignore[no-untyped-def]
    """Exibe a administracao de notas de atualizacao."""

    return _renderizar_painel(TipoPublicacao.ATUALIZACAO)


@PublicacoesBp.get("/<int:id_publicacao>", endpoint="visualizar_publicacao")
@login_required  # type: ignore[untyped-decorator]
def visualizar_publicacao(id_publicacao: int):  # type: ignore[no-untyped-def]
    """Exibe uma publicacao pertencente a audiencia atual e registra a leitura."""

    id_usuario, id_grupo, _nome = _identidade_usuario()
    try:
        item = obter_luftbase().publicacoes.obter_para_usuario(
            id_usuario,
            id_grupo,
            id_publicacao,
        )
    except ConteudoNaoEncontrado:
        abort(404)

    with contextlib.suppress(Exception):
        obter_luftbase().publicacoes.marcar_lida(
            id_usuario,
            id_grupo,
            id_publicacao,
        )

    publicacao = _publicacao_feed(item)
    publicacao["conteudo_html"] = renderizar_markdown(
        item.conteudo,
        lambda caminho: url_for("luftbase.static", filename=caminho),
    )
    return render_template("luftbase/publicacoes/detalhe.html", publicacao=publicacao)


def _data_payload(valor: Any, campo: str) -> datetime | None:
    if valor in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00")).replace(
            tzinfo=None
        )
    except (TypeError, ValueError) as erro:
        raise ErroConteudo(f"Data invalida no campo {campo}.") from erro


def _booleano_payload(valor: Any, *, padrao: bool) -> bool:
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().casefold() in {"1", "true", "sim", "yes", "on"}


def _nova_publicacao(tipo: TipoPublicacao, dados: dict[str, Any]) -> NovaPublicacao:
    id_usuario, _id_grupo, nome = _identidade_usuario()
    itens = tuple(
        ItemNotaAtualizacao(
            titulo=str(item.get("titulo") or ""),
            descricao=str(item.get("descricao") or "").strip() or None,
            tipo=TipoItemAtualizacao(str(item.get("tipo") or "MELHORIA").upper()),
            ordem=int(item.get("ordem") or 0),
        )
        for item in dados.get("itens_atualizacao") or []
    )
    ids_grupos = tuple(int(valor) for valor in dados.get("ids_grupos") or [])
    return NovaPublicacao(
        titulo=str(dados.get("titulo") or ""),
        resumo=str(dados.get("resumo") or "").strip() or None,
        conteudo=str(dados.get("conteudo") or ""),
        criado_por=nome,
        criado_por_id=id_usuario,
        tipo=tipo,
        audiencia=TipoAudiencia(str(dados.get("tipo_audiencia") or "GERAL").upper()),
        ids_grupos=ids_grupos,
        prioridade=PrioridadePublicacao(str(dados.get("prioridade") or "NORMAL").upper()),
        versao=str(dados.get("versao") or "").strip() or None,
        notificar=_booleano_payload(dados.get("notificar"), padrao=True),
        fixado=_booleano_payload(dados.get("fixado"), padrao=False),
        exibir_a_partir_de=_data_payload(dados.get("exibir_a_partir_de"), "exibir_a_partir_de"),
        expira_em=_data_payload(dados.get("expira_em"), "expira_em"),
        itens_atualizacao=itens,
    )


def _resposta_operacao(operacao: Any):  # type: ignore[no-untyped-def]
    try:
        dados = operacao()
        return jsonify({"status": "success", "dados": dados, "data": dados})
    except ConteudoNaoEncontrado as erro:
        return jsonify({"status": "error", "mensagem": str(erro), "message": str(erro)}), 404
    except (ErroConteudo, ValueError, TypeError) as erro:
        return jsonify({"status": "error", "mensagem": str(erro), "message": str(erro)}), 400
    except HTTPException:
        raise
    except Exception:
        current_app.logger.exception("Falha no modulo web de publicacoes")
        return (
            jsonify(
                {
                    "status": "error",
                    "mensagem": "Nao foi possivel concluir a operacao.",
                    "message": "Nao foi possivel concluir a operacao.",
                }
            ),
            500,
        )


def _criar(tipo: TipoPublicacao) -> dict[str, int]:
    validar_csrf_requisicao()
    dados = request.get_json(silent=True) or {}
    id_publicacao = obter_luftbase().publicacoes.criar_rascunho(_nova_publicacao(tipo, dados))
    registrar_alteracao_auditoria(
        recurso=tipo.value.upper(),
        id_recurso=str(id_publicacao),
        acao=f"CRIAR_{tipo.value.upper()}",
        descricao=f"{tipo.value.capitalize()} #{id_publicacao} criado como rascunho.",
        dados_anteriores=None,
        dados_novos=dados,
        severidade=SeveridadeAuditoria.BAIXA,
    )
    return {"id_publicacao": id_publicacao}


@PublicacoesBp.post("/api/comunicados", endpoint="criar_comunicado")
@login_required
@exigir_permissao(PermissaoLuftBase.COMUNICADOS_CRIAR)
def criar_comunicado():  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _criar(TipoPublicacao.COMUNICADO))


@PublicacoesBp.post("/api/atualizacoes", endpoint="criar_atualizacao")
@login_required
@exigir_permissao(PermissaoLuftBase.ATUALIZACOES_CRIAR)
def criar_atualizacao():  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _criar(TipoPublicacao.ATUALIZACAO))


def _publicar(id_publicacao: int) -> dict[str, object]:
    validar_csrf_requisicao()
    alterada = obter_luftbase().publicacoes.publicar(id_publicacao)
    registrar_alteracao_auditoria(
        recurso="PUBLICACAO",
        id_recurso=str(id_publicacao),
        acao="PUBLICAR",
        descricao=f"Publicação #{id_publicacao} publicada.",
        dados_anteriores={"status": "rascunho"},
        dados_novos={"status": "publicada"},
        severidade=SeveridadeAuditoria.MEDIA,
    )
    return {"id_publicacao": id_publicacao, "alterada": alterada}


@PublicacoesBp.post(
    "/api/comunicados/<int:id_publicacao>/publicar",
    endpoint="publicar_comunicado",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.COMUNICADOS_PUBLICAR)
def publicar_comunicado(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _publicar(id_publicacao))


@PublicacoesBp.post(
    "/api/atualizacoes/<int:id_publicacao>/publicar",
    endpoint="publicar_atualizacao",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.ATUALIZACOES_PUBLICAR)
def publicar_atualizacao(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _publicar(id_publicacao))


def _editar(tipo: TipoPublicacao, id_publicacao: int) -> dict[str, object]:
    validar_csrf_requisicao()
    dados = request.get_json(silent=True) or {}
    alterada = obter_luftbase().publicacoes.atualizar_rascunho(
        id_publicacao, _nova_publicacao(tipo, dados)
    )
    registrar_alteracao_auditoria(
        recurso=tipo.value.upper(),
        id_recurso=str(id_publicacao),
        acao=f"EDITAR_{tipo.value.upper()}",
        descricao=f"{tipo.value.capitalize()} #{id_publicacao} atualizado.",
        dados_novos=dados,
        severidade=SeveridadeAuditoria.BAIXA,
    )
    return {"id_publicacao": id_publicacao, "alterada": alterada}


@PublicacoesBp.post(
    "/api/comunicados/<int:id_publicacao>",
    endpoint="editar_comunicado",
)
@PublicacoesBp.post(
    "/api/comunicados/<int:id_publicacao>/editar",
    endpoint="editar_comunicado_alias",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.COMUNICADOS_EDITAR)
def editar_comunicado(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _editar(TipoPublicacao.COMUNICADO, id_publicacao))


@PublicacoesBp.post(
    "/api/atualizacoes/<int:id_publicacao>",
    endpoint="editar_atualizacao",
)
@PublicacoesBp.post(
    "/api/atualizacoes/<int:id_publicacao>/editar",
    endpoint="editar_atualizacao_alias",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.ATUALIZACOES_EDITAR)
def editar_atualizacao(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _editar(TipoPublicacao.ATUALIZACAO, id_publicacao))


def _arquivar(id_publicacao: int) -> dict[str, object]:
    validar_csrf_requisicao()
    alterada = obter_luftbase().publicacoes.arquivar(id_publicacao)
    registrar_alteracao_auditoria(
        recurso="PUBLICACAO",
        id_recurso=str(id_publicacao),
        acao="ARQUIVAR",
        descricao=f"Publicação #{id_publicacao} arquivada.",
        dados_novos={"status": "arquivada"},
        severidade=SeveridadeAuditoria.BAIXA,
    )
    return {"id_publicacao": id_publicacao, "alterada": alterada}


@PublicacoesBp.post(
    "/api/comunicados/<int:id_publicacao>/arquivar",
    endpoint="arquivar_comunicado",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.COMUNICADOS_ARQUIVAR)
def arquivar_comunicado(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _arquivar(id_publicacao))


@PublicacoesBp.post(
    "/api/atualizacoes/<int:id_publicacao>/arquivar",
    endpoint="arquivar_atualizacao",
)
@login_required  # type: ignore[untyped-decorator]
@exigir_permissao(PermissaoLuftBase.ATUALIZACOES_ARQUIVAR)
def arquivar_atualizacao(id_publicacao: int):  # type: ignore[no-untyped-def]
    return _resposta_operacao(lambda: _arquivar(id_publicacao))


@PublicacoesBp.get(
    "/api/publicacoes/<int:id_publicacao>",
    endpoint="obter_publicacao_admin",
)
@login_required  # type: ignore[untyped-decorator]
def obter_publicacao_admin(id_publicacao: int):  # type: ignore[no-untyped-def]
    decisoes = consultar_permissoes(
        (PermissaoLuftBase.COMUNICADOS_VISUALIZAR, PermissaoLuftBase.ATUALIZACOES_VISUALIZAR)
    )
    if not (
        decisoes.get(PermissaoLuftBase.COMUNICADOS_VISUALIZAR)
        or decisoes.get(PermissaoLuftBase.ATUALIZACOES_VISUALIZAR)
    ):
        abort(403)
    return _resposta_operacao(
        lambda: _publicacao_administracao(
            obter_luftbase().publicacoes.obter_administracao(id_publicacao)
        )
    )


__all__ = ["PublicacoesBp"]
