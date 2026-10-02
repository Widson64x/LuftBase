"""Consultas seletivas para decisoes de autorizacao hierarquica."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import and_, func, literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ErroAutorizacao
from luftbase.persistencia.core import (
    Modulo,
    Permissao,
    PermissaoGrupo,
    PermissaoUsuario,
    RevisaoCache,
    Sistema,
)

NAMESPACE_REVISAO_AUTORIZACAO = "autorizacao"
PROFUNDIDADE_MAXIMA = 32


@dataclass(frozen=True, slots=True)
class _RegraHierarquia:
    """Linha normalizada da arvore consultada no PostgreSQL."""

    chave: str
    escopo: int
    distancia: int
    ativo: bool
    possui_pai: bool
    vinculo_usuario: int | None
    usuario_concede: bool | None
    vinculo_grupo: int | None
    grupo_concede: bool | None


class RepositorioAutorizacao:
    """Resolve somente as chaves pedidas, seus ancestrais e regras aplicaveis."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def consultar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        chaves: Iterable[str],
    ) -> dict[str, bool]:
        """Aplica escopo, arvore, excecao de usuario e regra de grupo."""

        chaves_consultadas = tuple(dict.fromkeys(chaves))
        if not chaves_consultadas:
            return {}

        escopos = (0,) if id_sistema == 0 else (0, id_sistema)
        arvore = (
            select(
                Permissao.chave_permissao.label("chave"),
                Permissao.id_sistema.label("escopo"),
                Permissao.id_permissao.label("id_no"),
                Permissao.id_permissao_pai.label("id_pai"),
                literal(0).label("distancia"),
                Permissao.ativo.label("ativo"),
            )
            .join(Sistema, Sistema.id_sistema == Permissao.id_sistema)
            .join(Modulo, Modulo.id_modulo == Permissao.id_modulo)
            .where(
                Permissao.id_sistema.in_(escopos),
                Permissao.chave_permissao.in_(chaves_consultadas),
                Sistema.ativo.is_(True),
                Modulo.ativo.is_(True),
            )
            .cte("arvore_permissao", recursive=True)
        )
        pai = aliased(Permissao)
        arvore = arvore.union_all(
            select(
                arvore.c.chave,
                arvore.c.escopo,
                pai.id_permissao,
                pai.id_permissao_pai,
                arvore.c.distancia + 1,
                pai.ativo,
            )
            .join(
                pai,
                and_(
                    pai.id_permissao == arvore.c.id_pai,
                    pai.id_sistema == arvore.c.escopo,
                ),
            )
            .where(arvore.c.distancia < PROFUNDIDADE_MAXIMA)
        )

        declaracao = (
            select(
                arvore.c.chave,
                arvore.c.escopo,
                arvore.c.distancia,
                arvore.c.ativo,
                arvore.c.id_pai.is_not(None).label("possui_pai"),
                PermissaoUsuario.id_vinculo,
                PermissaoUsuario.conceder,
                PermissaoGrupo.id_vinculo,
                PermissaoGrupo.conceder,
            )
            .outerjoin(
                PermissaoUsuario,
                and_(
                    PermissaoUsuario.id_permissao == arvore.c.id_no,
                    PermissaoUsuario.codigo_usuario == id_usuario,
                ),
            )
            .outerjoin(
                PermissaoGrupo,
                and_(
                    PermissaoGrupo.id_permissao == arvore.c.id_no,
                    PermissaoGrupo.codigo_usuariogrupo == id_grupo,
                ),
            )
            .order_by(arvore.c.chave, arvore.c.escopo.desc(), arvore.c.distancia)
        )

        resultado = {chave: False for chave in chaves_consultadas}
        try:
            with self._banco.leitura() as sessao:
                linhas = sessao.execute(declaracao).all()
        except Exception as erro:
            raise ErroAutorizacao("Nao foi possivel comprovar as permissoes solicitadas.") from erro

        regras_por_chave: dict[tuple[str, int], list[_RegraHierarquia]] = defaultdict(list)
        for linha in linhas:
            regra = _RegraHierarquia(
                chave=str(linha[0]),
                escopo=int(linha[1]),
                distancia=int(linha[2]),
                ativo=bool(linha[3]),
                possui_pai=bool(linha[4]),
                vinculo_usuario=linha[5],
                usuario_concede=linha[6],
                vinculo_grupo=linha[7],
                grupo_concede=linha[8],
            )
            regras_por_chave[(regra.chave, regra.escopo)].append(regra)

        for chave in chaves_consultadas:
            escopo_preferido = id_sistema if (chave, id_sistema) in regras_por_chave else 0
            regras = regras_por_chave.get((chave, escopo_preferido), [])
            resultado[chave] = self._decidir(regras)
        return resultado

    @staticmethod
    def _decidir(regras: list[_RegraHierarquia]) -> bool:
        """A regra mais especifica vence; usuario sempre precede grupo."""

        if not regras or any(not regra.ativo for regra in regras):
            return False
        if any(regra.distancia >= PROFUNDIDADE_MAXIMA and regra.possui_pai for regra in regras):
            return False

        regras_usuario = [regra for regra in regras if regra.vinculo_usuario is not None]
        if regras_usuario:
            regra = min(regras_usuario, key=lambda item: item.distancia)
            return regra.usuario_concede is True

        regras_grupo = [regra for regra in regras if regra.vinculo_grupo is not None]
        if regras_grupo:
            regra = min(regras_grupo, key=lambda item: item.distancia)
            return regra.grupo_concede is True
        return False

    def obter_revisao(self) -> int:
        """Le o contador monotonicamente crescente da autorizacao."""

        declaracao = select(RevisaoCache.revisao).where(
            RevisaoCache.namespace == NAMESPACE_REVISAO_AUTORIZACAO
        )
        try:
            with self._banco.leitura() as sessao:
                revisao = sessao.scalar(declaracao)
        except Exception as erro:
            raise ErroAutorizacao("Nao foi possivel comprovar a revisao das permissoes.") from erro
        return int(revisao or 0)

    def incrementar_revisao(self) -> int:
        """Invalida atomicamente caches depois de uma mudanca de permissao."""

        declaracao = (
            insert(RevisaoCache)
            .values(namespace=NAMESPACE_REVISAO_AUTORIZACAO, revisao=1)
            .on_conflict_do_update(
                index_elements=[RevisaoCache.namespace],
                set_={
                    "revisao": RevisaoCache.revisao + 1,
                    "data_atualizacao": func.now(),
                },
            )
            .returning(RevisaoCache.revisao)
        )
        try:
            with self._banco.unidade_trabalho() as sessao:
                revisao = sessao.execute(declaracao).scalar_one()
        except Exception as erro:
            raise ErroAutorizacao("Nao foi possivel invalidar o cache de permissoes.") from erro
        return int(revisao)
