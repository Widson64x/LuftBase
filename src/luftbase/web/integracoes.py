"""Rotas da aba Integracoes do Painel de Controle (somente leitura)."""

from __future__ import annotations

import logging
from typing import Any

from flask import jsonify, request
from flask_login import login_required

from luftbase._versao import __version__
from luftbase.autorizacao.catalogo import PermissaoLuftBase
from luftbase.autorizacao.web import exigir_permissao
from luftbase.infraestrutura.cofre.cliente_hvac import ClienteVaultHvac
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.integracoes.diagnostico import montar_painel
from luftbase.integracoes.versoes import VerificadorVersao
from luftbase.plataforma import obter_luftbase
from luftbase.web.configuracoes import ConfiguracoesBp

logger = logging.getLogger(__name__)

_verificador = VerificadorVersao()


def _criar_cliente_vault(estado: Any) -> ClienteVaultHvac:
    """Cliente proprio do painel, com o mesmo token protegido que a aplicacao ja usa."""

    cofre = estado.configuracao.cofre
    token = DesprotetorFernet(cofre.token_acesso).revelar(cofre.token_protegido)
    return ClienteVaultHvac(cofre.endereco, Segredo(token))


@ConfiguracoesBp.get("/api/configuracoes/integracoes")
@login_required
@exigir_permissao(PermissaoLuftBase.SERVICOS_VISUALIZAR)
def api_integracoes():  # type: ignore[no-untyped-def]
    """Cartoes de integracao: caminhos no Vault, saude e versoes (sem nenhum valor secreto)."""

    estado = obter_luftbase()
    try:
        vault = _criar_cliente_vault(estado)
        dados = montar_painel(
            estado,
            vault,
            versao_vault=vault.versao_servidor,
            integracoes_aplicacao=estado.integracoes,
        )
    except Exception:
        logger.exception("Falha ao montar o painel de integracoes")
        return (
            jsonify(
                {
                    "status": "error",
                    "message": "Nao foi possivel montar o painel de integracoes agora.",
                }
            ),
            500,
        )
    return jsonify({"status": "success", "data": dados})


@ConfiguracoesBp.get("/api/configuracoes/integracoes/versao-luftbase")
@login_required
@exigir_permissao(PermissaoLuftBase.SERVICOS_VISUALIZAR)
def api_integracoes_versao_luftbase():  # type: ignore[no-untyped-def]
    """Compara a versao instalada do LuftBase com a ultima tag publicada no GitHub."""

    resultado = _verificador.verificar(__version__, forcar=request.args.get("forcar") == "1")
    return jsonify({"status": "success", "data": resultado.como_dict()})
