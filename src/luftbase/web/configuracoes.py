"""Módulo web de Painel de Controle, Governança e Configurações do LuftBase."""

from __future__ import annotations

import contextlib
import logging
import re
from dataclasses import dataclass
from typing import cast

logger = logging.getLogger(__name__)

from flask import Blueprint, abort, current_app, jsonify, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from luftbase.autorizacao.catalogo import PermissaoLuftBase
from luftbase.autorizacao.web import (
    consultar_permissoes,
    exigir_alguma_permissao,
    exigir_permissao,
    tem_permissao,
)
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.provisionamento_sistema import (
    CredenciaisOperador,
    ErroProvisionamento,
    PlanoSistema,
    ProvisionadorSistema,
    derivar_plano,
    destino_do_estado,
)
from luftbase.infraestrutura.servicos_host import (
    ACOES,
    ErroServicoHost,
    StatusServico,
    consultar_status,
    executar_acao,
    nome_do_servico,
    plataforma_do_host,
)
from luftbase.interface.parametros import ParametroAplicacao
from luftbase.interface.web import validar_csrf_requisicao
from luftbase.persistencia.core.seguranca import Modulo, Permissao, PermissaoGrupo, Sistema
from luftbase.plataforma import obter_luftbase
from luftbase.web.escopo import (
    eh_sistema_master,
    resolver_escopo_sistema,
    sistema_aplicacao_atual,
    usuario_autenticado_atual,
    validar_sistema_alteravel_manutencao,
)

ConfiguracoesBp = Blueprint("Configuracoes", __name__, url_prefix="/configuracoes")
AdminBp = Blueprint("Admin", __name__, url_prefix="/admin")

_PERMISSOES_ENTRADA_PAINEL = (
    PermissaoLuftBase.CONFIGURACOES_VISUALIZAR,
    PermissaoLuftBase.PERMISSOES_VISUALIZAR,
    PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
    PermissaoLuftBase.SISTEMAS_VISUALIZAR,
    PermissaoLuftBase.SERVICOS_VISUALIZAR,
    PermissaoLuftBase.COMUNICADOS_VISUALIZAR,
    PermissaoLuftBase.ATUALIZACOES_VISUALIZAR,
    PermissaoLuftBase.AUDITORIA_VISUALIZAR,
)


@dataclass(frozen=True, slots=True)
class SistemaAdaptador:
    """Adaptador com propriedades PascalCase e snake_case para o template."""

    id_sistema: int
    nome_sistema: str
    descricao_sistema: str | None
    ativo: bool
    em_manutencao: bool
    icone: str | None
    link: str | None
    categoria: str = "APLICACAO"
    ordem_exibicao: int = 0
    cor: str | None = None
    url_saude: str | None = None
    responsavel: str | None = None
    contato_suporte: str | None = None
    permissao_base: str | None = None
    schema_aplicacao: str | None = None

    @property
    def Id_Sistema(self) -> int:
        return self.id_sistema

    @property
    def Nome_Sistema(self) -> str:
        return self.nome_sistema

    @property
    def Descricao_Sistema(self) -> str | None:
        return self.descricao_sistema

    @property
    def Ativo(self) -> bool:
        return self.ativo

    @property
    def Em_Manutencao(self) -> bool:
        return self.em_manutencao

    @property
    def Icone(self) -> str | None:
        return self.icone

    @property
    def Link(self) -> str | None:
        return self.link

    @property
    def Categoria(self) -> str:
        return self.categoria

    @property
    def Ordem_Exibicao(self) -> int:
        return self.ordem_exibicao

    @property
    def Cor(self) -> str | None:
        return self.cor

    @property
    def Url_Saude(self) -> str | None:
        return self.url_saude

    @property
    def Responsavel(self) -> str | None:
        return self.responsavel

    @property
    def Contato_Suporte(self) -> str | None:
        return self.contato_suporte

    @property
    def Permissao_Base(self) -> str | None:
        return self.permissao_base

    @property
    def Schema_Aplicacao(self) -> str | None:
        return self.schema_aplicacao


def _parametros_visiveis(parametros: tuple[ParametroAplicacao, ...]) -> list[dict[str, str]]:
    """Cartoes da aba Configuracoes Gerais que o usuario pode abrir, com a URL ja resolvida."""

    if not parametros:
        return []
    chaves = tuple(p.permissao for p in parametros if p.permissao)
    decisoes = consultar_permissoes(chaves) if chaves else {}
    visiveis: list[dict[str, str]] = []
    for parametro in parametros:
        if parametro.permissao and not decisoes.get(parametro.permissao.strip().upper(), False):
            continue
        try:
            url = url_for(parametro.endpoint)
        except Exception:
            logger.warning(
                "Parametro '%s' ignorado: rota %r inexistente.",
                parametro.titulo,
                parametro.endpoint,
            )
            continue
        visiveis.append(
            {
                "titulo": parametro.titulo,
                "descricao": parametro.descricao,
                "icone": parametro.icone,
                "acao": parametro.acao,
                "url": url,
            }
        )
    return visiveis


