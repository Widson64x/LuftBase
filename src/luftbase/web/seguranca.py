"""Gerenciador web do catalogo e da matriz de autorizacao hierarquica."""

from __future__ import annotations

import contextlib
import logging
import os
import re
from dataclasses import dataclass
from typing import cast

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from luftbase.autorizacao.aviso_acesso import (
    CapturaAcesso,
    avisar_acessos_liberados,
    capturar_acesso,
)
from luftbase.autorizacao.catalogo import ACOES_PERMISSAO, PermissaoLuftBase
from luftbase.autorizacao.resolucao import resolver_estados as _resolver_estados
from luftbase.autorizacao.web import consultar_permissoes, exigir_permissao
from luftbase.interface.web import validar_csrf_requisicao
from luftbase.observabilidade import SeveridadeAuditoria, registrar_alteracao_auditoria
from luftbase.persistencia.core.seguranca import (
    Modulo,
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    Sistema,
)
from luftbase.persistencia.core.usuario import Usuario
from luftbase.persistencia.diretorio import GrupoDiretorio, UsuarioDiretorio
from luftbase.plataforma import obter_luftbase
from luftbase.web.escopo import eh_sistema_master, resolver_escopo_sistema

logger = logging.getLogger(__name__)
SegurancaBp = Blueprint("Seguranca", __name__, url_prefix="/seguranca")
_IDENTIFICADOR = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


@dataclass(frozen=True, slots=True)
class GrupoItem:
    """Grupo corporativo para exibicao em lista."""

    codigo_usuariogrupo: int
    sigla: str
    descricao: str

    @property
    def Codigo_UsuarioGrupo(self) -> int:
        return self.codigo_usuariogrupo

    @property
    def Nome_Grupo(self) -> str:
        return self.descricao

    @property
    def Nome_UsuarioGrupo(self) -> str:
        return self.descricao

    @property
    def Sigla_UsuarioGrupo(self) -> str:
        return self.sigla

    @property
    def nome(self) -> str:
        return self.descricao


@dataclass(frozen=True, slots=True)
class UsuarioItem:
    """Usuario corporativo para exibicao em lista."""

    codigo_usuario: int
    nome_usuario: str
    login_usuario: str
    id_grupo: int | None
    nome_grupo: str | None

    @property
    def Codigo_Usuario(self) -> int:
        return self.codigo_usuario

    @property
    def Nome_Usuario(self) -> str:
        return self.nome_usuario

    @property
    def Login_Usuario(self) -> str:
        return self.login_usuario

    @property
    def Nome_UsuarioGrupo(self) -> str:
        return self.nome_grupo or "Sem grupo"

    @property
    def nome(self) -> str:
        return self.nome_usuario

    @property
    def login(self) -> str:
        return self.login_usuario


@dataclass(frozen=True, slots=True)
class PermissaoItem:
    """Permissao pronta para exibicao em arvore."""

    id_permissao: int
    chave_permissao: str
    descricao_permissao: str
    codigo_modulo: str
    nome_modulo: str
    id_sistema: int
    id_permissao_pai: int | None
    recurso: str
    acao: str
    chave_pai: str | None
    sensivel: bool
    ativo: bool
    nivel: int
    possui_filhos: bool = False
    eh_gestora: bool = False

    @property
    def Id_Permissao(self) -> int:
        return self.id_permissao

    @property
    def Chave_Permissao(self) -> str:
        return self.chave_permissao

    @property
    def Descricao_Permissao(self) -> str:
        return self.descricao_permissao

    @property
    def Categoria_Permissao(self) -> str:
        return self.nome_modulo


@dataclass(frozen=True, slots=True)
class ModuloItem:
    """Modulo pronto para selecao e renderizacao no gerenciador."""

    id_modulo: int
    codigo_modulo: str
    nome_modulo: str
    descricao_modulo: str
    icone: str
    ordem_exibicao: int
    ativo: bool = True
    total_permissoes: int = 0

    @property
    def Id_Modulo(self) -> int:
        return self.id_modulo

    @property
    def Codigo_Modulo(self) -> str:
        return self.codigo_modulo

    @property
    def Nome_Modulo(self) -> str:
        return self.nome_modulo


@dataclass(frozen=True, slots=True)
class SistemaItem:
    """Sistema selecionavel no gerenciador."""

    id_sistema: int
    nome_sistema: str

    @property
    def Id_Sistema(self) -> int:
        return self.id_sistema

    @property
    def Nome_Sistema(self) -> str:
        return self.nome_sistema


def _calcular_niveis(permissoes: list[Permissao]) -> dict[int, int]:
    mapa = {item.id_permissao: item for item in permissoes}
    niveis: dict[int, int] = {}

    def calcular(item: Permissao, visitados: frozenset[int] = frozenset()) -> int:
        if item.id_permissao in niveis:
            return niveis[item.id_permissao]
        if item.id_permissao in visitados or item.id_permissao_pai is None:
            niveis[item.id_permissao] = 0
            return 0
        pai = mapa.get(item.id_permissao_pai)
        nivel = 0 if pai is None else min(calcular(pai, visitados | {item.id_permissao}) + 1, 32)
        niveis[item.id_permissao] = nivel
        return nivel

    for permissao in permissoes:
        calcular(permissao)
    return niveis


def _ordenar_arvore_modulo(
    permissoes_modulo: list[PermissaoItem],
) -> list[PermissaoItem]:
    """Ordena as permissoes de um modulo em travessia de arvore verdadeira (DFS).

    Nós pais aparecem sempre imediatamente acima de seus respectivos filhos e netos.
    """
    if not permissoes_modulo:
        return []

    ids_no_modulo = {p.id_permissao for p in permissoes_modulo}
    filhos_por_pai: dict[int, list[PermissaoItem]] = {}
    raizes: list[PermissaoItem] = []

    for item in permissoes_modulo:
        if item.id_permissao_pai is None or item.id_permissao_pai not in ids_no_modulo:
            raizes.append(item)
        else:
            filhos_por_pai.setdefault(item.id_permissao_pai, []).append(item)

    for lista_filhos in filhos_por_pai.values():
        lista_filhos.sort(key=lambda x: (x.nivel, x.chave_permissao))

    raizes.sort(key=lambda x: (x.nivel, x.chave_permissao))

    resultado: list[PermissaoItem] = []
    visitados: set[int] = set()

    def percorrer(no: PermissaoItem) -> None:
        if no.id_permissao in visitados:
            return
        visitados.add(no.id_permissao)
        resultado.append(no)
        for filho in filhos_por_pai.get(no.id_permissao, ()):
            percorrer(filho)

    for raiz in raizes:
        percorrer(raiz)

    for item in permissoes_modulo:
        if item.id_permissao not in visitados:
            resultado.append(item)

    return resultado


