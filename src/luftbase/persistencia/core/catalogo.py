"""Sincronizacao aditiva do catalogo sistemico entregue pelo LuftBase."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Connection, select, update
from sqlalchemy.dialects.postgresql import insert

from luftbase.autorizacao.catalogo import (
    MODULOS_PADRAO,
    PERMISSOES_PADRAO,
    PermissaoLuftBase,
)
from luftbase.persistencia.core.seguranca import (
    Modulo,
    Permissao,
    PermissaoGrupo,
    Sistema,
)


@dataclass(frozen=True, slots=True)
class ResultadoSincronizacaoCatalogo:
    """Resumo sem dados sensiveis da sincronizacao executada."""

    modulos: int
    permissoes: int
    grupo_administrador: int | None


def sincronizar_catalogo_workspace(
    conexao: Connection,
    *,
    grupo_administrador: int | None = None,
) -> ResultadoSincronizacaoCatalogo:
    """Insere ou atualiza metadados canonicos sem remover registros desconhecidos."""

    comando_sistema = insert(Sistema).values(
        id_sistema=0,
        nome_sistema="Luft-Workspace",
        descricao_sistema="Hub central da plataforma web Luft.",
        categoria="HUB",
        schema_aplicacao="workspace",
        ativo=True,
        em_manutencao=False,
        ordem_exibicao=0,
        icone="ph-bold ph-squares-four",
        link="/",
    )
    conexao.execute(
        comando_sistema.on_conflict_do_update(
            index_elements=[Sistema.id_sistema],
            set_={
                "nome_sistema": comando_sistema.excluded.nome_sistema,
                "descricao_sistema": comando_sistema.excluded.descricao_sistema,
                "categoria": comando_sistema.excluded.categoria,
                "schema_aplicacao": comando_sistema.excluded.schema_aplicacao,
                "icone": comando_sistema.excluded.icone,
                "link": comando_sistema.excluded.link,
            },
        )
    )

    ids_modulos: dict[str, int] = {}
    for modulo in MODULOS_PADRAO:
        comando_modulo = insert(Modulo).values(
            id_sistema=0,
            codigo_modulo=modulo.codigo,
            nome_modulo=modulo.nome,
            descricao_modulo=modulo.descricao,
            icone=modulo.icone,
            ordem_exibicao=modulo.ordem,
            ativo=True,
        )
        conexao.execute(
            comando_modulo.on_conflict_do_update(
                constraint="uq_core_modulo_codigo_sistema",
                set_={
                    "nome_modulo": comando_modulo.excluded.nome_modulo,
                    "descricao_modulo": comando_modulo.excluded.descricao_modulo,
                    "icone": comando_modulo.excluded.icone,
                    "ordem_exibicao": comando_modulo.excluded.ordem_exibicao,
                },
            )
        )
        id_modulo = conexao.scalar(
            select(Modulo.id_modulo).where(
                Modulo.id_sistema == 0,
                Modulo.codigo_modulo == modulo.codigo,
            )
        )
        if id_modulo is None:
            raise RuntimeError(f"Modulo {modulo.codigo} nao foi sincronizado.")
        ids_modulos[modulo.codigo] = id_modulo

    chave_acesso = PermissaoLuftBase.SISTEMA_ACESSAR.value
    conexao.execute(
        update(Permissao)
        .where(
            Permissao.id_sistema == 0,
            Permissao.eh_acesso_sistema.is_(True),
            Permissao.chave_permissao != chave_acesso,
        )
        .values(eh_acesso_sistema=False)
    )

    ids_permissoes: dict[str, int] = {}
    for definicao in PERMISSOES_PADRAO:
        id_pai = ids_permissoes.get(definicao.pai.value) if definicao.pai else None
        comando_permissao = insert(Permissao).values(
            id_sistema=0,
            id_modulo=ids_modulos[definicao.modulo],
            id_permissao_pai=id_pai,
            chave_permissao=definicao.chave.value,
            recurso=definicao.recurso,
            acao=definicao.acao.value,
            descricao_permissao=definicao.descricao,
            ativo=True,
            sensivel=definicao.sensivel,
            eh_acesso_sistema=definicao.acesso_sistema,
            ordem_exibicao=definicao.ordem,
        )
        conexao.execute(
            comando_permissao.on_conflict_do_update(
                constraint="uq_core_permissao_chave_sistema",
                set_={
                    "id_modulo": comando_permissao.excluded.id_modulo,
                    "id_permissao_pai": comando_permissao.excluded.id_permissao_pai,
                    "recurso": comando_permissao.excluded.recurso,
                    "acao": comando_permissao.excluded.acao,
                    "descricao_permissao": comando_permissao.excluded.descricao_permissao,
                    "sensivel": comando_permissao.excluded.sensivel,
                    "eh_acesso_sistema": comando_permissao.excluded.eh_acesso_sistema,
                    "ordem_exibicao": comando_permissao.excluded.ordem_exibicao,
                },
            )
        )
        id_permissao = conexao.scalar(
            select(Permissao.id_permissao).where(
                Permissao.id_sistema == 0,
                Permissao.chave_permissao == definicao.chave.value,
            )
        )
        if id_permissao is None:
            raise RuntimeError(f"Permissao {definicao.chave.value} nao foi sincronizada.")
        ids_permissoes[definicao.chave.value] = id_permissao

    if grupo_administrador is not None:
        if grupo_administrador <= 0:
            raise ValueError("O codigo do grupo administrador deve ser positivo.")
        for chave_admin in (
            PermissaoLuftBase.SISTEMA_ADMINISTRAR.value,
            PermissaoLuftBase.SISTEMA_ACESSAR.value,
        ):
            comando_grupo = insert(PermissaoGrupo).values(
                codigo_usuariogrupo=grupo_administrador,
                id_permissao=ids_permissoes[chave_admin],
                conceder=True,
            )
            conexao.execute(
                comando_grupo.on_conflict_do_nothing(constraint="uq_core_permissaogrupo")
            )

    return ResultadoSincronizacaoCatalogo(
        modulos=len(MODULOS_PADRAO),
        permissoes=len(PERMISSOES_PADRAO),
        grupo_administrador=grupo_administrador,
    )


__all__ = ["ResultadoSincronizacaoCatalogo", "sincronizar_catalogo_workspace"]