def _renderizar_painel_controle() -> str:
    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        sistemas_db = (
            sessao.execute(
                select(Sistema).order_by(Sistema.ordem_exibicao.asc(), Sistema.id_sistema.asc())
            )
            .scalars()
            .all()
        )
        perm_base_rows = sessao.execute(
            select(Permissao.id_sistema, Permissao.chave_permissao).where(
                Permissao.eh_acesso_sistema.is_(True), Permissao.ativo.is_(True)
            )
        ).all()
        mapa_permissoes_base = {row[0]: row[1] for row in perm_base_rows}

        sistemas = [
            SistemaAdaptador(
                id_sistema=s.id_sistema,
                nome_sistema=s.nome_sistema,
                descricao_sistema=s.descricao_sistema,
                ativo=bool(s.ativo is not False),
                em_manutencao=bool(s.em_manutencao),
                icone=s.icone or "ph-bold ph-app-window",
                link=s.link,
                categoria=s.categoria or "APLICACAO",
                ordem_exibicao=s.ordem_exibicao or 0,
                cor=s.cor,
                url_saude=s.url_saude,
                responsavel=s.responsavel,
                contato_suporte=s.contato_suporte,
                permissao_base=mapa_permissoes_base.get(s.id_sistema),
                schema_aplicacao=s.schema_aplicacao,
            )
            for s in sistemas_db
        ]

    # Permite que a aplicação sobreponha o template caso tenha customização local
    template_alvo = "luftbase/seguranca/painel_admin.html"
    for candidato in ("Pages/Configs/Configuracoes.html", "Pages/Configuracoes.html"):
        try:
            current_app.jinja_env.get_template(candidato)
            template_alvo = candidato
            break
        except Exception:
            pass

    try:
        url_comunicados = url_for("LuftPublicacoes.painel_comunicados")
    except Exception:
        url_comunicados = "/publicacoes/comunicados"

    try:
        url_atualizacoes = url_for("LuftPublicacoes.painel_atualizacoes")
    except Exception:
        url_atualizacoes = "/publicacoes/atualizacoes"

    id_sistema_atual = sistema_aplicacao_atual()
    is_master = eh_sistema_master()
    decisoes = consultar_permissoes(
        (
            PermissaoLuftBase.CONFIGURACOES_VISUALIZAR,
            PermissaoLuftBase.PERMISSOES_VISUALIZAR,
            PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
            PermissaoLuftBase.VARIAVEIS_EDITAR,
            PermissaoLuftBase.SISTEMAS_VISUALIZAR,
            PermissaoLuftBase.SISTEMAS_EDITAR,
            PermissaoLuftBase.SISTEMAS_CRIAR,
            PermissaoLuftBase.SERVICOS_VISUALIZAR,
            PermissaoLuftBase.SERVICOS_EXECUTAR,
            PermissaoLuftBase.COMUNICADOS_VISUALIZAR,
            PermissaoLuftBase.ATUALIZACOES_VISUALIZAR,
            PermissaoLuftBase.MANUTENCAO_GERENCIAR,
            PermissaoLuftBase.AUDITORIA_VISUALIZAR,
            PermissaoLuftBase.AUDITORIA_EXPORTAR,
            PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR,
        )
    )

    sistemas_exibidos = (
        sistemas if is_master else [s for s in sistemas if s.id_sistema == id_sistema_atual]
    )
    parametros_aplicacao = _parametros_visiveis(estado.parametros)

    return render_template(
        template_alvo,
        sistemas=sistemas_exibidos,
        is_master=is_master,
        sistema_atual_id=id_sistema_atual,
        pode_ver_configuracoes=bool(decisoes.get(PermissaoLuftBase.CONFIGURACOES_VISUALIZAR)),
        pode_ver_seguranca=bool(decisoes.get(PermissaoLuftBase.PERMISSOES_VISUALIZAR)),
        pode_ver_ambiente=any(
            bool(decisoes.get(chave))
            for chave in (
                PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
                PermissaoLuftBase.SISTEMAS_VISUALIZAR,
                PermissaoLuftBase.SERVICOS_VISUALIZAR,
            )
        ),
        pode_ver_sistemas=bool(decisoes.get(PermissaoLuftBase.SISTEMAS_VISUALIZAR)),
        pode_editar_sistemas=bool(decisoes.get(PermissaoLuftBase.SISTEMAS_EDITAR)),
        pode_editar_ambiente=bool(decisoes.get(PermissaoLuftBase.VARIAVEIS_EDITAR)),
        pode_ver_variaveis=bool(decisoes.get(PermissaoLuftBase.VARIAVEIS_VISUALIZAR)),
        pode_ver_servicos=bool(decisoes.get(PermissaoLuftBase.SERVICOS_VISUALIZAR)),
        pode_executar_servicos=bool(decisoes.get(PermissaoLuftBase.SERVICOS_EXECUTAR)),
        pode_criar_sistema=bool(decisoes.get(PermissaoLuftBase.SISTEMAS_CRIAR)),
        pode_ver_comunicados=bool(decisoes.get(PermissaoLuftBase.COMUNICADOS_VISUALIZAR)),
        pode_ver_atualizacoes=bool(decisoes.get(PermissaoLuftBase.ATUALIZACOES_VISUALIZAR)),
        pode_gerenciar_manutencao=bool(decisoes.get(PermissaoLuftBase.MANUTENCAO_GERENCIAR)),
        pode_ver_auditoria=bool(decisoes.get(PermissaoLuftBase.AUDITORIA_VISUALIZAR)),
        pode_exportar_auditoria=bool(decisoes.get(PermissaoLuftBase.AUDITORIA_EXPORTAR)),
        pode_ver_dados_sensiveis_auditoria=bool(
            decisoes.get(PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR)
        ),
        parametros_aplicacao=parametros_aplicacao,
        url_comunicados=url_comunicados,
        url_atualizacoes=url_atualizacoes,
        projetos_operacao=[],
        servicos_operacao=_servicos_operacao(),
    )


@ConfiguracoesBp.get("")
@ConfiguracoesBp.get("/painel")
@login_required
@exigir_alguma_permissao(_PERMISSOES_ENTRADA_PAINEL)
def visualizar_painel():  # type: ignore[no-untyped-def]
    """Renderiza o Painel de Controle oficial com governança corporativa."""

    return _renderizar_painel_controle()


@AdminBp.get("")
@AdminBp.get("/painel")
@login_required
@exigir_alguma_permissao(_PERMISSOES_ENTRADA_PAINEL)
def visualizar_painel_admin():  # type: ignore[no-untyped-def]
    """Alias retrocompatível para o Painel de Controle."""

    return _renderizar_painel_controle()


@ConfiguracoesBp.post("/api/configuracoes/manutencao/alternar")
@AdminBp.post("/api/manutencao/alternar")
@login_required
@exigir_permissao(PermissaoLuftBase.MANUTENCAO_GERENCIAR)
def api_manutencao_alternar():  # type: ignore[no-untyped-def]
    """Ativa ou desativa a manutenção de um sistema individual com validação de escopo e CSRF."""

    validar_csrf_requisicao()

    dados = request.get_json() or {}
    try:
        id_sistema = resolver_escopo_sistema(dados.get("IdSistema", -1))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "ID do sistema inválido."}), 400

    validar_sistema_alteravel_manutencao(id_sistema)

    em_manutencao = bool(dados.get("EmManutencao", False))
    estado = obter_luftbase()
    em_manutencao_anterior: bool | None = None
    with estado.bancos.core.escrita() as sessao:
        sistema = sessao.get(Sistema, id_sistema)
        if not sistema:
            return jsonify({"status": "error", "message": "Sistema não encontrado."}), 404
        em_manutencao_anterior = sistema.em_manutencao
        sistema.em_manutencao = em_manutencao

    status_texto = "ativada" if em_manutencao else "desativada"
    from luftbase.web.manutencao import invalidar_cache_manutencao

    invalidar_cache_manutencao(id_sistema)
    estado.auditoria.registrar_alteracao(
        recurso="SISTEMA",
        id_recurso=id_sistema,
        acao="ALTERNAR_MANUTENCAO",
        descricao=f"Manutenção do sistema {id_sistema} {status_texto}.",
        dados_anteriores={"em_manutencao": em_manutencao_anterior},
        dados_novos={"em_manutencao": em_manutencao},
    )
    return jsonify(
        {
            "status": "success",
            "message": f"Manutenção {status_texto} com sucesso.",
        }
    )


