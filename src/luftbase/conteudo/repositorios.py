"""Repositorios PostgreSQL de notificacoes e publicacoes."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from zoneinfo import ZoneInfo

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    delete,
    exists,
    func,
    literal_column,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session, selectinload

from luftbase.conteudo.modelos import (
    CategoriaNotificacao,
    NotificacaoUsuario,
    NovaNotificacao,
    NovaPublicacao,
    PaginaNotificacoes,
    PaginaPublicacoes,
    PublicacaoUsuario,
    TipoAudiencia,
    TipoPublicacao,
)
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado, ErroConteudo
from luftbase.persistencia.core.notificacoes import Notificacao, NotificacaoLeitura
from luftbase.persistencia.core.publicacoes import (
    NotaAtualizacaoItem,
    Publicacao,
    PublicacaoGrupo,
    PublicacaoLeitura,
    PublicacaoNotificacao,
)

_AGORA_BANCO: ColumnElement[datetime] = literal_column(
    "(CURRENT_TIMESTAMP AT TIME ZONE 'America/Sao_Paulo')"
)


def _agora_local() -> datetime:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)


def _json_texto(dados: Mapping[str, object] | None) -> str | None:
    if dados is None:
        return None
    try:
        return json.dumps(dados, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as erro:
        raise ErroConteudo("metadados deve conter somente valores JSON validos.") from erro


def _json_objeto(valor: str | None) -> object | None:
    if valor is None:
        return None
    try:
        return cast(object, json.loads(valor))
    except (TypeError, ValueError):
        # Dados legados invalidos continuam acessiveis sem derrubar a listagem.
        return None


def filtro_notificacao_visivel(
    id_sistema: int,
    id_usuario: int,
    id_grupo: int | None,
) -> ColumnElement[bool]:
    """Constroi uma unica politica SQL para audiencia, sistema e vigencia."""

    audiencias: list[ColumnElement[bool]] = [
        Notificacao.id_usuario_destino == id_usuario,
        and_(
            Notificacao.id_usuario_destino.is_(None),
            Notificacao.id_grupo_destino.is_(None),
        ),
    ]
    if id_grupo is not None:
        audiencias.append(
            and_(
                Notificacao.id_usuario_destino.is_(None),
                Notificacao.id_grupo_destino == id_grupo,
            )
        )
    return and_(
        or_(
            Notificacao.id_sistema == id_sistema,
            Notificacao.id_sistema == 0,
            Notificacao.id_sistema.is_(None),
        ),
        or_(*audiencias),
        or_(
            Notificacao.exibir_a_partir_de.is_(None), Notificacao.exibir_a_partir_de <= _AGORA_BANCO
        ),
        or_(Notificacao.expira_em.is_(None), Notificacao.expira_em > _AGORA_BANCO),
        # Arquivar a publicacao tambem recolhe a notificacao que ela emitiu.
        ~exists(
            select(PublicacaoNotificacao.id_vinculo)
            .join(Publicacao, Publicacao.id_publicacao == PublicacaoNotificacao.id_publicacao)
            .where(
                PublicacaoNotificacao.id_notificacao == Notificacao.id_notificacao,
                Publicacao.status_publicacao == "ARQUIVADO",
            )
        ),
    )


def filtro_publicacao_visivel(
    id_sistema: int,
    id_grupo: int | None,
) -> ColumnElement[bool]:
    """Constroi a politica SQL compartilhada pelo feed e pela leitura."""

    audiencia_grupo: ColumnElement[bool] = literal_column("false")
    if id_grupo is not None:
        audiencia_grupo = and_(
            Publicacao.tipo_audiencia == TipoAudiencia.GRUPOS.value,
            exists(
                select(PublicacaoGrupo.id_publicacao).where(
                    PublicacaoGrupo.id_publicacao == Publicacao.id_publicacao,
                    PublicacaoGrupo.id_grupo == id_grupo,
                )
            ),
        )
    return and_(
        Publicacao.id_sistema.in_((0, id_sistema)),
        or_(Publicacao.tipo_audiencia == TipoAudiencia.GERAL.value, audiencia_grupo),
        or_(
            Publicacao.status_publicacao == "PUBLICADO",
            and_(
                Publicacao.status_publicacao == "AGENDADO",
                Publicacao.exibir_a_partir_de <= _AGORA_BANCO,
            ),
        ),
        or_(Publicacao.exibir_a_partir_de.is_(None), Publicacao.exibir_a_partir_de <= _AGORA_BANCO),
        or_(Publicacao.expira_em.is_(None), Publicacao.expira_em > _AGORA_BANCO),
    )


class RepositorioNotificacoes:
    """Aplica audiencia e leitura individual sem carregar colecoes ORM."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def criar(self, id_sistema: int, dados: NovaNotificacao) -> int:
        """Cria uma notificacao em uma unidade de trabalho curta."""

        with self._banco.unidade_trabalho() as sessao:
            return self.adicionar(sessao, id_sistema, dados)

    @staticmethod
    def adicionar(sessao: Session, id_sistema: int, dados: NovaNotificacao) -> int:
        """Adiciona uma notificacao na transacao recebida e devolve seu ID."""

        entidade = Notificacao(
            id_sistema=id_sistema,
            id_usuario_destino=dados.id_usuario_destino,
            id_grupo_destino=dados.id_grupo_destino,
            tipo=dados.tipo.value,
            categoria=dados.categoria.value,
            titulo=dados.titulo,
            mensagem=dados.mensagem,
            icone=dados.icone,
            criado_por=dados.criado_por,
            metadados_json=_json_texto(dados.metadados),
            expira_em=dados.expira_em,
            exibir_a_partir_de=dados.exibir_a_partir_de,
        )
        sessao.add(entidade)
        sessao.flush()
        return entidade.id_notificacao

    def listar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        depois_de: int | None,
        limite: int,
        apenas_nao_lidas: bool = False,
    ) -> PaginaNotificacoes:
        """Lista a janela recente ou eventos posteriores a um cursor."""

        leitura_efetiva = case(
            (Notificacao.id_usuario_destino == id_usuario, Notificacao.lida),
            else_=NotificacaoLeitura.id_usuario.is_not(None),
        ).label("lida_efetiva")
        data_leitura_efetiva = case(
            (Notificacao.id_usuario_destino == id_usuario, Notificacao.data_leitura),
            else_=NotificacaoLeitura.data_leitura,
        ).label("data_leitura_efetiva")
        consulta = (
            select(
                Notificacao.id_notificacao,
                Notificacao.id_sistema,
                Notificacao.tipo,
                Notificacao.categoria,
                Notificacao.titulo,
                Notificacao.mensagem,
                Notificacao.icone,
                leitura_efetiva,
                Notificacao.data_criacao,
                data_leitura_efetiva,
                Notificacao.metadados_json,
                Notificacao.expira_em,
                Notificacao.exibir_a_partir_de,
            )
            .outerjoin(
                NotificacaoLeitura,
                and_(
                    NotificacaoLeitura.id_notificacao == Notificacao.id_notificacao,
                    NotificacaoLeitura.id_usuario == id_usuario,
                ),
            )
            .where(filtro_notificacao_visivel(id_sistema, id_usuario, id_grupo))
        )
        if apenas_nao_lidas:
            consulta = consulta.where(leitura_efetiva.is_(False))
        incremental = depois_de is not None
        if incremental:
            consulta = consulta.where(Notificacao.id_notificacao > depois_de).order_by(
                Notificacao.id_notificacao.asc()
            )
        else:
            consulta = consulta.order_by(Notificacao.id_notificacao.desc())
        with self._banco.leitura() as sessao:
            linhas = list(sessao.execute(consulta.limit(limite + 1)).mappings())
        tem_mais = incremental and len(linhas) > limite
        linhas = linhas[:limite]
        if not incremental:
            linhas.reverse()
        itens = tuple(self._notificacao_da_linha(linha) for linha in linhas)
        cursor_inicial = depois_de or 0
        proximo_cursor = max((item.id_notificacao for item in itens), default=cursor_inicial)
        return PaginaNotificacoes(itens, proximo_cursor, tem_mais)

    def marcar_lida(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_notificacao: int,
    ) -> bool:
        """Registra a leitura de forma idempotente e informa se houve mudanca."""

        with self._banco.unidade_trabalho() as sessao:
            destino = sessao.execute(
                select(
                    Notificacao.id_usuario_destino,
                    Notificacao.lida,
                )
                .where(
                    Notificacao.id_notificacao == id_notificacao,
                    filtro_notificacao_visivel(id_sistema, id_usuario, id_grupo),
                )
                .with_for_update()
            ).one_or_none()
            if destino is None:
                raise ConteudoNaoEncontrado("Notificacao nao encontrada para este usuario.")
            id_destino, lida = destino
            houve_mudanca = False
            if id_destino == id_usuario:
                if not bool(lida):
                    sessao.execute(
                        update(Notificacao)
                        .where(
                            Notificacao.id_notificacao == id_notificacao,
                            Notificacao.lida.is_(False),
                        )
                        .values(lida=True, data_leitura=_agora_local())
                    )
                    houve_mudanca = True
            else:
                resultado = sessao.execute(
                    insert(NotificacaoLeitura)
                    .values(id_notificacao=id_notificacao, id_usuario=id_usuario)
                    .on_conflict_do_nothing(
                        index_elements=(
                            NotificacaoLeitura.id_notificacao,
                            NotificacaoLeitura.id_usuario,
                        )
                    )
                    .returning(NotificacaoLeitura.id_notificacao)
                ).scalar_one_or_none()
                houve_mudanca = resultado is not None

            # Sincroniza leitura de publicacao vinculada, se houver
            id_pub = sessao.scalar(
                select(PublicacaoNotificacao.id_publicacao).where(
                    PublicacaoNotificacao.id_notificacao == id_notificacao
                )
            )
            if id_pub is not None:
                sessao.execute(
                    insert(PublicacaoLeitura)
                    .values(id_publicacao=id_pub, id_usuario=id_usuario)
                    .on_conflict_do_nothing(
                        index_elements=(
                            PublicacaoLeitura.id_publicacao,
                            PublicacaoLeitura.id_usuario,
                        )
                    )
                )

            return houve_mudanca

    def marcar_todas_lidas(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        """Marca todas as notificacoes visiveis e nao lidas do usuario."""

        with self._banco.unidade_trabalho() as sessao:
            ids_individuais = (
                sessao.execute(
                    update(Notificacao)
                    .where(
                        Notificacao.id_usuario_destino == id_usuario,
                        Notificacao.lida.is_(False),
                        filtro_notificacao_visivel(id_sistema, id_usuario, id_grupo),
                    )
                    .values(lida=True, data_leitura=_agora_local())
                    .returning(Notificacao.id_notificacao)
                )
                .scalars()
                .all()
            )
            total_individuais = len(ids_individuais)

            subq_lidas = select(NotificacaoLeitura.id_notificacao).where(
                NotificacaoLeitura.id_usuario == id_usuario
            )
            nao_lidas_coletivas = (
                sessao.execute(
                    select(Notificacao.id_notificacao).where(
                        or_(
                            Notificacao.id_usuario_destino.is_(None),
                            Notificacao.id_usuario_destino != id_usuario,
                        ),
                        filtro_notificacao_visivel(id_sistema, id_usuario, id_grupo),
                        Notificacao.id_notificacao.not_in(subq_lidas),
                    )
                )
                .scalars()
                .all()
            )

            total_coletivas = 0
            if nao_lidas_coletivas:
                registros = [
                    {"id_notificacao": id_notif, "id_usuario": id_usuario}
                    for id_notif in nao_lidas_coletivas
                ]
                sessao.execute(
                    insert(NotificacaoLeitura).on_conflict_do_nothing(
                        index_elements=(
                            NotificacaoLeitura.id_notificacao,
                            NotificacaoLeitura.id_usuario,
                        )
                    ),
                    registros,
                )
                total_coletivas = len(nao_lidas_coletivas)

            todos_ids = set(ids_individuais) | set(nao_lidas_coletivas)
            if todos_ids:
                pubs = (
                    sessao.execute(
                        select(PublicacaoNotificacao.id_publicacao)
                        .where(PublicacaoNotificacao.id_notificacao.in_(todos_ids))
                        .distinct()
                    )
                    .scalars()
                    .all()
                )
                if pubs:
                    sessao.execute(
                        insert(PublicacaoLeitura).on_conflict_do_nothing(
                            index_elements=(
                                PublicacaoLeitura.id_publicacao,
                                PublicacaoLeitura.id_usuario,
                            )
                        ),
                        [{"id_publicacao": pid, "id_usuario": id_usuario} for pid in pubs],
                    )

            return total_individuais + total_coletivas

    def contar_nao_lidas(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        """Conta notificacoes nao lidas visiveis para o usuario."""

        leitura_efetiva = case(
            (Notificacao.id_usuario_destino == id_usuario, Notificacao.lida),
            else_=NotificacaoLeitura.id_usuario.is_not(None),
        ).label("lida_efetiva")
        consulta = (
            select(func.count(Notificacao.id_notificacao))
            .outerjoin(
                NotificacaoLeitura,
                and_(
                    NotificacaoLeitura.id_notificacao == Notificacao.id_notificacao,
                    NotificacaoLeitura.id_usuario == id_usuario,
                ),
            )
            .where(
                filtro_notificacao_visivel(id_sistema, id_usuario, id_grupo),
                leitura_efetiva.is_(False),
            )
        )
        with self._banco.leitura() as sessao:
            total = sessao.scalar(consulta)
            return int(total or 0)

    def limpar_expiradas(self, *, antes_de: datetime | None = None) -> int:
        """Remove notificacoes cujo prazo expira_em seja anterior ao limite informado."""

        limite = antes_de or _agora_local()
        with self._banco.unidade_trabalho() as sessao:
            resultado = sessao.execute(
                delete(Notificacao).where(
                    Notificacao.expira_em.is_not(None),
                    Notificacao.expira_em < limite,
                )
            )
            return int(getattr(resultado, "rowcount", 0))

    @staticmethod
    def _notificacao_da_linha(linha: RowMapping) -> NotificacaoUsuario:
        return NotificacaoUsuario(
            id_notificacao=linha["id_notificacao"],
            id_sistema=linha["id_sistema"],
            tipo=linha["tipo"],
            categoria=linha["categoria"],
            titulo=linha["titulo"],
            mensagem=linha["mensagem"],
            icone=linha["icone"],
            lida=bool(linha["lida_efetiva"]),
            data_criacao=linha["data_criacao"],
            data_leitura=linha["data_leitura_efetiva"],
            metadados=_json_objeto(linha["metadados_json"]),
            expira_em=linha["expira_em"],
            exibir_a_partir_de=linha["exibir_a_partir_de"],
        )


@dataclass(frozen=True, slots=True)
class ResultadoPublicacao:
    """Resultado transacional usado para sinalizar somente depois do commit."""

    id_publicacao: int
    ids_notificacoes: tuple[int, ...] = ()
    alterada: bool = True


class RepositorioPublicacoes:
    """Mantem rascunhos, publicacao atomica, audiencia e recibos de leitura."""

    def __init__(self, banco: BancoSQLAlchemy) -> None:
        self._banco = banco

    def criar_rascunho(self, id_sistema: int, dados: NovaPublicacao) -> ResultadoPublicacao:
        """Cria um rascunho, reutilizando a chave externa quando informada."""

        with self._banco.unidade_trabalho() as sessao:
            if dados.id_externo:
                existente = sessao.scalar(
                    select(Publicacao.id_publicacao).where(
                        Publicacao.fonte == dados.fonte,
                        Publicacao.id_externo == dados.id_externo,
                    )
                )
                if existente is not None:
                    return ResultadoPublicacao(existente, alterada=False)
            entidade = Publicacao(
                id_sistema=id_sistema,
                tipo_publicacao=dados.tipo.value,
                status_publicacao="RASCUNHO",
                tipo_audiencia=dados.audiencia.value,
                titulo=dados.titulo,
                resumo=dados.resumo,
                conteudo=dados.conteudo,
                prioridade=dados.prioridade.value,
                versao=dados.versao,
                notificar=dados.notificar,
                fixado=dados.fixado,
                exibir_a_partir_de=dados.exibir_a_partir_de,
                expira_em=dados.expira_em,
                criado_por_id=dados.criado_por_id,
                criado_por=dados.criado_por,
                fonte=dados.fonte,
                id_externo=dados.id_externo,
                url_externa=dados.url_externa,
                metadados_json=_json_texto(dados.metadados),
            )
            sessao.add(entidade)
            sessao.flush()
            for id_grupo in dados.ids_grupos:
                sessao.add(PublicacaoGrupo(id_publicacao=entidade.id_publicacao, id_grupo=id_grupo))
            for item in dados.itens_atualizacao:
                sessao.add(
                    NotaAtualizacaoItem(
                        id_publicacao=entidade.id_publicacao,
                        tipo_item=item.tipo.value,
                        titulo=item.titulo,
                        descricao=item.descricao,
                        ordem=item.ordem,
                    )
                )
            return ResultadoPublicacao(entidade.id_publicacao)

    def publicar(self, id_sistema: int, id_publicacao: int) -> ResultadoPublicacao:
        """Publica e cria notificacoes vinculadas na mesma transacao."""

        with self._banco.unidade_trabalho() as sessao:
            publicacao = sessao.scalar(
                select(Publicacao)
                .where(
                    Publicacao.id_publicacao == id_publicacao,
                    Publicacao.id_sistema == id_sistema,
                )
                .with_for_update()
            )
            if publicacao is None:
                raise ConteudoNaoEncontrado("Publicacao nao encontrada no sistema atual.")
            if publicacao.status_publicacao in {"PUBLICADO", "AGENDADO"}:
                return ResultadoPublicacao(id_publicacao, alterada=False)
            if publicacao.status_publicacao == "ARQUIVADO":
                raise ErroConteudo("Publicacao arquivada nao pode ser publicada.")

            agora = _agora_local()
            agendada = bool(publicacao.exibir_a_partir_de and publicacao.exibir_a_partir_de > agora)
            publicacao.status_publicacao = "AGENDADO" if agendada else "PUBLICADO"
            publicacao.data_publicacao = None if agendada else agora
            publicacao.data_atualizacao = agora
            ids_notificacoes: list[int] = []
            if publicacao.notificar:
                ids_grupos = (
                    tuple(
                        sessao.scalars(
                            select(PublicacaoGrupo.id_grupo).where(
                                PublicacaoGrupo.id_publicacao == id_publicacao
                            )
                        )
                    )
                    if publicacao.tipo_audiencia == TipoAudiencia.GRUPOS.value
                    else (None,)
                )
                for id_grupo in ids_grupos:
                    notificacao = NovaNotificacao(
                        titulo=publicacao.titulo,
                        mensagem=publicacao.resumo or publicacao.conteudo,
                        categoria=(
                            CategoriaNotificacao.ATUALIZACAO
                            if publicacao.tipo_publicacao == TipoPublicacao.ATUALIZACAO.value
                            else CategoriaNotificacao.COMUNICADO
                        ),
                        id_grupo_destino=id_grupo,
                        criado_por=publicacao.criado_por,
                        metadados={"id_publicacao": id_publicacao},
                        expira_em=publicacao.expira_em,
                        exibir_a_partir_de=publicacao.exibir_a_partir_de,
                    )
                    id_notificacao = RepositorioNotificacoes.adicionar(
                        sessao,
                        id_sistema,
                        notificacao,
                    )
                    ids_notificacoes.append(id_notificacao)
                    sessao.add(
                        PublicacaoNotificacao(
                            id_publicacao=id_publicacao,
                            id_notificacao=id_notificacao,
                        )
                    )
            return ResultadoPublicacao(id_publicacao, tuple(ids_notificacoes))

    def atualizar_rascunho(
        self, id_sistema: int, id_publicacao: int, dados: NovaPublicacao
    ) -> ResultadoPublicacao:
        """Atualiza um rascunho existente se ele pertencer ao sistema informado."""

        with self._banco.unidade_trabalho() as sessao:
            publicacao = sessao.scalar(
                select(Publicacao)
                .where(
                    Publicacao.id_publicacao == id_publicacao,
                    Publicacao.id_sistema == id_sistema,
                )
                .with_for_update()
            )
            if publicacao is None:
                raise ConteudoNaoEncontrado("Publicacao nao encontrada no sistema atual.")
            if publicacao.status_publicacao != "RASCUNHO":
                raise ErroConteudo("Apenas rascunhos podem ser editados.")

            publicacao.titulo = dados.titulo
            publicacao.resumo = dados.resumo
            publicacao.conteudo = dados.conteudo
            publicacao.tipo_audiencia = dados.audiencia.value
            publicacao.prioridade = dados.prioridade.value
            publicacao.versao = dados.versao
            publicacao.notificar = dados.notificar
            publicacao.fixado = dados.fixado
            publicacao.exibir_a_partir_de = dados.exibir_a_partir_de
            publicacao.expira_em = dados.expira_em
            publicacao.metadados_json = _json_texto(dados.metadados)
            publicacao.data_atualizacao = _agora_local()

            sessao.execute(
                delete(PublicacaoGrupo).where(PublicacaoGrupo.id_publicacao == id_publicacao)
            )
            for id_grupo in dados.ids_grupos:
                sessao.add(PublicacaoGrupo(id_publicacao=id_publicacao, id_grupo=id_grupo))

            sessao.execute(
                delete(NotaAtualizacaoItem).where(
                    NotaAtualizacaoItem.id_publicacao == id_publicacao
                )
            )
            for item in dados.itens_atualizacao:
                sessao.add(
                    NotaAtualizacaoItem(
                        id_publicacao=id_publicacao,
                        tipo_item=item.tipo.value,
                        titulo=item.titulo,
                        descricao=item.descricao,
                        ordem=item.ordem,
                    )
                )
            return ResultadoPublicacao(id_publicacao)

    def arquivar(self, id_sistema: int, id_publicacao: int) -> bool:
        """Arquiva uma publicacao do sistema informado."""

        with self._banco.unidade_trabalho() as sessao:
            publicacao = sessao.scalar(
                select(Publicacao)
                .where(
                    Publicacao.id_publicacao == id_publicacao,
                    Publicacao.id_sistema == id_sistema,
                )
                .with_for_update()
            )
            if publicacao is None:
                raise ConteudoNaoEncontrado("Publicacao nao encontrada no sistema atual.")
            if publicacao.status_publicacao == "ARQUIVADO":
                return False
            publicacao.status_publicacao = "ARQUIVADO"
            publicacao.data_atualizacao = _agora_local()
            return True

    def listar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        depois_de: int | None,
        limite: int,
    ) -> PaginaPublicacoes:
        """Lista uma janela recente ou publicacoes posteriores ao cursor."""

        consulta = (
            select(
                Publicacao.id_publicacao,
                Publicacao.id_sistema,
                Publicacao.tipo_publicacao,
                Publicacao.tipo_audiencia,
                Publicacao.titulo,
                Publicacao.resumo,
                Publicacao.prioridade,
                Publicacao.versao,
                Publicacao.fixado,
                Publicacao.exibir_a_partir_de,
                Publicacao.expira_em,
                Publicacao.data_publicacao,
                PublicacaoLeitura.id_usuario.is_not(None).label("lida_efetiva"),
            )
            .outerjoin(
                PublicacaoLeitura,
                and_(
                    PublicacaoLeitura.id_publicacao == Publicacao.id_publicacao,
                    PublicacaoLeitura.id_usuario == id_usuario,
                ),
            )
            .where(filtro_publicacao_visivel(id_sistema, id_grupo))
        )
        incremental = depois_de is not None
        if incremental:
            consulta = consulta.where(Publicacao.id_publicacao > depois_de).order_by(
                Publicacao.id_publicacao.asc()
            )
        else:
            consulta = consulta.order_by(Publicacao.id_publicacao.desc())
        with self._banco.leitura() as sessao:
            linhas = list(sessao.execute(consulta.limit(limite + 1)).mappings())
        tem_mais = incremental and len(linhas) > limite
        linhas = linhas[:limite]
        if not incremental:
            linhas.reverse()
        itens = tuple(self._publicacao_da_linha(linha) for linha in linhas)
        cursor_inicial = depois_de or 0
        proximo_cursor = max((item.id_publicacao for item in itens), default=cursor_inicial)
        return PaginaPublicacoes(itens, proximo_cursor, tem_mais)

    def obter(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> PublicacaoUsuario:
        """Busca o conteudo completo somente quando o usuario pode ve-lo."""

        consulta = (
            select(
                Publicacao.id_publicacao,
                Publicacao.id_sistema,
                Publicacao.tipo_publicacao,
                Publicacao.tipo_audiencia,
                Publicacao.titulo,
                Publicacao.resumo,
                Publicacao.conteudo,
                Publicacao.prioridade,
                Publicacao.versao,
                Publicacao.fixado,
                Publicacao.exibir_a_partir_de,
                Publicacao.expira_em,
                Publicacao.data_publicacao,
                PublicacaoLeitura.id_usuario.is_not(None).label("lida_efetiva"),
            )
            .outerjoin(
                PublicacaoLeitura,
                and_(
                    PublicacaoLeitura.id_publicacao == Publicacao.id_publicacao,
                    PublicacaoLeitura.id_usuario == id_usuario,
                ),
            )
            .where(
                Publicacao.id_publicacao == id_publicacao,
                filtro_publicacao_visivel(id_sistema, id_grupo),
            )
        )
        with self._banco.leitura() as sessao:
            linha = sessao.execute(consulta).mappings().one_or_none()
        if linha is None:
            raise ConteudoNaoEncontrado("Publicacao nao encontrada para este usuario.")
        return self._publicacao_da_linha(linha, incluir_conteudo=True)

    def marcar_lida(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> bool:
        """Insere o recibo uma unica vez e rejeita publicacao invisivel."""

        with self._banco.unidade_trabalho() as sessao:
            visivel = sessao.scalar(
                select(Publicacao.id_publicacao).where(
                    Publicacao.id_publicacao == id_publicacao,
                    filtro_publicacao_visivel(id_sistema, id_grupo),
                )
            )
            if visivel is None:
                raise ConteudoNaoEncontrado("Publicacao nao encontrada para este usuario.")
            resultado = sessao.execute(
                insert(PublicacaoLeitura)
                .values(id_publicacao=id_publicacao, id_usuario=id_usuario)
                .on_conflict_do_nothing(
                    index_elements=(
                        PublicacaoLeitura.id_publicacao,
                        PublicacaoLeitura.id_usuario,
                    )
                )
                .returning(PublicacaoLeitura.id_publicacao)
            ).scalar_one_or_none()

            # Sincroniza notificações associadas a esta publicação como lidas para o usuário
            ids_notifs = (
                sessao.execute(
                    select(PublicacaoNotificacao.id_notificacao).where(
                        PublicacaoNotificacao.id_publicacao == id_publicacao
                    )
                )
                .scalars()
                .all()
            )
            if ids_notifs:
                sessao.execute(
                    update(Notificacao)
                    .where(
                        Notificacao.id_notificacao.in_(ids_notifs),
                        Notificacao.id_usuario_destino == id_usuario,
                        Notificacao.lida.is_(False),
                    )
                    .values(lida=True, data_leitura=_agora_local())
                )
                sessao.execute(
                    insert(NotificacaoLeitura).on_conflict_do_nothing(
                        index_elements=(
                            NotificacaoLeitura.id_notificacao,
                            NotificacaoLeitura.id_usuario,
                        )
                    ),
                    [{"id_notificacao": n_id, "id_usuario": id_usuario} for n_id in ids_notifs],
                )

            return resultado is not None

    @staticmethod
    def consulta_administracao(
        id_sistema: int,
        tipo: TipoPublicacao | None,
        limite: int,
        offset: int,
    ) -> Select[tuple[Publicacao]]:
        """Monta a consulta da gestao: o Workspace ve tudo; um sistema, as suas e as globais.

        As globais (`id_sistema = 0`) aparecem para quem as recebe (feed), mas so as ja visiveis
        (publicadas ou agendadas): rascunhos e arquivadas pertencem ao Workspace. A gestao delas
        continua restrita ao proprio Workspace (`obter_administracao`, `atualizar_rascunho` e
        `arquivar` filtram pelo sistema).
        """

        consulta = (
            select(Publicacao)
            .options(
                selectinload(Publicacao.grupos),
                selectinload(Publicacao.itens_atualizacao),
            )
            .order_by(Publicacao.id_publicacao.desc())
        )
        if id_sistema != 0:
            consulta = consulta.where(
                or_(
                    Publicacao.id_sistema == id_sistema,
                    and_(
                        Publicacao.id_sistema == 0,
                        Publicacao.status_publicacao.in_(("PUBLICADO", "AGENDADO")),
                    ),
                )
            )
        if tipo is not None:
            consulta = consulta.where(Publicacao.tipo_publicacao == tipo.value)
        return consulta.limit(limite).offset(offset)

    def listar_administracao(
        self,
        *,
        id_sistema: int,
        tipo: TipoPublicacao | None = None,
        limite: int = 50,
        offset: int = 0,
    ) -> list[Publicacao]:
        """Lista publicacoes para gestao administrativa com seus relacionamentos."""

        consulta = self.consulta_administracao(id_sistema, tipo, limite, offset)
        with self._banco.leitura() as sessao:
            return list(sessao.scalars(consulta).all())

    def obter_administracao(
        self,
        *,
        id_sistema: int,
        id_publicacao: int,
    ) -> Publicacao:
        """Obtem uma publicacao com seus relacionamentos para gestao administrativa."""

        consulta = (
            select(Publicacao)
            .options(
                selectinload(Publicacao.grupos),
                selectinload(Publicacao.itens_atualizacao),
            )
            .where(Publicacao.id_publicacao == id_publicacao)
        )
        if id_sistema != 0:
            consulta = consulta.where(Publicacao.id_sistema == id_sistema)

        with self._banco.leitura() as sessao:
            item = sessao.scalar(consulta)
        if item is None:
            raise ConteudoNaoEncontrado("Publicacao nao encontrada.")
        return item

    @staticmethod
    def _publicacao_da_linha(
        linha: RowMapping,
        *,
        incluir_conteudo: bool = False,
    ) -> PublicacaoUsuario:
        return PublicacaoUsuario(
            id_publicacao=linha["id_publicacao"],
            id_sistema=linha["id_sistema"],
            tipo=linha["tipo_publicacao"],
            audiencia=linha["tipo_audiencia"],
            titulo=linha["titulo"],
            resumo=linha["resumo"],
            conteudo=linha.get("conteudo") if incluir_conteudo else None,
            prioridade=linha["prioridade"],
            versao=linha["versao"],
            fixado=bool(linha["fixado"]),
            lida=bool(linha["lida_efetiva"]),
            exibir_a_partir_de=linha["exibir_a_partir_de"],
            expira_em=linha["expira_em"],
            data_publicacao=linha["data_publicacao"],
        )
