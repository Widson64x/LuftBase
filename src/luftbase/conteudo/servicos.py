"""Casos de uso de notificacoes e publicacoes."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from luftbase.conteudo.modelos import (
    ComunicadoExterno,
    NovaNotificacao,
    NovaPublicacao,
    PaginaNotificacoes,
    PaginaPublicacoes,
    ProvedorComunicados,
    PublicacaoUsuario,
    TipoAudiencia,
    TipoPublicacao,
)
from luftbase.conteudo.repositorios import ResultadoPublicacao
from luftbase.conteudo.sinalizacao import SinalizadorConteudoRedis
from luftbase.nucleo.excecoes import ErroConteudo
from luftbase.persistencia.core.publicacoes import Publicacao


class PortaNotificacoes(Protocol):
    """Operacoes persistentes exigidas pelo servico de notificacoes."""

    def criar(self, id_sistema: int, dados: NovaNotificacao) -> int:
        """Cria e devolve o identificador."""

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
        """Lista notificacoes visiveis."""

    def marcar_lida(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_notificacao: int,
    ) -> bool:
        """Persiste o recibo de leitura."""

    def marcar_todas_lidas(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        """Persiste o recibo de leitura de todas as notificacoes visiveis."""

    def ocultar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_notificacao: int,
    ) -> bool:
        """Some com uma notificacao so da lista da pessoa."""

    def ocultar_todas(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        apenas_lidas: bool = False,
    ) -> int:
        """Some com as notificacoes visiveis da pessoa."""

    def contar_nao_lidas(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        """Conta notificacoes nao lidas visiveis para o usuario."""

    def limpar_expiradas(self, *, antes_de: datetime | None = None) -> int:
        """Remove notificacoes expiradas."""


class PortaPublicacoes(Protocol):
    """Operacoes persistentes exigidas pelo servico de publicacoes."""

    def criar_rascunho(self, id_sistema: int, dados: NovaPublicacao) -> ResultadoPublicacao:
        """Cria ou recupera um rascunho idempotente."""

    def publicar(self, id_sistema: int, id_publicacao: int) -> ResultadoPublicacao:
        """Publica e cria notificacoes na mesma transacao."""

    def listar(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        depois_de: int | None,
        limite: int,
    ) -> PaginaPublicacoes:
        """Lista publicacoes visiveis."""

    def obter(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> PublicacaoUsuario:
        """Obtem uma publicacao visivel."""

    def marcar_lida(
        self,
        *,
        id_sistema: int,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> bool:
        """Persiste o recibo de leitura."""

    def atualizar_rascunho(
        self, id_sistema: int, id_publicacao: int, dados: NovaPublicacao
    ) -> ResultadoPublicacao:
        """Atualiza um rascunho existente."""

    def arquivar(self, id_sistema: int, id_publicacao: int) -> bool:
        """Arquiva uma publicacao."""

    def listar_administracao(
        self,
        *,
        id_sistema: int,
        tipo: TipoPublicacao | None = None,
        limite: int = 50,
        offset: int = 0,
    ) -> list[Publicacao]:
        """Lista publicacoes para gestao administrativa."""

    def obter_administracao(
        self,
        *,
        id_sistema: int,
        id_publicacao: int,
    ) -> Publicacao:
        """Obtem uma publicacao para gestao administrativa."""


def _validar_consulta(cursor: int | None, limite: int) -> None:
    if cursor is not None and cursor < 0:
        raise ErroConteudo("cursor nao pode ser negativo.")
    if not 1 <= limite <= 100:
        raise ErroConteudo("limite deve estar entre 1 e 100.")


class ServicoNotificacoes:
    """Orquestra notificacoes com PostgreSQL autoritativo e sinal descartavel."""

    def __init__(
        self,
        id_sistema: int,
        repositorio: PortaNotificacoes,
        sinalizador: SinalizadorConteudoRedis,
    ) -> None:
        self._id_sistema = id_sistema
        self._repositorio = repositorio
        self._sinalizador = sinalizador

    def criar(self, dados: NovaNotificacao) -> int:
        """Cria no PostgreSQL e somente depois atualiza o sinal Redis."""

        id_notificacao = self._repositorio.criar(self._id_sistema, dados)
        self._sinalizador.publicar("notificacoes", self._id_sistema, id_notificacao)
        return id_notificacao

    def listar_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        *,
        cursor: int | None = None,
        limite: int = 30,
        apenas_nao_lidas: bool = False,
    ) -> PaginaNotificacoes:
        """Le uma janela limitada; cursor ausente devolve somente os mais recentes."""

        _validar_consulta(cursor, limite)
        return self._repositorio.listar(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            depois_de=cursor,
            limite=limite,
            apenas_nao_lidas=apenas_nao_lidas,
        )

    def marcar_lida(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_notificacao: int,
    ) -> bool:
        """Marca uma notificacao visivel, sem duplicar recibos."""

        if id_notificacao <= 0:
            raise ErroConteudo("id_notificacao deve ser positivo.")
        return self._repositorio.marcar_lida(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            id_notificacao=id_notificacao,
        )

    def marcar_todas_lidas(
        self,
        id_usuario: int,
        id_grupo: int | None,
    ) -> int:
        """Marca todas as notificacoes visiveis do usuario como lidas."""

        return self._repositorio.marcar_todas_lidas(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
        )

    def ocultar(self, id_usuario: int, id_grupo: int | None, id_notificacao: int) -> bool:
        """Limpa UMA notificacao da lista da pessoa; ela continua existindo para as demais."""

        if id_notificacao <= 0:
            raise ErroConteudo("id_notificacao deve ser positivo.")
        return self._repositorio.ocultar(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            id_notificacao=id_notificacao,
        )

    def ocultar_todas(
        self, id_usuario: int, id_grupo: int | None, *, apenas_lidas: bool = False
    ) -> int:
        """Limpa as notificacoes da lista da pessoa (todas, ou so as ja lidas)."""

        return self._repositorio.ocultar_todas(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            apenas_lidas=apenas_lidas,
        )

    def contar_nao_lidas(self, id_usuario: int, id_grupo: int | None) -> int:
        """Conta notificacoes nao lidas visiveis para o usuario."""

        return self._repositorio.contar_nao_lidas(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
        )

    def limpar_expiradas(self, *, antes_de: datetime | None = None) -> int:
        """Remove notificacoes expiradas."""

        return self._repositorio.limpar_expiradas(antes_de=antes_de)

    def ultimo_cursor_sinalizado(self) -> int | None:
        """Consulta o cache Redis sem assumir que ele esta completo."""

        return self._sinalizador.obter_cursor("notificacoes", self._id_sistema)


class ServicoPublicacoes:
    """Orquestra publicacoes e seus recibos no sistema atual."""

    def __init__(
        self,
        id_sistema: int,
        repositorio: PortaPublicacoes,
        sinalizador: SinalizadorConteudoRedis,
    ) -> None:
        self._id_sistema = id_sistema
        self._repositorio = repositorio
        self._sinalizador = sinalizador

    def criar_rascunho(self, dados: NovaPublicacao) -> int:
        """Cria um rascunho, com idempotencia opcional pela origem externa."""

        resultado = self._repositorio.criar_rascunho(self._id_sistema, dados)
        return resultado.id_publicacao

    def publicar(self, id_publicacao: int) -> bool:
        """Publica atomicamente e sinaliza cursores apenas depois do commit."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        resultado = self._repositorio.publicar(self._id_sistema, id_publicacao)
        if not resultado.alterada:
            return False
        self._sinalizador.publicar(
            "publicacoes",
            self._id_sistema,
            resultado.id_publicacao,
        )
        for id_notificacao in resultado.ids_notificacoes:
            self._sinalizador.publicar(
                "notificacoes",
                self._id_sistema,
                id_notificacao,
            )
        return True

    def listar_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        *,
        cursor: int | None = None,
        limite: int = 30,
    ) -> PaginaPublicacoes:
        """Le uma janela limitada do feed."""

        _validar_consulta(cursor, limite)
        return self._repositorio.listar(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            depois_de=cursor,
            limite=limite,
        )

    def obter_para_usuario(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> PublicacaoUsuario:
        """Obtem o conteudo completo sem transformar GET em escrita."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        return self._repositorio.obter(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            id_publicacao=id_publicacao,
        )

    def marcar_lida(
        self,
        id_usuario: int,
        id_grupo: int | None,
        id_publicacao: int,
    ) -> bool:
        """Registra a leitura com operacao explicita e idempotente."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        return self._repositorio.marcar_lida(
            id_sistema=self._id_sistema,
            id_usuario=id_usuario,
            id_grupo=id_grupo,
            id_publicacao=id_publicacao,
        )

    def ultimo_cursor_sinalizado(self) -> int | None:
        """Consulta o cache Redis sem usa-lo como fonte de dados."""

        return self._sinalizador.obter_cursor("publicacoes", self._id_sistema)

    def atualizar_rascunho(self, id_publicacao: int, dados: NovaPublicacao) -> bool:
        """Atualiza um rascunho existente."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        resultado = self._repositorio.atualizar_rascunho(self._id_sistema, id_publicacao, dados)
        return resultado.alterada

    def corrigir_texto(self, id_publicacao: int, dados: NovaPublicacao) -> bool:
        """Corrige titulo, resumo e conteudo de uma publicacao ja publicada, sem renotificar."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        return self._repositorio.corrigir_texto(
            self._id_sistema,
            id_publicacao,
            titulo=dados.titulo,
            resumo=dados.resumo,
            conteudo=dados.conteudo,
        )

    def arquivar(self, id_publicacao: int) -> bool:
        """Arquiva uma publicacao."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        return self._repositorio.arquivar(self._id_sistema, id_publicacao)

    def listar_administracao(
        self,
        *,
        tipo: TipoPublicacao | None = None,
        limite: int = 50,
        offset: int = 0,
    ) -> list[Publicacao]:
        """Lista publicacoes para gestao administrativa."""

        if not 1 <= limite <= 100:
            raise ErroConteudo("limite deve estar entre 1 e 100.")
        if offset < 0:
            raise ErroConteudo("offset nao pode ser negativo.")
        return self._repositorio.listar_administracao(
            id_sistema=self._id_sistema,
            tipo=tipo,
            limite=limite,
            offset=offset,
        )

    def obter_administracao(self, id_publicacao: int) -> Publicacao:
        """Obtem uma publicacao para gestao administrativa."""

        if id_publicacao <= 0:
            raise ErroConteudo("id_publicacao deve ser positivo.")
        return self._repositorio.obter_administracao(
            id_sistema=self._id_sistema,
            id_publicacao=id_publicacao,
        )

    def importar_comunicado_externo(self, comunicado: ComunicadoExterno) -> int:
        """Importa comunicado de fonte externa (idempotente por id_externo + fonte)."""

        nova_pub = NovaPublicacao(
            titulo=comunicado.titulo,
            conteudo=comunicado.conteudo,
            resumo=comunicado.resumo,
            criado_por=comunicado.criado_por,
            tipo=TipoPublicacao.COMUNICADO,
            audiencia=TipoAudiencia.GERAL,
            prioridade=comunicado.prioridade,
            versao=comunicado.versao,
            fonte=comunicado.fonte,
            id_externo=comunicado.id_externo,
            url_externa=comunicado.url_externa,
            exibir_a_partir_de=comunicado.data_publicacao,
            expira_em=comunicado.expira_em,
            metadados=comunicado.metadados,
            notificar=False,
        )
        resultado = self._repositorio.criar_rascunho(self._id_sistema, nova_pub)
        return resultado.id_publicacao

    def sincronizar_provedor(self, provedor: ProvedorComunicados) -> list[int]:
        """Sincroniza multiplos comunicados a partir de um provedor externo."""

        comunicados = provedor.obter_comunicados()
        return [self.importar_comunicado_externo(c) for c in comunicados]
