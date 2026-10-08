"""Resolucao do estado efetivo das permissoes (usuario > grupo, com heranca pela arvore)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from luftbase.persistencia.core.seguranca import Permissao


def resolver_estados(
    permissoes: list[Permissao],
    regras_usuario: dict[int, bool],
    regras_grupo: dict[int, bool],
    *,
    somente: set[int] | None = None,
) -> dict[str, dict[str, object]]:
    """Resolve estados efetivos e explica a origem usada pela interface."""

    mapa = {item.id_permissao: item for item in permissoes}
    estados: dict[str, dict[str, object]] = {}
    for permissao in permissoes:
        if somente is not None and permissao.id_permissao not in somente:
            continue
        caminho: list[Permissao] = []
        atual: Permissao | None = permissao
        visitados: set[int] = set()
        while atual is not None and atual.id_permissao not in visitados and len(caminho) <= 32:
            caminho.append(atual)
            visitados.add(atual.id_permissao)
            atual = mapa.get(atual.id_permissao_pai) if atual.id_permissao_pai else None

        origem = "PADRAO"
        regra_id: int | None = None
        permitido = False
        if len(caminho) <= 32 and all(item.ativo for item in caminho):
            regra_usuario = next(
                (item for item in caminho if item.id_permissao in regras_usuario), None
            )
            regra_grupo = next(
                (item for item in caminho if item.id_permissao in regras_grupo), None
            )
            if regra_usuario is not None:
                origem = "USUARIO"
                regra_id = regra_usuario.id_permissao
                permitido = regras_usuario[regra_id]
            elif regra_grupo is not None:
                origem = "GRUPO"
                regra_id = regra_grupo.id_permissao
                permitido = regras_grupo[regra_id]

        regra_item = mapa.get(regra_id) if regra_id else None
        estados[str(permissao.id_permissao)] = {
            "permitido": permitido,
            "origem": origem,
            "herdada": regra_id is not None and regra_id != permissao.id_permissao,
            "regra_id": regra_id,
            "regra_chave": regra_item.chave_permissao if regra_item else None,
            "regra_descricao": regra_item.descricao_permissao if regra_item else None,
            "ativo": permissao.ativo,
        }
    return estados


__all__ = ["resolver_estados"]