def _carregar_permissoes(sessao: object, sistema_id: int) -> list[Permissao]:
    return list(
        sessao.execute(  # type: ignore[attr-defined]
            select(Permissao)
            .where(Permissao.id_sistema == sistema_id)
            .order_by(Permissao.id_modulo, Permissao.ordem_exibicao, Permissao.chave_permissao)
        )
        .scalars()
        .all()
    )


def _url_base_publica() -> str:
    """Endereco publico da plataforma para links de e-mail (`LUFT_URL_PUBLICA` ou o host da requisicao)."""

    return (os.environ.get("LUFT_URL_PUBLICA") or "").strip() or request.host_url


def _avisar_acesso_liberado(antes: CapturaAcesso, estado: object) -> dict[str, int]:
    """Avisa (notificacao + e-mail) quem ganhou acesso por causa desta mudanca. Nunca levanta."""

    resultado = avisar_acessos_liberados(
        estado.bancos,  # type: ignore[attr-defined]
        estado.email,  # type: ignore[attr-defined]
        antes,
        url_base=_url_base_publica(),
        liberado_por=str(getattr(current_user, "login", "") or ""),
        garantir_usuario=garantir_usuario_no_core,
    )
    if resultado.com_acesso_novo:
        registrar_alteracao_auditoria(
            recurso="ACESSO_SISTEMA",
            id_recurso=antes.id_sistema,
            acao="ACESSO_LIBERADO_AVISO",
            descricao=(
                f"{resultado.com_acesso_novo} pessoa(s) ganharam acesso ao sistema "
                f"{antes.id_sistema}; avisos enviados."
            ),
            dados_novos=resultado.como_dict(),
            severidade=SeveridadeAuditoria.BAIXA,
        )
    return resultado.como_dict()


@SegurancaBp.get("/gerenciador")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def visualizar_gerenciador():  # type: ignore[no-untyped-def]
    """Renderiza modulos e arvore de permissoes do sistema selecionado."""

    sistema_selecionado = resolver_escopo_sistema(request.args.get("sistema_id"))
    is_master = eh_sistema_master()
    estado = obter_luftbase()
    decisoes = consultar_permissoes(
        (
            PermissaoLuftBase.PERMISSOES_CONCEDER,
            PermissaoLuftBase.PERMISSOES_CRIAR,
            PermissaoLuftBase.USUARIOS_DESATIVAR,
        )
    )

    with estado.bancos.core.leitura() as sessao_core:
        sistemas_db = (
            sessao_core.execute(
                select(Sistema).where(Sistema.ativo.is_(True)).order_by(Sistema.ordem_exibicao)
            )
            .scalars()
            .all()
        )
        todos_sistemas = [SistemaItem(s.id_sistema, s.nome_sistema) for s in sistemas_db]
        sistemas_disponiveis = (
            todos_sistemas
            if is_master
            else [s for s in todos_sistemas if s.id_sistema == sistema_selecionado]
        )
        modulos_db = list(
            sessao_core.execute(
                select(Modulo)
                .where(Modulo.id_sistema == sistema_selecionado)
                .order_by(Modulo.ordem_exibicao, Modulo.nome_modulo)
            )
            .scalars()
            .all()
        )
        contagens_modulo: dict[int, int] = {
            int(r[0]): int(r[1])
            for r in sessao_core.execute(
                select(Permissao.id_modulo, func.count(Permissao.id_permissao))
                .where(Permissao.id_sistema == sistema_selecionado)
                .group_by(Permissao.id_modulo)
            ).all()
        }
        modulos = [
            ModuloItem(
                id_modulo=m.id_modulo,
                codigo_modulo=m.codigo_modulo,
                nome_modulo=m.nome_modulo,
                descricao_modulo=m.descricao_modulo or "",
                icone=m.icone or "ph-cube",
                ordem_exibicao=m.ordem_exibicao,
                ativo=m.ativo,
                total_permissoes=contagens_modulo.get(m.id_modulo, 0),
            )
            for m in modulos_db
        ]
        permissoes = _carregar_permissoes(sessao_core, sistema_selecionado)
        niveis = _calcular_niveis(permissoes)
        ids_com_filhos = {p.id_permissao_pai for p in permissoes if p.id_permissao_pai is not None}
        mapa_chaves = {p.id_permissao: p.chave_permissao for p in permissoes}
        itens_brutos_por_modulo: dict[str, list[PermissaoItem]] = {
            modulo.nome_modulo: [] for modulo in modulos
        }
        modulos_por_id = {modulo.id_modulo: modulo for modulo in modulos}
        for permissao in permissoes:
            modulo = modulos_por_id[permissao.id_modulo]
            id_pai = permissao.id_permissao_pai
            chave_pai = mapa_chaves.get(id_pai) if id_pai else None
            eh_gestora = (
                permissao.acao in ("ADMINISTRAR", "GERENCIAR")
                or permissao.id_permissao_pai is None
                or permissao.chave_permissao.endswith(".MODULO.GERENCIAR")
            )
            itens_brutos_por_modulo[modulo.nome_modulo].append(
                PermissaoItem(
                    id_permissao=permissao.id_permissao,
                    chave_permissao=permissao.chave_permissao,
                    descricao_permissao=permissao.descricao_permissao,
                    codigo_modulo=modulo.codigo_modulo,
                    nome_modulo=modulo.nome_modulo,
                    id_sistema=permissao.id_sistema,
                    id_permissao_pai=permissao.id_permissao_pai,
                    recurso=permissao.recurso,
                    acao=permissao.acao,
                    chave_pai=chave_pai,
                    sensivel=permissao.sensivel,
                    ativo=permissao.ativo,
                    nivel=niveis[permissao.id_permissao],
                    possui_filhos=permissao.id_permissao in ids_com_filhos,
                    eh_gestora=eh_gestora,
                )
            )

        por_modulo: dict[str, list[PermissaoItem]] = {
            nome_mod: _ordenar_arvore_modulo(itens)
            for nome_mod, itens in itens_brutos_por_modulo.items()
        }

    try:
        with estado.bancos.diretorio.leitura() as sessao_dir:
            grupos_db = (
                sessao_dir.execute(select(GrupoDiretorio).order_by(GrupoDiretorio.descricao))
                .scalars()
                .all()
            )
            grupos = [
                GrupoItem(g.id_grupo, g.sigla or f"G_{g.id_grupo}", g.descricao or "Sem nome")
                for g in grupos_db
            ]
            usuarios_db = (
                sessao_dir.execute(
                    select(UsuarioDiretorio).order_by(UsuarioDiretorio.nome_completo)
                )
                .scalars()
                .all()
            )
            nomes_grupo = {grupo.codigo_usuariogrupo: grupo.sigla for grupo in grupos}
            usuarios = [
                UsuarioItem(
                    usuario.id_usuario,
                    usuario.nome_completo or usuario.login or f"Usuario {usuario.id_usuario}",
                    usuario.login or "",
                    usuario.id_grupo,
                    nomes_grupo.get(usuario.id_grupo or -1),
                )
                for usuario in usuarios_db
            ]
    except (SQLAlchemyError, OSError, RuntimeError) as erro:
        logger.warning("Diretorio corporativo indisponivel: %s", erro)
        grupos = []
        usuarios = []

    return render_template(
        "luftbase/seguranca/gerenciador.html",
        Grupos=grupos,
        Usuarios=usuarios,
        PermissoesPorCategoria=por_modulo,
        Modulos=modulos,
        AcoesPermissao=ACOES_PERMISSAO,
        PodeEditar=bool(decisoes.get(PermissaoLuftBase.PERMISSOES_CONCEDER.value)),
        PodeCriar=bool(decisoes.get(PermissaoLuftBase.PERMISSOES_CRIAR.value)),
        PodeBloquear=bool(decisoes.get(PermissaoLuftBase.USUARIOS_DESATIVAR.value)),
        IsMaster=is_master,
        SistemaIdSelecionado=sistema_selecionado,
        SistemasDisponiveis=sistemas_disponiveis,
    )