@ConfiguracoesBp.post("/api/configuracoes/manutencao/lote")
@AdminBp.post("/api/manutencao/lote")
@login_required
@exigir_permissao(PermissaoLuftBase.MANUTENCAO_GERENCIAR)
def api_manutencao_lote():  # type: ignore[no-untyped-def]
    """Alterna manutenção em lote (exclusivo para escopo master)."""

    validar_csrf_requisicao()

    if not eh_sistema_master():
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Operações de manutenção em lote são restritas ao sistema master.",
                }
            ),
            403,
        )

    dados = request.get_json() or {}
    ids = dados.get("IdsSistemas", [])
    em_manutencao = bool(dados.get("EmManutencao", False))
    ids_limpos = [int(i) for i in ids if str(i).strip() not in ("0", "")]
    if not ids_limpos:
        return (
            jsonify({"status": "error", "message": "Nenhum sistema alterável informado."}),
            400,
        )

    estado = obter_luftbase()
    with estado.bancos.core.escrita() as sessao:
        sistemas = (
            sessao.execute(select(Sistema).where(Sistema.id_sistema.in_(ids_limpos)))
            .scalars()
            .all()
        )
        for s in sistemas:
            if s.id_sistema != 0:
                s.em_manutencao = em_manutencao

    status_texto = "ativada" if em_manutencao else "desativada"
    from luftbase.web.manutencao import invalidar_cache_manutencao

    invalidar_cache_manutencao()
    estado.auditoria.registrar_alteracao(
        recurso="SISTEMA",
        id_recurso="LOTE",
        acao="ALTERNAR_MANUTENCAO_LOTE",
        descricao=f"Manutenção em lote {status_texto} para {len(ids_limpos)} sistemas.",
        dados_anteriores={"em_manutencao": not em_manutencao, "sistemas": ids_limpos},
        dados_novos={"em_manutencao": em_manutencao, "sistemas": ids_limpos},
    )
    return jsonify(
        {
            "status": "success",
            "message": f"Manutenção em lote {status_texto} com sucesso.",
        }
    )


@ConfiguracoesBp.post("/api/configuracoes/sistema/atualizar")
@AdminBp.post("/api/sistema/atualizar")
@login_required
@exigir_permissao(PermissaoLuftBase.SISTEMAS_EDITAR)
def api_sistema_atualizar():  # type: ignore[no-untyped-def]
    """Atualiza todos os metadados cadastrais do sistema com validação de escopo e CSRF."""

    validar_csrf_requisicao()

    dados = request.get_json() or {}
    try:
        id_sistema = resolver_escopo_sistema(dados.get("IdSistema", -1))
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "ID do sistema inválido."}), 400

    if id_sistema == 0 and not eh_sistema_master():
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "O sistema base (ID 0) permite somente consulta.",
                }
            ),
            403,
        )

    estado = obter_luftbase()
    anteriores: dict[str, Any] = {}
    novos: dict[str, Any] = {}
    with estado.bancos.core.escrita() as sessao:
        sistema = sessao.get(Sistema, id_sistema)
        if not sistema:
            return jsonify({"status": "error", "message": "Sistema não encontrado."}), 404

        anteriores = {
            "nome_sistema": sistema.nome_sistema,
            "descricao_sistema": sistema.descricao_sistema,
            "categoria": sistema.categoria,
            "icone": sistema.icone,
            "cor": sistema.cor,
            "link": sistema.link,
            "url_saude": sistema.url_saude,
            "responsavel": sistema.responsavel,
            "contato_suporte": sistema.contato_suporte,
            "ordem_exibicao": sistema.ordem_exibicao,
            "schema_aplicacao": sistema.schema_aplicacao,
            "ativo": sistema.ativo,
            "em_manutencao": sistema.em_manutencao,
        }

        if "Nome" in dados:
            nome = str(dados["Nome"]).strip()
            if not nome:
                return jsonify({"status": "error", "message": "Nome não pode ser vazio."}), 400
            existente_nome = (
                sessao.execute(
                    select(Sistema).where(
                        func.lower(Sistema.nome_sistema) == nome.lower(),
                        Sistema.id_sistema != id_sistema,
                    )
                )
                .scalars()
                .first()
            )
            if existente_nome:
                return (
                    jsonify(
                        {
                            "status": "error",
                            "message": f"Já existe outro sistema cadastrado com o nome '{nome}'.",
                        }
                    ),
                    409,
                )
            sistema.nome_sistema = nome

        if "Descricao" in dados:
            sistema.descricao_sistema = str(dados["Descricao"]).strip() or None
        if "Categoria" in dados and id_sistema != 0:
            cat = str(dados["Categoria"]).strip().upper()
            if cat in ("HUB", "APLICACAO", "SERVICO"):
                sistema.categoria = cat
        if "Icone" in dados:
            sistema.icone = str(dados["Icone"]).strip() or "ph-bold ph-app-window"
        if "Cor" in dados:
            sistema.cor = str(dados["Cor"]).strip() or None
        if "Link" in dados:
            sistema.link = str(dados["Link"]).strip() or None
        if "UrlSaude" in dados:
            sistema.url_saude = str(dados["UrlSaude"]).strip() or None
        if "Responsavel" in dados:
            sistema.responsavel = str(dados["Responsavel"]).strip() or None
        if "ContatoSuporte" in dados:
            sistema.contato_suporte = str(dados["ContatoSuporte"]).strip() or None
        if "OrdemExibicao" in dados and id_sistema != 0:
            with contextlib.suppress(TypeError, ValueError):
                sistema.ordem_exibicao = max(0, int(dados["OrdemExibicao"]))
        if "Ativo" in dados and id_sistema != 0 and bool(dados["Ativo"]) != sistema.ativo:
            # Descontinuar tira o sistema do ar para todos; exige permissao propria.
            if not tem_permissao(PermissaoLuftBase.SISTEMAS_DESATIVAR):
                abort(403)
            sistema.ativo = bool(dados["Ativo"])
        if "EmManutencao" in dados and id_sistema != 0:
            sistema.em_manutencao = bool(dados["EmManutencao"])
        if ("SchemaAplicacao" in dados or "schema_aplicacao" in dados) and id_sistema != 0:
            val_schema = (
                str(dados.get("SchemaAplicacao") or dados.get("schema_aplicacao") or "")
                .strip()
                .lower()
                or None
            )
            if val_schema:
                if not re.match(r"^[a-z_][a-z0-9_]{0,62}$", val_schema):
                    return jsonify({"status": "error", "message": "Nome do schema inválido."}), 400
                try:
                    from luftbase.cli.bootstrap import provisionar_schema_sistema

                    # Savepoint: uma falha de DDL nao pode abortar a transacao da sessao.
                    with sessao.begin_nested():
                        provisionar_schema_sistema(
                            sessao.connection(), id_sistema=id_sistema, schema_aplicacao=val_schema
                        )
                except Exception as erro_s:
                    logger.warning("Falha ao provisionar schema %s: %s", val_schema, erro_s)
            sistema.schema_aplicacao = val_schema

        novos = {
            "nome_sistema": sistema.nome_sistema,
            "descricao_sistema": sistema.descricao_sistema,
            "categoria": sistema.categoria,
            "icone": sistema.icone,
            "cor": sistema.cor,
            "link": sistema.link,
            "url_saude": sistema.url_saude,
            "responsavel": sistema.responsavel,
            "contato_suporte": sistema.contato_suporte,
            "ordem_exibicao": sistema.ordem_exibicao,
            "schema_aplicacao": sistema.schema_aplicacao,
            "ativo": sistema.ativo,
            "em_manutencao": sistema.em_manutencao,
        }

    from luftbase.web.manutencao import invalidar_cache_manutencao

    estado.autorizacao.invalidar_cache()
    invalidar_cache_manutencao(id_sistema)
    estado.auditoria.registrar_alteracao(
        recurso="SISTEMA",
        id_recurso=id_sistema,
        acao="ATUALIZAR_SISTEMA",
        descricao=(
            f"Atualizadas configurações do sistema '{novos.get('nome_sistema')}' (ID {id_sistema})."
        ),
        dados_anteriores=anteriores,
        dados_novos=novos,
    )

    return jsonify(
        {
            "status": "success",
            "message": "Configurações do sistema atualizadas com sucesso.",
        }
    )


