"""Contexto de template que toda aplicacao Luft precisa para exibir o Painel de Controle."""

from __future__ import annotations

from luftbase.autorizacao import PermissaoLuftBase, consultar_permissoes

_CHAVES_PAINEL = (
    PermissaoLuftBase.CONFIGURACOES_VISUALIZAR,
    PermissaoLuftBase.PERMISSOES_VISUALIZAR,
    PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
    PermissaoLuftBase.VARIAVEIS_EDITAR,
    PermissaoLuftBase.SISTEMAS_VISUALIZAR,
    PermissaoLuftBase.SERVICOS_VISUALIZAR,
    PermissaoLuftBase.COMUNICADOS_VISUALIZAR,
    PermissaoLuftBase.COMUNICADOS_CRIAR,
    PermissaoLuftBase.ATUALIZACOES_VISUALIZAR,
    PermissaoLuftBase.ATUALIZACOES_CRIAR,
    PermissaoLuftBase.AUDITORIA_VISUALIZAR,
)

SINALIZADORES_PAINEL = (
    "pode_ver_painel",
    "pode_ver_configuracoes",
    "pode_ver_seguranca",
    "pode_ver_ambiente",
    "pode_editar_ambiente",
    "pode_ver_comunicados",
    "pode_ver_atualizacoes",
    "pode_ver_auditoria",
)


def contexto_painel(decisoes: dict[str, bool] | None = None) -> dict[str, object]:
    """Sinalizadores `pode_ver_*` do Painel de Controle para o usuario autenticado.

    Uma unica consulta em lote (cache por requisicao do LuftBase). Sem usuario autenticado todos
    saem falsos. Use dentro de um ``context_processor``::

        return {"layout_base": "Layout/BaseLayout.html", **contexto_painel()}

    ``decisoes`` permite reaproveitar uma consulta em lote ja feita (deve conter as chaves do
    painel); por padrao a funcao consulta sozinha.
    """

    if decisoes is None:
        decisoes = consultar_permissoes(_CHAVES_PAINEL)

    def pode(*chaves: str) -> bool:
        return any(bool(decisoes.get(chave, False)) for chave in chaves)

    configuracoes = pode(PermissaoLuftBase.CONFIGURACOES_VISUALIZAR)
    seguranca = pode(PermissaoLuftBase.PERMISSOES_VISUALIZAR)
    ambiente = pode(
        PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
        PermissaoLuftBase.SISTEMAS_VISUALIZAR,
        PermissaoLuftBase.SERVICOS_VISUALIZAR,
    )
    editar_ambiente = pode(PermissaoLuftBase.VARIAVEIS_EDITAR)
    comunicados = pode(
        PermissaoLuftBase.COMUNICADOS_VISUALIZAR, PermissaoLuftBase.COMUNICADOS_CRIAR
    )
    atualizacoes = pode(
        PermissaoLuftBase.ATUALIZACOES_VISUALIZAR, PermissaoLuftBase.ATUALIZACOES_CRIAR
    )
    auditoria = pode(PermissaoLuftBase.AUDITORIA_VISUALIZAR)
    return {
        "pode_ver_painel": any(
            (
                configuracoes,
                seguranca,
                ambiente,
                editar_ambiente,
                comunicados,
                atualizacoes,
                auditoria,
            )
        ),
        "pode_ver_configuracoes": configuracoes,
        "pode_ver_seguranca": seguranca,
        "pode_ver_ambiente": ambiente,
        "pode_editar_ambiente": editar_ambiente,
        "pode_ver_comunicados": comunicados,
        "pode_ver_atualizacoes": atualizacoes,
        "pode_ver_auditoria": auditoria,
    }