@SegurancaBp.get("/api/permissoes/buscar-grupo")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def buscar_acessos_grupo():  # type: ignore[no-untyped-def]
    """Retorna regras diretas e estados herdados de um grupo."""

    try:
        id_grupo = int(request.args.get("idGrupo", -1))
        sistema_id = resolver_escopo_sistema(request.args.get("sistema_id"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Parametros invalidos."), 400
    if id_grupo <= 0:
        return jsonify(status="error", message="ID do grupo invalido."), 400

    with obter_luftbase().bancos.core.leitura() as sessao:
        permissoes = _carregar_permissoes(sessao, sistema_id)
        linhas_regras = sessao.execute(
            select(PermissaoGrupo.id_permissao, PermissaoGrupo.conceder)
            .join(Permissao, Permissao.id_permissao == PermissaoGrupo.id_permissao)
            .where(
                PermissaoGrupo.codigo_usuariogrupo == id_grupo,
                Permissao.id_sistema == sistema_id,
            )
        ).all()
        regras: dict[int, bool] = {int(r[0]): bool(r[1]) for r in linhas_regras}
        estados = _resolver_estados(permissoes, {}, regras)
    return jsonify(
        status="success",
        data={
            "estados": estados,
            "regras_permitidas": [id_ for id_, concede in regras.items() if concede],
            "regras_bloqueadas": [id_ for id_, concede in regras.items() if not concede],
        },
    )


@SegurancaBp.get("/api/permissoes/buscar-usuario")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def buscar_acessos_usuario():  # type: ignore[no-untyped-def]
    """Retorna os estados efetivos e suas origens para um usuario."""

    try:
        id_usuario = int(request.args.get("idUsuario", -1))
        sistema_id = resolver_escopo_sistema(request.args.get("sistema_id"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Parametros invalidos."), 400
    if id_usuario <= 0:
        return jsonify(status="error", message="ID do usuario invalido."), 400

    estado = obter_luftbase()
    id_grupo: int | None = None
    try:
        with estado.bancos.diretorio.leitura() as sessao_dir:
            usuario = sessao_dir.get(UsuarioDiretorio, id_usuario)
            id_grupo = usuario.id_grupo if usuario else None
    except Exception as erro:
        logger.warning("Falha ao consultar o grupo do usuario %s: %s", id_usuario, erro)

    with estado.bancos.core.leitura() as sessao:
        permissoes = _carregar_permissoes(sessao, sistema_id)
        regras_grupo: dict[int, bool] = {}
        if id_grupo is not None:
            linhas_grupo = sessao.execute(
                select(PermissaoGrupo.id_permissao, PermissaoGrupo.conceder)
                .join(Permissao, Permissao.id_permissao == PermissaoGrupo.id_permissao)
                .where(
                    PermissaoGrupo.codigo_usuariogrupo == id_grupo,
                    Permissao.id_sistema == sistema_id,
                )
            ).all()
            regras_grupo = {int(r[0]): bool(r[1]) for r in linhas_grupo}
        linhas_usuario = sessao.execute(
            select(PermissaoUsuario.id_permissao, PermissaoUsuario.conceder)
            .join(Permissao, Permissao.id_permissao == PermissaoUsuario.id_permissao)
            .where(
                PermissaoUsuario.codigo_usuario == id_usuario,
                Permissao.id_sistema == sistema_id,
            )
        ).all()
        regras_usuario: dict[int, bool] = {int(r[0]): bool(r[1]) for r in linhas_usuario}
        estados = _resolver_estados(permissoes, regras_usuario, regras_grupo)

    return jsonify(
        status="success",
        data={
            "estados": estados,
            "regras_usuario": regras_usuario,
        },
    )


@SegurancaBp.post("/api/permissoes/salvar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CONCEDER)
def salvar_vinculo():  # type: ignore[no-untyped-def]
    """Cria uma regra permitir/negar ou restaura a heranca."""

    validar_csrf_requisicao()
    dados = request.get_json() or {}
    raw_alvo = dados.get("IdAlvo")
    raw_permissao = dados.get("IdPermissao")
    if raw_alvo is None or raw_permissao is None:
        return jsonify(status="error", message="IDs invalidos."), 400
    try:
        id_alvo = int(raw_alvo)
        id_permissao = int(raw_permissao)
    except (TypeError, ValueError):
        return jsonify(status="error", message="IDs invalidos."), 400
    tipo = str(dados.get("Tipo") or "").strip()
    acao = str(dados.get("Acao") or "").strip()
    if tipo not in {"Grupo", "Usuario"} or acao not in {"Permitir", "Bloquear", "Resetar"}:
        return jsonify(status="error", message="Tipo ou acao invalida."), 400
    if id_alvo <= 0 or id_permissao <= 0:
        return jsonify(status="error", message="IDs devem ser positivos."), 400

    estado = obter_luftbase()
    ator = getattr(current_user, "id_usuario", None)
    modelo: type[PermissaoGrupo | PermissaoUsuario] = (
        PermissaoGrupo if tipo == "Grupo" else PermissaoUsuario
    )
    coluna_alvo = (
        PermissaoGrupo.codigo_usuariogrupo if tipo == "Grupo" else PermissaoUsuario.codigo_usuario
    )
    dados_anteriores: dict[str, object] | None = None
    dados_novos: dict[str, object] | None = None
    chave_permissao = ""
    if tipo == "Usuario" and acao != "Resetar" and not garantir_usuario_no_core(id_alvo):
        return jsonify(status="error", message="Usuario nao encontrado no diretorio."), 404
    with estado.bancos.core.leitura() as sessao_previa:
        id_sistema_regra = sessao_previa.execute(
            select(Permissao.id_sistema).where(Permissao.id_permissao == id_permissao)
        ).scalar_one_or_none()
    antes_acesso = (
        capturar_acesso(estado.bancos, tipo=tipo, id_alvo=id_alvo, id_sistema=id_sistema_regra)
        if id_sistema_regra is not None
        else None
    )
    with estado.bancos.core.escrita() as sessao:
        permissao = sessao.get(Permissao, id_permissao)
        if permissao is None:
            return jsonify(status="error", message="Permissao nao encontrada."), 404
        chave_permissao = permissao.chave_permissao
        resolver_escopo_sistema(permissao.id_sistema)
        vinculo = cast(
            PermissaoGrupo | PermissaoUsuario | None,
            sessao.execute(
                select(modelo).where(coluna_alvo == id_alvo, modelo.id_permissao == id_permissao)
            ).scalar_one_or_none(),
        )
        if vinculo is not None:
            dados_anteriores = {
                "tipo": tipo,
                "id_alvo": id_alvo,
                "chave_permissao": chave_permissao,
                "conceder": vinculo.conceder,
            }
        if acao == "Resetar":
            if vinculo is not None:
                sessao.delete(vinculo)
            dados_novos = None
        elif vinculo is None:
            sessao.add(
                modelo(
                    **{coluna_alvo.key: id_alvo},
                    id_permissao=id_permissao,
                    conceder=acao == "Permitir",
                    codigo_usuario_alteracao=ator,
                )
            )
            dados_novos = {
                "tipo": tipo,
                "id_alvo": id_alvo,
                "chave_permissao": chave_permissao,
                "conceder": acao == "Permitir",
            }
        else:
            vinculo.conceder = acao == "Permitir"
            vinculo.codigo_usuario_alteracao = ator
            dados_novos = {
                "tipo": tipo,
                "id_alvo": id_alvo,
                "chave_permissao": chave_permissao,
                "conceder": acao == "Permitir",
            }

    estado.autorizacao.invalidar_cache()
    registrar_alteracao_auditoria(
        recurso=f"PERMISSAO_{tipo.upper()}",
        id_recurso=f"{id_alvo}:{chave_permissao}",
        acao=f"PERMISSAO_{acao.upper()}",
        descricao=f"Regra de permissão '{chave_permissao}' para {tipo.lower()} {id_alvo} alterada para {acao}.",
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        severidade=SeveridadeAuditoria.MEDIA,
    )
    if antes_acesso is not None:
        _avisar_acesso_liberado(antes_acesso, estado)
    return jsonify(status="success", message="Regra salva com sucesso.")


@SegurancaBp.get("/api/permissoes/resumo-origem")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def resumo_regras_origem():  # type: ignore[no-untyped-def]
    """Retorna contadores de regras diretas de uma entidade origem para preview."""

    try:
        id_alvo = int(request.args.get("id", -1))
        tipo = str(request.args.get("tipo") or "").strip()
        sistema_id = resolver_escopo_sistema(request.args.get("sistema_id"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Parametros invalidos."), 400

    if id_alvo <= 0 or tipo not in {"Grupo", "Usuario"}:
        return jsonify(status="error", message="Entidade invalida."), 400

    modelo: type[PermissaoGrupo | PermissaoUsuario] = (
        PermissaoGrupo if tipo == "Grupo" else PermissaoUsuario
    )
    coluna_alvo = (
        PermissaoGrupo.codigo_usuariogrupo if tipo == "Grupo" else PermissaoUsuario.codigo_usuario
    )

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        linhas = sessao.execute(
            select(
                Permissao.chave_permissao,
                Permissao.descricao_permissao,
                modelo.conceder,
            )
            .join(Permissao, Permissao.id_permissao == modelo.id_permissao)
            .where(coluna_alvo == id_alvo, Permissao.id_sistema == sistema_id)
            .order_by(Permissao.chave_permissao)
        ).all()

    regras = [
        {"chave": chave, "descricao": descricao or "", "conceder": bool(conceder)}
        for chave, descricao, conceder in linhas
    ]
    total = len(regras)
    permitidas = sum(1 for regra in regras if regra["conceder"])
    return jsonify(
        status="success",
        data={
            "total": total,
            "permitidas": permitidas,
            "bloqueadas": total - permitidas,
            "regras": regras,
        },
    )


@SegurancaBp.post("/api/permissoes/espelhar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CONCEDER)
def espelhar_permissoes():  # type: ignore[no-untyped-def]
    """Copia em lote as regras diretas de uma origem para um destino."""

    validar_csrf_requisicao()
    dados = request.get_json() or {}

    try:
        id_origem = int(dados.get("id_origem", -1))
        id_destino = int(dados.get("id_destino", -1))
        sistema_id = resolver_escopo_sistema(dados.get("sistema_id"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Parametros numericos invalidos."), 400

    tipo_origem = str(dados.get("tipo_origem") or "").strip()
    tipo_destino = str(dados.get("tipo_destino") or "").strip()
    modo = str(dados.get("modo") or "substituir").strip().lower()

    if tipo_origem not in {"Grupo", "Usuario"} or tipo_destino not in {"Grupo", "Usuario"}:
        return jsonify(status="error", message="Tipos de entidade invalidos."), 400

    if id_origem <= 0 or id_destino <= 0:
        return jsonify(status="error", message="IDs de entidade devem ser positivos."), 400

    if tipo_origem == tipo_destino and id_origem == id_destino:
        return (
            jsonify(
                status="error",
                message="A origem e o destino nao podem ser a mesma entidade.",
            ),
            400,
        )

    if modo not in {"substituir", "mesclar"}:
        return (
            jsonify(
                status="error",
                message="Modo de espelhamento invalido. Use 'substituir' ou 'mesclar'.",
            ),
            400,
        )

    modelo_origem: type[PermissaoGrupo | PermissaoUsuario] = (
        PermissaoGrupo if tipo_origem == "Grupo" else PermissaoUsuario
    )
    coluna_origem = (
        PermissaoGrupo.codigo_usuariogrupo
        if tipo_origem == "Grupo"
        else PermissaoUsuario.codigo_usuario
    )

    modelo_destino: type[PermissaoGrupo | PermissaoUsuario] = (
        PermissaoGrupo if tipo_destino == "Grupo" else PermissaoUsuario
    )
    coluna_destino = (
        PermissaoGrupo.codigo_usuariogrupo
        if tipo_destino == "Grupo"
        else PermissaoUsuario.codigo_usuario
    )

    estado = obter_luftbase()
    ator = getattr(current_user, "id_usuario", None)

    if tipo_destino == "Usuario" and not garantir_usuario_no_core(id_destino):
        return jsonify(status="error", message="O usuario de destino nao foi encontrado no diretorio."), 404

    antes_acesso = capturar_acesso(
        estado.bancos, tipo=tipo_destino, id_alvo=id_destino, id_sistema=sistema_id
    )
    with estado.bancos.core.escrita() as sessao:
        regras_origem = sessao.execute(
            select(modelo_origem.id_permissao, modelo_origem.conceder)
            .join(Permissao, Permissao.id_permissao == modelo_origem.id_permissao)
            .where(
                coluna_origem == id_origem,
                Permissao.id_sistema == sistema_id,
            )
        ).all()

        if not regras_origem:
            return (
                jsonify(
                    status="error",
                    message=(
                        "A origem selecionada nao possui nenhuma regra direta"
                        " cadastrada neste sistema."
                    ),
                ),
                400,
            )

        if modo == "substituir":
            regras_existentes = list(
                sessao.execute(
                    select(modelo_destino)
                    .join(Permissao, Permissao.id_permissao == modelo_destino.id_permissao)
                    .where(
                        coluna_destino == id_destino,
                        Permissao.id_sistema == sistema_id,
                    )
                )
                .scalars()
                .all()
            )
            for reg in regras_existentes:
                sessao.delete(reg)
            sessao.flush()

            for id_perm, conceder in regras_origem:
                sessao.add(
                    modelo_destino(
                        **{coluna_destino.key: id_destino},
                        id_permissao=id_perm,
                        conceder=conceder,
                        codigo_usuario_alteracao=ator,
                    )
                )
        else:  # modo == "mesclar"
            regras_mesclar: list[PermissaoGrupo | PermissaoUsuario] = cast(
                list[PermissaoGrupo | PermissaoUsuario],
                list(
                    sessao.execute(
                        select(modelo_destino)
                        .join(Permissao, Permissao.id_permissao == modelo_destino.id_permissao)
                        .where(
                            coluna_destino == id_destino,
                            Permissao.id_sistema == sistema_id,
                        )
                    )
                    .scalars()
                    .all()
                ),
            )
            mapa_existentes = {r.id_permissao: r for r in regras_mesclar}

            for id_perm, conceder in regras_origem:
                if id_perm in mapa_existentes:
                    mapa_existentes[id_perm].conceder = conceder
                    mapa_existentes[id_perm].codigo_usuario_alteracao = ator
                else:
                    sessao.add(
                        modelo_destino(
                            **{coluna_destino.key: id_destino},
                            id_permissao=id_perm,
                            conceder=conceder,
                            codigo_usuario_alteracao=ator,
                        )
                    )

    estado.autorizacao.invalidar_cache()
    total_copiadas = len(regras_origem)
    registrar_alteracao_auditoria(
        recurso=f"PERMISSAO_{tipo_destino.upper()}",
        id_recurso=str(id_destino),
        acao="ESPELHAR_PERMISSOES",
        descricao=f"Espelhadas {total_copiadas} regra(s) de {tipo_origem.lower()} {id_origem} para {tipo_destino.lower()} {id_destino} no modo '{modo}'.",
        dados_anteriores={"modo": modo, "id_origem": id_origem, "tipo_origem": tipo_origem},
        dados_novos={"id_destino": id_destino, "tipo_destino": tipo_destino, "total_regras": total_copiadas},
        severidade=SeveridadeAuditoria.MEDIA,
    )
    _avisar_acesso_liberado(antes_acesso, estado)
    return jsonify(
        status="success",
        message=f"{total_copiadas} regra(s) espelhada(s) com sucesso.",
        total=total_copiadas,
    )


@SegurancaBp.get("/api/usuarios/<int:codigo_usuario>/bloqueio")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def consultar_bloqueio_usuario(codigo_usuario: int):  # type: ignore[no-untyped-def]
    """Estado do bloqueio de login de uma pessoa (sem o motivo para quem so visualiza)."""

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        linha = sessao.execute(
            select(Usuario.bloqueado, Usuario.motivo_bloqueio).where(
                Usuario.codigo_usuario == codigo_usuario
            )
        ).first()
    bloqueado = bool(linha[0]) if linha else False
    pode = bool(consultar_permissoes([PermissaoLuftBase.USUARIOS_DESATIVAR.value]).get(
        PermissaoLuftBase.USUARIOS_DESATIVAR.value
    ))
    return jsonify(
        status="success",
        data={
            "bloqueado": bloqueado,
            "motivo": (linha[1] if linha and pode else None),
            "pode_alterar": pode,
        },
    )


def _alterar_bloqueio(bloquear: bool):  # type: ignore[no-untyped-def]
    validar_csrf_requisicao()
    dados = request.get_json(silent=True) or {}
    try:
        codigo = int(dados.get("IdUsuario"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Usuario invalido."), 400
    if codigo <= 0:
        return jsonify(status="error", message="Usuario invalido."), 400
    motivo = str(dados.get("Motivo") or "").strip()
    if bloquear and len(motivo) < 5:
        return jsonify(status="error", message="Informe o motivo do bloqueio (minimo 5 letras)."), 400
    if bloquear and codigo == getattr(current_user, "id_usuario", None):
        return jsonify(status="error", message="Voce nao pode bloquear o proprio acesso."), 400

    estado = obter_luftbase()
    if not garantir_usuario_no_core(codigo):
        return jsonify(status="error", message="Usuario nao encontrado no diretorio."), 404
    repositorio = estado.usuarios_core
    anterior = repositorio.esta_bloqueado(codigo)
    if not repositorio.definir_bloqueio(codigo, bloquear, motivo):
        return jsonify(status="error", message="Usuario nao encontrado."), 404

    encerradas = 0
    if bloquear:
        armazenamento = estado.infraestrutura.armazenamento_sessoes
        revogar = getattr(armazenamento, "revogar_sessao", None)
        if callable(revogar):
            for sessao_ativa in repositorio.listar_sessoes_usuario(codigo):
                with contextlib.suppress(Exception):
                    if revogar(sessao_ativa["id_sessao"], "BLOQUEIO_ADMIN"):
                        encerradas += 1
    estado.autorizacao.invalidar_cache()
    registrar_alteracao_auditoria(
        recurso="USUARIO_BLOQUEIO",
        id_recurso=codigo,
        acao="USUARIO_BLOQUEADO" if bloquear else "USUARIO_DESBLOQUEADO",
        descricao=(
            f"Login do usuario {codigo} {'bloqueado' if bloquear else 'desbloqueado'}"
            f"{': ' + motivo if bloquear else ''}."
        ),
        dados_anteriores={"bloqueado": anterior},
        dados_novos={"bloqueado": bloquear, "motivo": motivo or None, "sessoes_encerradas": encerradas},
        severidade=SeveridadeAuditoria.ALTA if bloquear else SeveridadeAuditoria.MEDIA,
    )
    return jsonify(
        status="success",
        message=(
            f"Acesso bloqueado. {encerradas} sessao(oes) encerrada(s)."
            if bloquear
            else "Acesso desbloqueado."
        ),
        sessoes_encerradas=encerradas,
    )


@SegurancaBp.post("/api/usuarios/bloquear")
@login_required
@exigir_permissao(PermissaoLuftBase.USUARIOS_DESATIVAR)
def bloquear_usuario():  # type: ignore[no-untyped-def]
    """Bloqueia o login da pessoa e derruba as sessoes ativas dela."""

    return _alterar_bloqueio(True)


@SegurancaBp.post("/api/usuarios/desbloquear")
@login_required
@exigir_permissao(PermissaoLuftBase.USUARIOS_DESATIVAR)
def desbloquear_usuario():  # type: ignore[no-untyped-def]
    """Devolve o direito de entrar."""

    return _alterar_bloqueio(False)


@SegurancaBp.post("/api/permissoes/limpar-todas")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CONCEDER)
def limpar_todas_regras():  # type: ignore[no-untyped-def]
    """Remove todas as regras diretas do alvo no sistema especificado."""

    validar_csrf_requisicao()
    dados = request.get_json() or {}

    try:
        id_alvo = int(dados.get("id_alvo", -1))
        sistema_id = resolver_escopo_sistema(dados.get("sistema_id"))
    except (TypeError, ValueError):
        return jsonify(status="error", message="Parametros numericos invalidos."), 400

    tipo = str(dados.get("tipo") or "").strip()
    if tipo not in {"Grupo", "Usuario"}:
        return jsonify(status="error", message="Tipo de entidade invalido."), 400
    if id_alvo <= 0:
        return jsonify(status="error", message="ID de alvo invalido."), 400

    modelo: type[PermissaoGrupo | PermissaoUsuario] = (
        PermissaoGrupo if tipo == "Grupo" else PermissaoUsuario
    )
    coluna_alvo = (
        PermissaoGrupo.codigo_usuariogrupo if tipo == "Grupo" else PermissaoUsuario.codigo_usuario
    )

    estado = obter_luftbase()
    with estado.bancos.core.escrita() as sessao:
        regras = list(
            sessao.execute(
                select(modelo)
                .join(Permissao, Permissao.id_permissao == modelo.id_permissao)
                .where(
                    coluna_alvo == id_alvo,
                    Permissao.id_sistema == sistema_id,
                )
            )
            .scalars()
            .all()
        )
        total = len(regras)
        for r in regras:
            sessao.delete(r)

    estado.autorizacao.invalidar_cache()
    registrar_alteracao_auditoria(
        recurso=f"PERMISSAO_{tipo.upper()}",
        id_recurso=str(id_alvo),
        acao="LIMPAR_REGRAS",
        descricao=f"Removidas todas as {total} regra(s) do {tipo.lower()} {id_alvo} no sistema {sistema_id}.",
        dados_anteriores={"id_alvo": id_alvo, "tipo": tipo, "total_removidas": total},
        dados_novos=None,
        severidade=SeveridadeAuditoria.MEDIA,
    )
    return jsonify(
        status="success",
        message=f"{total} regra(s) removida(s). Acessos restaurados para a heranca padrao.",
        total=total,
    )


@SegurancaBp.get("/api/modulos/listar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def listar_modulos_api():  # type: ignore[no-untyped-def]
    """Lista todos os modulos do sistema com total de permissoes vinculadas."""

    sistema_id = resolver_escopo_sistema(request.args.get("sistema_id"))
    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        modulos = list(
            sessao.execute(
                select(Modulo)
                .where(Modulo.id_sistema == sistema_id)
                .order_by(Modulo.ordem_exibicao, Modulo.nome_modulo)
            )
            .scalars()
            .all()
        )
        contagens: dict[int, int] = {
            int(r[0]): int(r[1])
            for r in sessao.execute(
                select(Permissao.id_modulo, func.count(Permissao.id_permissao))
                .where(Permissao.id_sistema == sistema_id)
                .group_by(Permissao.id_modulo)
            ).all()
        }
        dados = [
            {
                "id_modulo": m.id_modulo,
                "codigo_modulo": m.codigo_modulo,
                "nome_modulo": m.nome_modulo,
                "descricao_modulo": m.descricao_modulo or "",
                "icone": m.icone or "ph-cube",
                "ordem_exibicao": m.ordem_exibicao,
                "ativo": m.ativo,
                "total_permissoes": contagens.get(m.id_modulo, 0),
            }
            for m in modulos
        ]
    return jsonify(status="success", data=dados)


@SegurancaBp.post("/api/modulos/salvar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CRIAR)
def salvar_modulo_api():  # type: ignore[no-untyped-def]
    """Cria ou atualiza um modulo funcional."""

    validar_csrf_requisicao()
    payload = request.get_json() if request.is_json else request.form
    sistema_id = resolver_escopo_sistema(payload.get("sistema_id"))
    raw_id = payload.get("id_modulo")
    id_modulo = int(raw_id) if raw_id else None

    codigo = _normalizar_identificador(
        payload.get("codigo_modulo") or payload.get("codigo"), limite=50
    )
    nome = str(payload.get("nome_modulo") or payload.get("nome") or "").strip()
    raw_desc = str(payload.get("descricao_modulo") or payload.get("descricao") or "").strip()
    descricao = raw_desc or None
    icone = str(payload.get("icone") or "").strip() or "ph-squares-four"
    ativo = payload.get("ativo") in (True, "true", "1", 1, "on")
    try:
        ordem = int(payload.get("ordem_exibicao", 10))
    except (TypeError, ValueError):
        ordem = 10

    if not nome:
        return jsonify(status="error", message="Nome do módulo é obrigatório."), 400

    estado = obter_luftbase()
    dados_anteriores: dict[str, object] | None = None
    dados_novos: dict[str, object] = {
        "codigo": codigo,
        "nome": nome,
        "descricao": descricao,
        "icone": icone,
        "ordem": ordem,
        "ativo": ativo,
        "sistema_id": sistema_id,
    }
    with estado.bancos.core.escrita() as sessao:
        if id_modulo:
            modulo = sessao.get(Modulo, id_modulo)
            if modulo is None or modulo.id_sistema != sistema_id:
                return jsonify(status="error", message="Módulo não encontrado."), 404
            dados_anteriores = {
                "codigo": modulo.codigo_modulo,
                "nome": modulo.nome_modulo,
                "descricao": modulo.descricao_modulo,
                "icone": modulo.icone,
                "ordem": modulo.ordem_exibicao,
                "ativo": modulo.ativo,
                "sistema_id": modulo.id_sistema,
            }
            modulo.nome_modulo = nome
            modulo.descricao_modulo = descricao
            modulo.icone = icone
            modulo.ordem_exibicao = ordem
            modulo.ativo = ativo
            msg = f"Módulo '{nome}' atualizado com sucesso."
        else:
            if not codigo:
                return jsonify(status="error", message="Código do módulo é obrigatório."), 400
            existe = sessao.scalar(
                select(Modulo.id_modulo).where(
                    Modulo.id_sistema == sistema_id, Modulo.codigo_modulo == codigo
                )
            )
            if existe is not None:
                return (
                    jsonify(
                        status="error",
                        message=f"Já existe um módulo com o código '{codigo}'.",
                    ),
                    409,
                )
            novo = Modulo(
                id_sistema=sistema_id,
                codigo_modulo=codigo,
                nome_modulo=nome,
                descricao_modulo=descricao,
                icone=icone,
                ordem_exibicao=ordem,
                ativo=ativo,
            )
            sessao.add(novo)
            sessao.flush()
            id_modulo = novo.id_modulo
            msg = f"Módulo '{nome}' criado com sucesso."

    estado.autorizacao.invalidar_cache()
    registrar_alteracao_auditoria(
        recurso="MODULO",
        id_recurso=str(id_modulo),
        acao="ATUALIZAR_MODULO" if raw_id else "CRIAR_MODULO",
        descricao=msg,
        dados_anteriores=dados_anteriores,
        dados_novos=dados_novos,
        severidade=SeveridadeAuditoria.BAIXA,
    )
    if request.is_json:
        return jsonify(status="success", message=msg, data={"id_modulo": id_modulo})
    return redirect(url_for("Seguranca.visualizar_gerenciador", sistema_id=sistema_id))


@SegurancaBp.get("/api/modulos/<int:id_modulo>/estrutura")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
def obter_estrutura_modulo(id_modulo):  # type: ignore[no-untyped-def]
    """Retorna os recursos existentes e as permissoes candidatas a pai no modulo."""

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        modulo = sessao.get(Modulo, id_modulo)
        if modulo is None:
            return jsonify(status="error", message="Módulo não encontrado."), 404
        sistema_id = modulo.id_sistema
        resolver_escopo_sistema(sistema_id)

        recursos = list(
            sessao.execute(
                select(Permissao.recurso)
                .where(Permissao.id_modulo == id_modulo, Permissao.id_sistema == sistema_id)
                .distinct()
                .order_by(Permissao.recurso)
            )
            .scalars()
            .all()
        )

        permissoes_modulo = list(
            sessao.execute(
                select(Permissao)
                .where(
                    Permissao.id_sistema == sistema_id,
                    (Permissao.id_modulo == id_modulo)
                    | (Permissao.eh_acesso_sistema.is_(True))
                    | (Permissao.acao == "ADMINISTRAR"),
                )
                .order_by(Permissao.id_modulo, Permissao.chave_permissao)
            )
            .scalars()
            .all()
        )
        niveis = _calcular_niveis(permissoes_modulo)

        chave_gestor_modulo = f"{modulo.codigo_modulo}.MODULO.GERENCIAR"
        candidatas = []
        for p in permissoes_modulo:
            eh_gestor = p.chave_permissao == chave_gestor_modulo
            eh_admin_geral = p.acao == "ADMINISTRAR" and p.id_permissao_pai is None
            candidatas.append(
                {
                    "id_permissao": p.id_permissao,
                    "chave_permissao": p.chave_permissao,
                    "descricao_permissao": p.descricao_permissao,
                    "modulo": modulo.codigo_modulo if p.id_modulo == id_modulo else "PLATAFORMA",
                    "nivel": niveis.get(p.id_permissao, 0),
                    "recomendado": eh_gestor,
                    "eh_admin_geral": eh_admin_geral,
                }
            )

        candidatas.sort(
            key=lambda x: (
                not x["recomendado"],
                not x["eh_admin_geral"],
                x["nivel"],
                x["chave_permissao"],
            )
        )

        modulo_info = {
            "id_modulo": modulo.id_modulo,
            "codigo_modulo": modulo.codigo_modulo,
            "nome_modulo": modulo.nome_modulo,
        }

    return jsonify(
        status="success",
        data={
            "modulo": modulo_info,
            "recursos": recursos,
            "permissoes_pai": candidatas,
        },
    )


@SegurancaBp.post("/modulos/criar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CRIAR)
def criar_modulo():  # type: ignore[no-untyped-def]
    """Cadastra um modulo funcional no sistema autorizado."""

    return salvar_modulo_api()


@SegurancaBp.post("/permissoes/criar")
@login_required
@exigir_permissao(PermissaoLuftBase.PERMISSOES_CRIAR)
def criar_nova_permissao():  # type: ignore[no-untyped-def]
    """Cria uma permissao no padrao MODULO.RECURSO.ACAO."""

    validar_csrf_requisicao()
    payload = request.get_json() if request.is_json else request.form
    sistema_id = resolver_escopo_sistema(payload.get("sistema_id"))
    recurso = _normalizar_identificador(payload.get("recurso"), limite=80)
    acao = _normalizar_identificador(payload.get("acao"), limite=30)
    try:
        id_modulo = int(payload.get("id_modulo", ""))
        pai_bruto = payload.get("id_permissao_pai")
        id_pai = int(pai_bruto) if pai_bruto else None
    except (TypeError, ValueError):
        return jsonify(status="error", message="Modulo ou permissao pai invalida."), 400
    if not recurso or acao not in ACOES_PERMISSAO:
        return jsonify(status="error", message="Recurso ou acao invalida."), 400

    estado = obter_luftbase()
    with estado.bancos.core.escrita() as sessao:
        modulo = sessao.get(Modulo, id_modulo)
        if modulo is None or modulo.id_sistema != sistema_id:
            return jsonify(status="error", message="Modulo nao pertence ao sistema."), 400
        if id_pai is not None:
            pai = sessao.get(Permissao, id_pai)
            if pai is None or pai.id_sistema != sistema_id:
                return jsonify(status="error", message="Permissao pai invalida."), 400
        chave = f"{modulo.codigo_modulo}.{recurso}.{acao}"
        existe = sessao.scalar(
            select(Permissao.id_permissao).where(
                Permissao.id_sistema == sistema_id,
                Permissao.chave_permissao == chave,
            )
        )
        if existe is not None:
            return jsonify(status="error", message=f"A permissão '{chave}' já existe."), 409
        sensivel = payload.get("sensivel") in (True, "1", "true", 1, "on")
        sessao.add(
            Permissao(
                id_sistema=sistema_id,
                id_modulo=id_modulo,
                id_permissao_pai=id_pai,
                chave_permissao=chave,
                recurso=recurso,
                acao=acao,
                descricao_permissao=str(payload.get("descricao") or "").strip() or chave,
                ativo=True,
                sensivel=sensivel,
            )
        )
    estado.autorizacao.invalidar_cache()
    registrar_alteracao_auditoria(
        recurso="PERMISSAO",
        id_recurso=chave,
        acao="CRIAR_PERMISSAO",
        descricao=f"Permissão '{chave}' criada com sucesso.",
        dados_anteriores=None,
        dados_novos={
            "chave": chave,
            "recurso": recurso,
            "acao": acao,
            "id_modulo": id_modulo,
            "id_sistema": sistema_id,
            "id_permissao_pai": id_pai,
            "sensivel": sensivel,
        },
        severidade=SeveridadeAuditoria.MEDIA,
    )
    if request.is_json:
        return jsonify(
            status="success",
            message=f"Permissão '{chave}' criada com sucesso.",
            data={"chave": chave},
        )
    return redirect(url_for("Seguranca.visualizar_gerenciador", sistema_id=sistema_id))


def garantir_usuario_no_core(codigo_usuario: int) -> bool:
    """Cria o cadastro em `core.tb_usuario` de quem ainda nao fez login (dados do diretorio).

    A regra de permissao de usuario tem FK para `tb_usuario`; sem esta etapa, dar uma permissao
    a alguem que ainda nao entrou no LuftBase falhava com violacao de chave estrangeira. No
    primeiro login real o cadastro e completado (nome, e-mail e grupo vindos do diretorio).
    Devolve False quando o usuario nao existe nem no diretorio.
    """

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        existe = sessao.execute(
            select(Usuario.codigo_usuario).where(Usuario.codigo_usuario == codigo_usuario)
        ).first()
    if existe is not None:
        return True
    try:
        with estado.bancos.diretorio.leitura() as sessao_dir:
            origem = sessao_dir.get(UsuarioDiretorio, codigo_usuario)
            if origem is None or not (origem.login or "").strip():
                return False
            grupo = origem.grupo
            dados = {
                "codigo_usuario": codigo_usuario,
                "login_usuario": (origem.login or "").strip(),
                "nome_usuario": (origem.nome_completo or origem.login or "").strip(),
                "email_usuario": (origem.email or "").strip() or None,
                "codigo_usuariogrupo": origem.id_grupo,
                "sigla_usuariogrupo": (grupo.sigla or "").strip() or None if grupo else None,
            }
    except SQLAlchemyError:
        logger.exception("Falha ao ler o usuario %s no diretorio", codigo_usuario)
        return False
    estado.usuarios_core.garantir_usuario_do_diretorio(**dados)
    return True


def _normalizar_identificador(valor: object, *, limite: int) -> str:
    texto = re.sub(r"[^A-Z0-9_]+", "_", str(valor or "").upper().strip()).strip("_")
    if len(texto) > limite or not _IDENTIFICADOR.fullmatch(texto):
        return ""
    return texto


__all__ = ["SegurancaBp", "visualizar_gerenciador"]