_CATEGORIAS_SISTEMA = ("HUB", "APLICACAO", "SERVICO")
_REGEX_SCHEMA = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_REGEX_ICONE = re.compile(r"^ph(-(bold|fill|light|thin|duotone))? ph-[a-z0-9-]+$")
_REGEX_COR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_REGEX_CHAVE_PERMISSAO = re.compile(r"^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*){1,}$")
_SCHEMAS_RESERVADOS = ("core", "public", "information_schema")
_SQLSTATE_SEM_PRIVILEGIO = "42501"


class FalhaCadastroSistema(Exception):
    """Interrompe o cadastro dentro da transacao, forcando o rollback de todas as etapas."""

    def __init__(
        self, mensagem: str, erros: dict[str, str] | None = None, status: int = 422
    ) -> None:
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.erros = erros or {}
        self.status = status


def prefixo_chave_sistema(nome: str) -> str:
    """Deriva o prefixo da chave de permissao base a partir do nome do sistema.

    A chave precisa comecar por letra (constraint de ``tb_permissao``); nomes
    iniciados por digito recebem o prefixo ``SISTEMA_``.
    """

    prefixo = re.sub(r"[^A-Za-z0-9_]+", "_", nome).strip("_").upper()
    if prefixo and not prefixo[0].isalpha():
        prefixo = f"SISTEMA_{prefixo}"
    return prefixo[:50]


def _texto_opcional(
    dados: dict[str, object], campo: str, rotulo: str, limite: int, erros: dict[str, str]
) -> str | None:
    valor = str(dados.get(campo) or "").strip()
    if len(valor) > limite:
        erros[campo] = f"{rotulo} aceita no máximo {limite} caracteres (informado: {len(valor)})."
    return valor or None


def _endereco_opcional(
    dados: dict[str, object], campo: str, rotulo: str, erros: dict[str, str]
) -> str | None:
    valor = _texto_opcional(dados, campo, rotulo, 500, erros)
    if valor and campo not in erros:
        if " " in valor:
            erros[campo] = f"{rotulo} não pode conter espaços."
        elif not (valor.startswith("/") or re.match(r"^https?://[^/\s]+", valor)):
            erros[campo] = (
                f"{rotulo} deve ser uma rota iniciada por '/' (ex: /Luft-Integrador/) "
                "ou uma URL completa iniciada por http:// ou https://."
            )
    return valor


