"""Catalogo declarativo de modulos e permissoes de uma aplicacao satelite.

Cada aplicacao descreve em Python seus modulos e a arvore de permissoes. O cadastro do
sistema em `core.tb_sistema` pertence ao Workspace; na inicializacao o LuftBase compara o
catalogo com o core e grava somente o que falta ou divergiu. A sincronizacao e aditiva e
idempotente: nunca remove registros desconhecidos nem vinculos de grupos e usuarios.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import Connection, select, update
from sqlalchemy.dialects.postgresql import insert

from luftbase.autorizacao.catalogo import AcaoPermissao, DefinicaoModulo
from luftbase.persistencia.core.catalogo import ResultadoSincronizacaoCatalogo
from luftbase.persistencia.core.seguranca import Modulo, Permissao, Sistema

_PADRAO_CHAVE = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$")
_CATEGORIAS = frozenset({"APLICACAO", "SERVICO"})


class ErroCatalogo(ValueError):
    """Indica um catalogo declarado de forma inconsistente."""


@dataclass(frozen=True, slots=True)
class SistemaAplicacao:
    """Dados de exibicao em `core.tb_sistema`, usados apenas pela CLI de sincronizacao."""

    nome: str
    descricao: str
    icone: str = "ph-bold ph-app-window"
    link: str | None = None
    categoria: str = "APLICACAO"
    ordem: int = 0


@dataclass(frozen=True, slots=True)
class PermissaoAplicacao:
    """No da arvore `MODULO.RECURSO.ACAO`.

    O modulo e o primeiro segmento da chave, salvo quando `modulo` e informado; isso permite
    manter as chaves de acesso no modulo `PLATAFORMA` criado pelo Workspace.
    """

    chave: str
    descricao: str
    pai: str | None = None
    sensivel: bool = False
    acesso_sistema: bool = False
    ordem: int = 0
    modulo_codigo: str | None = None

    @property
    def modulo(self) -> str:
        return self.modulo_codigo or self.chave.split(".")[0]

    @property
    def recurso(self) -> str:
        return self.chave.split(".")[1]

    @property
    def acao(self) -> str:
        return self.chave.split(".")[2]


@dataclass(frozen=True, slots=True)
class CatalogoAplicacao:
    """Declaracao completa, validada antes de qualquer escrita."""

    modulos: tuple[DefinicaoModulo, ...]
    permissoes: tuple[PermissaoAplicacao, ...] = field(default_factory=tuple)
    sistema: SistemaAplicacao | None = None

    def validar(self) -> None:
        """Rejeita chaves fora do padrao, acoes desconhecidas e arvores quebradas."""

        if self.sistema is not None and self.sistema.categoria not in _CATEGORIAS:
            raise ErroCatalogo("A categoria do sistema deve ser APLICACAO ou SERVICO.")
        codigos = [modulo.codigo for modulo in self.modulos]
        if len(set(codigos)) != len(codigos):
            raise ErroCatalogo("Ha codigos de modulo repetidos no catalogo.")

        acoes = {acao.value for acao in AcaoPermissao}
        declaradas: set[str] = set()
        acessos = 0
        for permissao in self.permissoes:
            if not _PADRAO_CHAVE.fullmatch(permissao.chave):
                raise ErroCatalogo(
                    f"A chave {permissao.chave!r} deve seguir MODULO.RECURSO.ACAO em maiusculas."
                )
            if permissao.chave in declaradas:
                raise ErroCatalogo(f"A chave {permissao.chave!r} foi declarada duas vezes.")
            if permissao.acao not in acoes:
                raise ErroCatalogo(
                    f"A acao {permissao.acao!r} de {permissao.chave!r} nao e aceita pelo core."
                )
            if permissao.modulo not in codigos:
                raise ErroCatalogo(
                    f"O modulo {permissao.modulo!r} de {permissao.chave!r} nao foi declarado."
                )
            # Exigir o pai antes do filho permite gravar a arvore numa unica passada.
            if permissao.pai is not None and permissao.pai not in declaradas:
                raise ErroCatalogo(
                    f"O pai {permissao.pai!r} de {permissao.chave!r} deve ser declarado antes."
                )
            acessos += permissao.acesso_sistema
            declaradas.add(permissao.chave)
        if acessos != 1:
            raise ErroCatalogo("O catalogo precisa de exatamente uma permissao de acesso.")


def _validar_id(id_sistema: int) -> None:
    if isinstance(id_sistema, bool) or id_sistema <= 0:
        raise ErroCatalogo("O sistema 0 e sincronizado pelo proprio LuftBase (bootstrap).")


def pendencias_catalogo(
    conexao: Connection,
    id_sistema: int,
    catalogo: CatalogoAplicacao,
) -> list[str]:
    """Lista o que falta ou diverge no core; lista vazia significa catalogo em dia."""

    _validar_id(id_sistema)
    catalogo.validar()

    modulos = {
        linha.codigo_modulo: linha
        for linha in conexao.execute(select(Modulo).where(Modulo.id_sistema == id_sistema))
    }
    codigo_por_id = {linha.id_modulo: codigo for codigo, linha in modulos.items()}
    permissoes = {
        linha.chave_permissao: linha
        for linha in conexao.execute(select(Permissao).where(Permissao.id_sistema == id_sistema))
    }
    chave_por_id = {linha.id_permissao: chave for chave, linha in permissoes.items()}

    pendencias: list[str] = []
    for modulo in catalogo.modulos:
        atual = modulos.get(modulo.codigo)
        if atual is None:
            pendencias.append(f"modulo {modulo.codigo} ausente")
        elif (atual.nome_modulo, atual.descricao_modulo, atual.icone, atual.ordem_exibicao) != (
            modulo.nome,
            modulo.descricao,
            modulo.icone,
            modulo.ordem,
        ):
            pendencias.append(f"modulo {modulo.codigo} divergente")

    chave_acesso = next(p.chave for p in catalogo.permissoes if p.acesso_sistema)
    for permissao in catalogo.permissoes:
        gravada = permissoes.get(permissao.chave)
        if gravada is None:
            pendencias.append(f"permissao {permissao.chave} ausente")
            continue
        declarado = (
            permissao.modulo,
            permissao.pai,
            permissao.recurso,
            permissao.acao,
            permissao.descricao,
            permissao.sensivel,
            permissao.acesso_sistema,
            permissao.ordem,
        )
        gravado = (
            codigo_por_id.get(gravada.id_modulo),
            chave_por_id.get(gravada.id_permissao_pai) if gravada.id_permissao_pai else None,
            gravada.recurso,
            gravada.acao,
            gravada.descricao_permissao,
            gravada.sensivel,
            gravada.eh_acesso_sistema,
            gravada.ordem_exibicao,
        )
        if declarado != gravado:
            pendencias.append(f"permissao {permissao.chave} divergente")

    for chave, linha in permissoes.items():
        if linha.eh_acesso_sistema and chave != chave_acesso:
            pendencias.append(f"permissao {chave} marcada como acesso")
    return pendencias


def sincronizar_catalogo_aplicacao(
    conexao: Connection,
    id_sistema: int,
    catalogo: CatalogoAplicacao,
) -> ResultadoSincronizacaoCatalogo:
    """Grava modulos e permissoes declarados (e o sistema, se declarado), sem remover nada."""

    _validar_id(id_sistema)
    catalogo.validar()

    sistema = catalogo.sistema
    if sistema is None:
        if (
            conexao.scalar(select(Sistema.id_sistema).where(Sistema.id_sistema == id_sistema))
            is None
        ):
            raise ErroCatalogo(
                f"O sistema {id_sistema} nao existe em core.tb_sistema. "
                "Cadastre-o pelo Luft-Workspace e use o ID gerado em LUFT_SISTEMA_ID."
            )
    else:
        comando_sistema = insert(Sistema).values(
            id_sistema=id_sistema,
            nome_sistema=sistema.nome,
            descricao_sistema=sistema.descricao,
            categoria=sistema.categoria,
            ativo=True,
            em_manutencao=False,
            ordem_exibicao=sistema.ordem,
            icone=sistema.icone,
            link=sistema.link,
        )
        # `ativo` e `em_manutencao` sao operacionais: uma sincronizacao nao os reverte.
        conexao.execute(
            comando_sistema.on_conflict_do_update(
                index_elements=[Sistema.id_sistema],
                set_={
                    "nome_sistema": comando_sistema.excluded.nome_sistema,
                    "descricao_sistema": comando_sistema.excluded.descricao_sistema,
                    "categoria": comando_sistema.excluded.categoria,
                    "icone": comando_sistema.excluded.icone,
                    "link": comando_sistema.excluded.link,
                    "ordem_exibicao": comando_sistema.excluded.ordem_exibicao,
                },
            )
        )

    ids_modulos: dict[str, int] = {}
    for modulo in catalogo.modulos:
        comando_modulo = insert(Modulo).values(
            id_sistema=id_sistema,
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
                Modulo.id_sistema == id_sistema,
                Modulo.codigo_modulo == modulo.codigo,
            )
        )
        if id_modulo is None:
            raise RuntimeError(f"Modulo {modulo.codigo} nao foi sincronizado.")
        ids_modulos[modulo.codigo] = id_modulo

    chave_acesso = next(p.chave for p in catalogo.permissoes if p.acesso_sistema)
    conexao.execute(
        update(Permissao)
        .where(
            Permissao.id_sistema == id_sistema,
            Permissao.eh_acesso_sistema.is_(True),
            Permissao.chave_permissao != chave_acesso,
        )
        .values(eh_acesso_sistema=False)
    )

    ids_permissoes: dict[str, int] = {}
    for permissao in catalogo.permissoes:
        comando_permissao = insert(Permissao).values(
            id_sistema=id_sistema,
            id_modulo=ids_modulos[permissao.modulo],
            id_permissao_pai=ids_permissoes.get(permissao.pai) if permissao.pai else None,
            chave_permissao=permissao.chave,
            recurso=permissao.recurso,
            acao=permissao.acao,
            descricao_permissao=permissao.descricao,
            ativo=True,
            sensivel=permissao.sensivel,
            eh_acesso_sistema=permissao.acesso_sistema,
            ordem_exibicao=permissao.ordem,
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
                Permissao.id_sistema == id_sistema,
                Permissao.chave_permissao == permissao.chave,
            )
        )
        if id_permissao is None:
            raise RuntimeError(f"Permissao {permissao.chave} nao foi sincronizada.")
        ids_permissoes[permissao.chave] = id_permissao

    return ResultadoSincronizacaoCatalogo(
        modulos=len(catalogo.modulos),
        permissoes=len(catalogo.permissoes),
        grupo_administrador=None,
    )


__all__ = [
    "CatalogoAplicacao",
    "ErroCatalogo",
    "PermissaoAplicacao",
    "SistemaAplicacao",
    "pendencias_catalogo",
    "sincronizar_catalogo_aplicacao",
]