def validar_payload_novo_sistema(
    dados: dict[str, object],
) -> tuple[dict[str, object], dict[str, str]]:
    """Valida o cadastro de sistema e devolve os valores normalizados e os erros por campo.

    As chaves de ``erros`` sao os nomes dos campos do payload, para que a tela
    destaque exatamente o campo com problema.
    """

    erros: dict[str, str] = {}
    valores: dict[str, object] = {}

    id_sistema: int | None = None
    dado_id = dados.get("IdSistema")
    if dado_id not in (None, ""):
        try:
            id_sistema = int(str(dado_id).strip())
        except (TypeError, ValueError):
            erros["IdSistema"] = "O ID manual deve ser um número inteiro (ex: 12)."
        else:
            if id_sistema <= 0:
                erros["IdSistema"] = (
                    "O ID manual deve ser maior que zero. O ID 0 é reservado ao sistema base."
                )
    valores["id_sistema"] = id_sistema if "IdSistema" not in erros else None

    nome = str(dados.get("Nome") or "").strip()
    if not nome:
        erros["Nome"] = "Informe o nome do sistema. Este campo é obrigatório."
    elif len(nome) > 100:
        erros["Nome"] = f"O nome aceita no máximo 100 caracteres (informado: {len(nome)})."
    elif not prefixo_chave_sistema(nome):
        erros["Nome"] = "O nome precisa conter ao menos uma letra ou número."
    valores["nome_sistema"] = nome

    categoria = str(dados.get("Categoria") or "APLICACAO").strip().upper()
    if categoria not in _CATEGORIAS_SISTEMA:
        erros["Categoria"] = "Categoria inválida. Escolha Aplicação, Serviço ou Hub."
    valores["categoria"] = categoria

    ordem_bruta = dados.get("OrdemExibicao")
    ordem = 0
    if ordem_bruta not in (None, ""):
        try:
            ordem = int(str(ordem_bruta).strip())
        except (TypeError, ValueError):
            erros["OrdemExibicao"] = "A ordem deve ser um número inteiro."
        else:
            if not 0 <= ordem <= 32767:
                erros["OrdemExibicao"] = "A ordem deve estar entre 0 e 32767."
    valores["ordem_exibicao"] = ordem

    valores["descricao_sistema"] = _texto_opcional(dados, "Descricao", "A descrição", 500, erros)

    icone = _texto_opcional(dados, "Icone", "O ícone", 255, erros) or "ph-bold ph-app-window"
    if "Icone" not in erros and not _REGEX_ICONE.match(icone):
        erros["Icone"] = (
            "Ícone inválido. Use o formato Phosphor 'ph-bold ph-nome-do-icone' "
            "ou clique em 'Escolher...'."
        )
    valores["icone"] = icone

    cor = _texto_opcional(dados, "Cor", "A cor", 30, erros)
    if cor and "Cor" not in erros and not _REGEX_COR.match(cor):
        erros["Cor"] = "Cor inválida. Use hexadecimal no formato #RRGGBB (ex: #2563eb)."
    valores["cor"] = cor

    valores["link"] = _endereco_opcional(dados, "Link", "O link / rota base", erros)
    valores["url_saude"] = _endereco_opcional(dados, "UrlSaude", "A URL de saúde", erros)
    valores["responsavel"] = _texto_opcional(dados, "Responsavel", "O responsável", 150, erros)
    valores["contato_suporte"] = _texto_opcional(
        dados, "ContatoSuporte", "O contato de suporte", 255, erros
    )

    schema = (
        str(dados.get("SchemaAplicacao") or dados.get("schema_aplicacao") or "").strip() or None
    )
    if schema:
        if schema != schema.lower():
            erros["SchemaAplicacao"] = (
                f"O schema deve ser todo em minúsculas (use '{schema.lower()}')."
            )
        elif not _REGEX_SCHEMA.match(schema):
            erros["SchemaAplicacao"] = (
                "Schema inválido. Comece com letra ou '_' e use apenas letras minúsculas, "
                "números e '_' (máximo 63 caracteres). Hífens e espaços não são aceitos."
            )
        elif schema in _SCHEMAS_RESERVADOS or schema.startswith("pg_"):
            erros["SchemaAplicacao"] = (
                f"O schema '{schema}' é reservado da plataforma/PostgreSQL. "
                "Informe um schema próprio do sistema ou deixe em branco."
            )
    valores["schema_aplicacao"] = schema

    valores["ativo"] = bool(dados.get("Ativo", True))
    valores["em_manutencao"] = bool(dados.get("EmManutencao", False))

    chave_informada = str(dados.get("ChavePermissaoBase") or "").strip().upper()
    if chave_informada and not _REGEX_CHAVE_PERMISSAO.match(chave_informada):
        erros["ChavePermissaoBase"] = (
            "Chave de permissão inválida. Use o formato PREFIXO.RECURSO.ACAO em maiúsculas."
        )
    if chave_informada:
        valores["chave_permissao_base"] = chave_informada
    elif "Nome" not in erros:
        valores["chave_permissao_base"] = f"{prefixo_chave_sistema(nome)}.SISTEMA.ACESSAR"
    else:
        valores["chave_permissao_base"] = None

    return valores, erros


def _resposta_erro_cadastro(  # type: ignore[no-untyped-def]
    mensagem: str, erros: dict[str, str] | None, status: int
):
    return jsonify({"status": "error", "message": mensagem, "erros": erros or {}}), status


def _ler_credenciais_operador(
    dados: dict[str, object],
) -> tuple[CredenciaisOperador | None, dict[str, str]]:
    """Le token/usuario/senha do modal; os valores vivem so nesta requisicao."""

    erros: dict[str, str] = {}
    token = str(dados.get("TokenOperadorVault") or "").strip()
    usuario = str(dados.get("UsuarioBanco") or "").strip()
    senha = str(dados.get("SenhaBanco") or "")
    if not token:
        erros["TokenOperadorVault"] = "Informe o token de operador do Vault."
    if not usuario:
        erros["UsuarioBanco"] = "Informe o usuário administrativo do PostgreSQL (ex: admin)."
    if not senha:
        erros["SenhaBanco"] = "Informe a senha do usuário administrativo."
    if erros:
        return None, erros
    return CredenciaisOperador(usuario, Segredo(token), Segredo(senha)), {}


@ConfiguracoesBp.get("/api/configuracoes/sistema/provisionamento")
@login_required
@exigir_permissao(PermissaoLuftBase.SISTEMAS_CRIAR)
def api_sistema_destino_provisionamento():  # type: ignore[no-untyped-def]
    """Mostra no modal onde o provisionamento sera feito (sem nenhum segredo)."""

    return jsonify({"status": "success", **destino_do_estado(obter_luftbase()).como_dict()})


@ConfiguracoesBp.post("/api/configuracoes/sistema/criar")
@AdminBp.post("/api/sistema/criar")
@login_required
@exigir_permissao(PermissaoLuftBase.SISTEMAS_CRIAR)
def api_sistema_criar():  # type: ignore[no-untyped-def]
    """Cadastra aplicação no catálogo corporativo com auto-incremento e permissão base."""

    validar_csrf_requisicao()

    if not eh_sistema_master():
        return (
            jsonify(
                {
                    "status": "error",
                    "message": (
                        "Criação de novos sistemas no catálogo corporativo "
                        "é restrita ao sistema master."
                    ),
                }
            ),
            403,
        )

    dados = request.get_json(silent=True)
    if not isinstance(dados, dict):
        return _resposta_erro_cadastro(
            "Requisição inválida: o corpo precisa ser um JSON com os dados do sistema.", None, 400
        )

    valores, erros = validar_payload_novo_sistema(dados)
    credenciais: CredenciaisOperador | None = None
    if dados.get("ProvisionarInfraestrutura"):
        credenciais, erros_credenciais = _ler_credenciais_operador(dados)
        erros.update(erros_credenciais)
        if not valores.get("schema_aplicacao") and "SchemaAplicacao" not in erros:
            erros["SchemaAplicacao"] = (
                "Informe o schema: ele é obrigatório para provisionar o banco e o Vault."
            )
    if erros:
        quantidade = len(erros)
        return _resposta_erro_cadastro(
            f"Corrija {quantidade} campo{'s' if quantidade > 1 else ''} destacado"
            f"{'s' if quantidade > 1 else ''} antes de cadastrar.",
            erros,
            400,
        )

    id_sistema = cast("int | None", valores["id_sistema"])
    nome = str(valores["nome_sistema"])
    schema_aplicacao = cast("str | None", valores["schema_aplicacao"])
    chave_base = str(valores["chave_permissao_base"])
    args_sistema = {
        chave: valor
        for chave, valor in valores.items()
        if chave not in ("id_sistema", "chave_permissao_base")
    }
    if id_sistema is not None:
        args_sistema["id_sistema"] = id_sistema

    etapas: list[str] = []
    estado = obter_luftbase()

    provisionador: ProvisionadorSistema | None = None
    alias_conexao = ""
    if credenciais is not None:
        provisionador = ProvisionadorSistema(destino_do_estado(estado), credenciais)
        try:
            provisionador.verificar()
            alias_conexao = provisionador.alias_conexao()
        except ErroProvisionamento as falha:
            provisionador.encerrar()
            return _resposta_erro_cadastro(
                f"Nada foi gravado. {falha.mensagem}",
                {falha.campo: falha.mensagem} if falha.campo else None,
                422,
            )

    # O segredo e gravado no Vault por ultimo, ainda dentro da transacao do core; se o core
    # nao confirmar o cadastro, o segredo e removido para nao sobrar credencial orfa.
    segredo_gravado: int | None = None
    cadastro_confirmado = False
    try:
        try:
            with estado.bancos.core.escrita() as sessao:
                # Conflitos verificados antes de qualquer escrita, com o campo responsável.
                conflitos: dict[str, str] = {}
                if id_sistema is not None:
                    sistema_com_id = sessao.get(Sistema, id_sistema)
                    if sistema_com_id is not None:
                        conflitos["IdSistema"] = (
                            f"Já existe um sistema com o ID {id_sistema}. "
                            "Deixe o ID em branco para usar o auto-incremento."
                        )
                if (
                    sessao.execute(
                        select(Sistema.id_sistema).where(
                            func.lower(Sistema.nome_sistema) == nome.lower()
                        )
                    ).first()
                    is not None
                ):
                    conflitos["Nome"] = f"Já existe um sistema cadastrado com o nome '{nome}'."
                if schema_aplicacao:
                    dono_schema = sessao.execute(
                        select(Sistema.nome_sistema).where(
                            Sistema.schema_aplicacao == schema_aplicacao
                        )
                    ).scalar()
                    if dono_schema:
                        conflitos["SchemaAplicacao"] = (
                            f"O schema '{schema_aplicacao}' já pertence ao sistema '{dono_schema}'."
                        )
                if conflitos:
                    raise FalhaCadastroSistema(
                        "Já existe um cadastro conflitante. Ajuste os campos destacados.",
                        conflitos,
                        409,
                    )

                # 1. Sistema
                novo = Sistema(**args_sistema)
                sessao.add(novo)
                sessao.flush()  # Garante geração automática do id_sistema pelo banco
                id_gerado = novo.id_sistema
                etapas.append(f"Sistema '{nome}' criado em core.tb_sistema (ID {id_gerado}).")

                # 2. Schema dedicado (opcional). Qualquer falha cancela o cadastro inteiro.
                plano: PlanoSistema | None = None
                senha_role: Segredo | None = None
                if provisionador is not None:
                    if provisionador.segredo_existe(id_gerado):
                        raise FalhaCadastroSistema(
                            "Nada foi gravado. Já existe um segredo no Vault "
                            f"para o ID {id_gerado}.",
                            {
                                "IdSistema": (
                                    f"O Vault já tem 'sistemas/{id_gerado}'. Use outro ID ou "
                                    "remova o segredo antigo com o CLI."
                                )
                            },
                            409,
                        )
                    try:
                        plano = derivar_plano(
                            id_gerado,
                            nome,
                            str(schema_aplicacao),
                            provisionador.ambiente,
                        )
                        senha_role, schema_criado = provisionador.provisionar_banco(plano)
                    except ErroProvisionamento as falha:
                        raise FalhaCadastroSistema(
                            f"Nada foi gravado. {falha.mensagem}",
                            {falha.campo: falha.mensagem} if falha.campo else None,
                        ) from falha
                    except Exception as erro_admin:
                        logger.warning("Falha ao provisionar banco do sistema %s", nome)
                        mensagem_admin = (
                            "Falha ao criar schema/role com o usuário administrativo: "
                            f"{str(getattr(erro_admin, 'orig', erro_admin)).splitlines()[0][:200]}"
                        )
                        raise FalhaCadastroSistema(
                            f"Nada foi gravado no core. {mensagem_admin}",
                            {"UsuarioBanco": mensagem_admin},
                        ) from erro_admin
                    etapas.append(
                        f"Schema '{plano.esquema}' "
                        f"{'criado' if schema_criado else 'reaproveitado'}; role '{plano.role}' "
                        "com senha nova e privilégios no core."
                    )
                elif schema_aplicacao:
                    from luftbase.cli.bootstrap import provisionar_schema_sistema

                    usuario_banco, banco = sessao.execute(
                        select(func.current_user(), func.current_database())
                    ).one()
                    try:
                        # Savepoint: a falha do DDL não pode deixar a transação abortada.
                        with sessao.begin_nested():
                            criado = provisionar_schema_sistema(
                                sessao.connection(),
                                id_sistema=id_gerado,
                                schema_aplicacao=str(schema_aplicacao),
                            )
                    except Exception as erro_schema:
                        sqlstate = getattr(getattr(erro_schema, "orig", None), "sqlstate", None)
                        logger.warning(
                            "Falha ao provisionar schema %s: %s", schema_aplicacao, erro_schema
                        )
                        if sqlstate == _SQLSTATE_SEM_PRIVILEGIO:
                            mensagem_schema = (
                                f"O usuário de banco '{usuario_banco}' não tem permissão "
                                "para criar "
                                f"schemas no banco '{banco}'. Peça ao DBA para executar "
                                f"'CREATE SCHEMA {schema_aplicacao};' e tente novamente "
                                "(o schema existente será reaproveitado), ou deixe este campo em "
                                "branco para cadastrar o sistema sem schema próprio."
                            )
                        else:
                            mensagem_schema = (
                                f"Não foi possível provisionar o schema '{schema_aplicacao}': "
                                f"{getattr(erro_schema, 'orig', erro_schema)}"
                            )
                        raise FalhaCadastroSistema(
                            f"Nada foi gravado. {mensagem_schema}",
                            {"SchemaAplicacao": mensagem_schema},
                        ) from erro_schema
                    etapas.append(
                        f"Schema '{schema_aplicacao}' criado no banco."
                        if criado
                        else f"Schema '{schema_aplicacao}' já existia e foi vinculado ao sistema."
                    )

                # 3. Módulo raiz do sistema
                modulo_padrao = Modulo(
                    id_sistema=id_gerado,
                    codigo_modulo="PLATAFORMA",
                    nome_modulo=f"Plataforma {nome}",
                    descricao_modulo=(
                        f"Módulo estrutural e de controle de acesso do sistema {nome}."
                    ),
                    ativo=True,
                    ordem_exibicao=0,
                    icone="ph-bold ph-shield-check",
                )
                sessao.add(modulo_padrao)
                sessao.flush()
                etapas.append("Módulo 'PLATAFORMA' criado em core.tb_modulo.")

                # 4. Permissão base de acesso, criada já associada ao novo sistema
                permissao_base = Permissao(
                    id_sistema=id_gerado,
                    id_modulo=modulo_padrao.id_modulo,
                    chave_permissao=chave_base,
                    recurso="SISTEMA",
                    acao="ACESSAR",
                    descricao_permissao=f"Permissão base de acesso ao sistema {nome}.",
                    ativo=True,
                    sensivel=False,
                    eh_acesso_sistema=True,
                    ordem_exibicao=0,
                )
                sessao.add(permissao_base)
                sessao.flush()
                etapas.append(
                    f"Permissão base '{chave_base}' criada em core.tb_permissao "
                    f"e associada ao sistema {id_gerado}."
                )

                # 5. Conceder permissão ao grupo do criador (se for admin) ou grupo 6 (TI)
                usuario_atual = usuario_autenticado_atual()
                grupo_alvo_id = (
                    usuario_atual.id_grupo if usuario_atual and usuario_atual.id_grupo else 6
                )
                if grupo_alvo_id:
                    id_usuario_atual = usuario_atual.id_usuario if usuario_atual else None
                    sessao.add(
                        PermissaoGrupo(
                            id_permissao=permissao_base.id_permissao,
                            codigo_usuariogrupo=grupo_alvo_id,
                            conceder=True,
                            codigo_usuario_alteracao=id_usuario_atual,
                        )
                    )
                    sessao.flush()
                    etapas.append(f"Acesso concedido ao grupo {grupo_alvo_id}.")

                # 6. Segredo do sistema no Vault (CAS 0), por ultimo
                if provisionador is not None and plano is not None and senha_role is not None:
                    try:
                        caminho = provisionador.gravar_segredo(plano, alias_conexao, senha_role)
                    except Exception as erro_vault:
                        mensagem_vault = (
                            "O Vault recusou a gravação do segredo do sistema "
                            f"({type(erro_vault).__name__}). Confira se o token tem escrita "
                            "em bancos/postgresql/sistemas."
                        )
                        raise FalhaCadastroSistema(
                            f"Nada foi gravado no core. {mensagem_vault}",
                            {"TokenOperadorVault": mensagem_vault},
                            502,
                        ) from erro_vault
                    segredo_gravado = id_gerado
                    etapas.append(
                        f"Segredo '{caminho}' gravado no Vault "
                        f"(identificador '{plano.identificador}')."
                    )
        except FalhaCadastroSistema as falha:
            return _resposta_erro_cadastro(falha.mensagem, falha.erros, falha.status)
        except IntegrityError as erro_integridade:
            logger.warning("Conflito ao cadastrar sistema %s: %s", nome, erro_integridade)
            return _resposta_erro_cadastro(
                "Nada foi gravado. O banco recusou o cadastro por conflito de dados "
                f"({getattr(erro_integridade, 'orig', erro_integridade)}).",
                None,
                409,
            )
        except SQLAlchemyError as erro_banco:
            logger.exception("Falha de banco ao cadastrar sistema %s", nome)
            return _resposta_erro_cadastro(
                "Nada foi gravado. Falha no banco de dados ao cadastrar o sistema "
                f"({type(getattr(erro_banco, 'orig', erro_banco)).__name__}). "
                "Detalhes registrados no log do servidor.",
                None,
                500,
            )
        cadastro_confirmado = True
    finally:
        if provisionador is not None:
            if segredo_gravado is not None and not cadastro_confirmado:
                try:
                    provisionador.remover_segredo(segredo_gravado)
                    logger.warning(
                        "Segredo do sistema %s removido: o core nao confirmou o cadastro.",
                        segredo_gravado,
                    )
                except Exception:
                    logger.exception(
                        "Segredo do sistema %s ficou no Vault sem cadastro no core; remova com "
                        "'luftbase vault postgresql remover-sistemas'.",
                        segredo_gravado,
                    )
            provisionador.encerrar()

    # Invalidação de caches fora da transação de escrita do core
    from luftbase.web.manutencao import invalidar_cache_manutencao

    estado.autorizacao.invalidar_cache()
    invalidar_cache_manutencao(id_gerado)
    estado.auditoria.registrar_alteracao(
        recurso="SISTEMA",
        id_recurso=id_gerado,
        acao="CRIAR_SISTEMA",
        descricao=f"Sistema '{nome}' (ID {id_gerado}) cadastrado com sucesso com permissão base '{chave_base}'.",
        dados_anteriores=None,
        dados_novos=args_sistema,
    )

    return jsonify(
        {
            "status": "success",
            "message": (
                f"Sistema '{nome}' (ID {id_gerado}) cadastrado com sucesso "
                f"com permissão base '{chave_base}'."
            ),
            "id_sistema": id_gerado,
            "chave_permissao_base": chave_base,
            "etapas": etapas,
        }
    )


@ConfiguracoesBp.get("/api/configuracoes/ambiente/variaveis")
@login_required
@exigir_permissao(PermissaoLuftBase.VARIAVEIS_VISUALIZAR)
def api_ambiente_variaveis():  # type: ignore[no-untyped-def]
    """Informa que o recurso de ambiente está em homologação."""

    return (
        jsonify(
            {
                "status": "error",
                "message": (
                    "Recurso de gestão de ambiente em fase de homologação "
                    "e indisponível no momento."
                ),
            }
        ),
        501,
    )


@ConfiguracoesBp.post("/api/configuracoes/ambiente/variaveis/salvar")
@login_required
@exigir_permissao(PermissaoLuftBase.VARIAVEIS_EDITAR)
def api_ambiente_variaveis_salvar():  # type: ignore[no-untyped-def]
    """Informa que a alteração de variáveis está em homologação."""

    validar_csrf_requisicao()
    return (
        jsonify(
            {
                "status": "error",
                "message": (
                    "Recurso de gestão de variáveis em fase de homologação "
                    "e indisponível no momento."
                ),
            }
        ),
        501,
    )


def _sistemas_com_servico() -> list[Sistema]:
    """Sistemas ativos cujo servico a tela pode ver: o Hub ve todos; um satelite, so o proprio."""

    estado = obter_luftbase()
    with estado.bancos.core.leitura() as sessao:
        consulta = select(Sistema).where(Sistema.ativo.is_(True)).order_by(Sistema.id_sistema.asc())
        sistemas = list(sessao.execute(consulta).scalars().all())
        sessao.expunge_all()
    if eh_sistema_master():
        return sistemas
    atual = sistema_aplicacao_atual()
    return [s for s in sistemas if s.id_sistema == atual]


def _servico_do_sistema(sistema: Sistema) -> dict[str, object]:
    """Descreve o servico de uma aplicacao, descoberto pelo nome do sistema (sem .env)."""

    nome = nome_do_servico(sistema.nome_sistema, plataforma_do_host())
    # O Hub e a propria aplicacao em execucao so se monitoram: parar a si mesma derrubaria a tela.
    protegido = sistema.id_sistema == 0 or sistema.id_sistema == sistema_aplicacao_atual()
    return {
        "idServico": str(sistema.id_sistema),
        "nomeExibicao": sistema.nome_sistema,
        "nomeServico": nome,
        "descricao": sistema.descricao_sistema or "",
        "protegido": protegido,
        "status": "VERIFICANDO",
    }


def _servicos_operacao() -> list[dict[str, object]]:
    try:
        return [_servico_do_sistema(s) for s in _sistemas_com_servico()]
    except SQLAlchemyError:
        logger.exception("Falha ao listar os servicos das aplicacoes")
        return []


@ConfiguracoesBp.get("/api/configuracoes/ambiente/servicos")
@login_required
@exigir_permissao(PermissaoLuftBase.SERVICOS_VISUALIZAR)
def api_ambiente_servicos():  # type: ignore[no-untyped-def]
    """Status atual do servico de cada aplicacao visivel para este sistema."""

    plataforma = plataforma_do_host()
    itens = []
    for servico in _servicos_operacao():
        nome = cast("str | None", servico["nomeServico"])
        status = (
            consultar_status(nome, plataforma).value if nome else StatusServico.INDISPONIVEL.value
        )
        itens.append({**servico, "status": status})
    return jsonify({"status": "success", "data": {"servicos": itens}})


@ConfiguracoesBp.post("/api/configuracoes/ambiente/servicos/acao")
@login_required
@exigir_permissao(PermissaoLuftBase.SERVICOS_EXECUTAR)
def api_ambiente_servicos_acao():  # type: ignore[no-untyped-def]
    """Inicia, para ou reinicia o servico de uma aplicacao cadastrada (exceto o Hub e o proprio)."""

    validar_csrf_requisicao()
    dados = request.get_json(silent=True) or {}
    acao = str(dados.get("acao", "")).strip().lower()
    id_servico = str(dados.get("idServico", "")).strip()
    if acao not in ACOES:
        return jsonify({"status": "error", "message": "Ação inválida."}), 400

    # So atua sobre servicos de sistemas cadastrados e visiveis: nada de nomes livres.
    servico = next((s for s in _servicos_operacao() if s["idServico"] == id_servico), None)
    if servico is None or not servico["nomeServico"]:
        return jsonify({"status": "error", "message": "Serviço não encontrado."}), 404
    if servico["protegido"]:
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Serviço protegido: este permite somente monitoramento.",
                }
            ),
            403,
        )

    nome = cast("str", servico["nomeServico"])
    estado = obter_luftbase()
    try:
        executar_acao(nome, acao, plataforma_do_host())
    except ErroServicoHost as erro:
        estado.auditoria.registrar_alteracao(
            recurso="SERVICO",
            id_recurso=int(id_servico),
            acao=f"FALHA_{acao.upper()}_SERVICO",
            descricao=f"Falha ao {acao} o serviço {nome}: {erro}",
            dados_anteriores=None,
            dados_novos={"servico": nome, "acao": acao},
        )
        return jsonify({"status": "error", "message": str(erro)}), 502
    estado.auditoria.registrar_alteracao(
        recurso="SERVICO",
        id_recurso=int(id_servico),
        acao=f"{acao.upper()}_SERVICO",
        descricao=f"Serviço {nome}: ação '{acao}' executada.",
        dados_anteriores=None,
        dados_novos={"servico": nome, "acao": acao},
    )
    return jsonify({"status": "success", "message": f"Serviço {nome}: {acao} concluído."})


from luftbase.web import integracoes as _integracoes  # noqa: E402,F401,I001


__all__ = ["AdminBp", "ConfiguracoesBp", "visualizar_painel"]
