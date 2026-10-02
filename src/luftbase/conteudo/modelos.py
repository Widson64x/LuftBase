"""Contratos imutaveis de notificacoes e publicacoes."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from luftbase.nucleo.excecoes import ErroConteudo


class TipoNotificacao(StrEnum):
    """Tipos persistidos de notificacao."""

    SISTEMA = "SISTEMA"
    ALERTA = "ALERTA"
    INFO = "INFO"
    SUCESSO = "SUCESSO"
    ERRO = "ERRO"


class CategoriaNotificacao(StrEnum):
    """Categorias persistidas de notificacao."""

    ETL = "ETL"
    SEGURANCA = "SEGURANCA"
    BANCO = "BANCO"
    SERVICO = "SERVICO"
    GERAL = "GERAL"
    USUARIO = "USUARIO"
    CONFIGURACAO = "CONFIGURACAO"
    INTEGRACAO = "INTEGRACAO"
    COMUNICADO = "COMUNICADO"
    ATUALIZACAO = "ATUALIZACAO"


class TipoPublicacao(StrEnum):
    """Tipos publicos de publicacao."""

    COMUNICADO = "COMUNICADO"
    ATUALIZACAO = "ATUALIZACAO"


class TipoAudiencia(StrEnum):
    """Formas suportadas de selecionar a audiencia."""

    GERAL = "GERAL"
    GRUPOS = "GRUPOS"


class PrioridadePublicacao(StrEnum):
    """Prioridades de exibicao da publicacao."""

    BAIXA = "BAIXA"
    NORMAL = "NORMAL"
    ALTA = "ALTA"
    CRITICA = "CRITICA"


class TipoItemAtualizacao(StrEnum):
    """Tipos de item de uma nota de atualizacao."""

    NOVO = "NOVO"
    MELHORIA = "MELHORIA"
    CORRECAO = "CORRECAO"
    SEGURANCA = "SEGURANCA"
    TECNICO = "TECNICO"


def _texto_obrigatorio(valor: str, campo: str, maximo: int | None = None) -> str:
    texto = valor.strip()
    if not texto:
        raise ErroConteudo(f"{campo} e obrigatorio.")
    if maximo is not None and len(texto) > maximo:
        raise ErroConteudo(f"{campo} deve ter no maximo {maximo} caracteres.")
    return texto


def _validar_vigencia(inicio: datetime | None, fim: datetime | None) -> None:
    if inicio is not None and fim is not None and fim <= inicio:
        raise ErroConteudo("A expiracao deve ser posterior ao inicio da exibicao.")


@dataclass(frozen=True, slots=True)
class NovaNotificacao:
    """Dados aceitos para criar uma notificacao no sistema atual."""

    titulo: str
    mensagem: str
    tipo: TipoNotificacao = TipoNotificacao.INFO
    categoria: CategoriaNotificacao = CategoriaNotificacao.GERAL
    id_usuario_destino: int | None = None
    id_grupo_destino: int | None = None
    icone: str | None = None
    criado_por: str = "SISTEMA"
    metadados: Mapping[str, object] | None = field(default=None, repr=False)
    expira_em: datetime | None = None
    exibir_a_partir_de: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "titulo", _texto_obrigatorio(self.titulo, "titulo", 200))
        object.__setattr__(self, "mensagem", _texto_obrigatorio(self.mensagem, "mensagem"))
        object.__setattr__(
            self,
            "criado_por",
            _texto_obrigatorio(self.criado_por, "criado_por", 150),
        )
        if self.icone is not None and len(self.icone.strip()) > 100:
            raise ErroConteudo("icone deve ter no maximo 100 caracteres.")
        if self.id_usuario_destino is not None and self.id_usuario_destino <= 0:
            raise ErroConteudo("id_usuario_destino deve ser positivo.")
        if self.id_grupo_destino is not None and self.id_grupo_destino <= 0:
            raise ErroConteudo("id_grupo_destino deve ser positivo.")
        if self.id_usuario_destino is not None and self.id_grupo_destino is not None:
            raise ErroConteudo("A notificacao deve escolher usuario ou grupo, nunca ambos.")
        _validar_vigencia(self.exibir_a_partir_de, self.expira_em)


@dataclass(frozen=True, slots=True)
class NotificacaoUsuario:
    """Notificacao visivel e destacada do ORM para um usuario."""

    id_notificacao: int
    id_sistema: int | None
    tipo: str
    categoria: str
    titulo: str
    mensagem: str
    icone: str | None
    lida: bool
    data_criacao: datetime
    data_leitura: datetime | None
    metadados: object | None
    expira_em: datetime | None
    exibir_a_partir_de: datetime | None

    def como_dict(self) -> dict[str, object]:
        """Serializa a notificacao sem expor uma entidade ORM."""

        return {
            "id_notificacao": self.id_notificacao,
            "id_sistema": self.id_sistema,
            "tipo": self.tipo,
            "categoria": self.categoria,
            "titulo": self.titulo,
            "mensagem": self.mensagem,
            "icone": self.icone,
            "lida": self.lida,
            "data_criacao": self.data_criacao.isoformat(),
            "data_leitura": self.data_leitura.isoformat() if self.data_leitura else None,
            "metadados": self.metadados,
            "expira_em": self.expira_em.isoformat() if self.expira_em else None,
            "exibir_a_partir_de": (
                self.exibir_a_partir_de.isoformat() if self.exibir_a_partir_de else None
            ),
        }


@dataclass(frozen=True, slots=True)
class PaginaNotificacoes:
    """Janela limitada de notificacoes e cursor para retomada."""

    itens: tuple[NotificacaoUsuario, ...]
    proximo_cursor: int
    tem_mais: bool

    def como_dict(self) -> dict[str, object]:
        """Serializa a pagina para HTTP."""

        return {
            "itens": [item.como_dict() for item in self.itens],
            "proximo_cursor": self.proximo_cursor,
            "tem_mais": self.tem_mais,
        }


@dataclass(frozen=True, slots=True)
class ItemNotaAtualizacao:
    """Item ordenado de uma nota de atualizacao."""

    titulo: str
    descricao: str | None = None
    tipo: TipoItemAtualizacao = TipoItemAtualizacao.MELHORIA
    ordem: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "titulo", _texto_obrigatorio(self.titulo, "titulo", 200))
        if self.ordem < 0:
            raise ErroConteudo("ordem nao pode ser negativa.")


@dataclass(frozen=True, slots=True)
class NovaPublicacao:
    """Dados de um rascunho de publicacao no sistema atual."""

    titulo: str
    conteudo: str
    criado_por: str
    tipo: TipoPublicacao = TipoPublicacao.COMUNICADO
    audiencia: TipoAudiencia = TipoAudiencia.GERAL
    ids_grupos: Sequence[int] = ()
    resumo: str | None = None
    prioridade: PrioridadePublicacao = PrioridadePublicacao.NORMAL
    versao: str | None = None
    notificar: bool = True
    fixado: bool = False
    exibir_a_partir_de: datetime | None = None
    expira_em: datetime | None = None
    criado_por_id: int | None = None
    fonte: str = "INTERNO"
    id_externo: str | None = None
    url_externa: str | None = None
    metadados: Mapping[str, object] | None = field(default=None, repr=False)
    itens_atualizacao: Sequence[ItemNotaAtualizacao] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "titulo", _texto_obrigatorio(self.titulo, "titulo", 200))
        object.__setattr__(self, "conteudo", _texto_obrigatorio(self.conteudo, "conteudo"))
        object.__setattr__(
            self,
            "criado_por",
            _texto_obrigatorio(self.criado_por, "criado_por", 150),
        )
        grupos = tuple(sorted(set(self.ids_grupos)))
        object.__setattr__(self, "ids_grupos", grupos)
        if any(id_grupo <= 0 for id_grupo in grupos):
            raise ErroConteudo("Todos os ids_grupos devem ser positivos.")
        if self.audiencia is TipoAudiencia.GRUPOS and not grupos:
            raise ErroConteudo("Publicacao para grupos exige ao menos um grupo.")
        if self.audiencia is TipoAudiencia.GERAL and grupos:
            raise ErroConteudo("Publicacao geral nao aceita grupos.")
        if self.tipo is TipoPublicacao.ATUALIZACAO and not (self.versao or "").strip():
            raise ErroConteudo("Nota de atualizacao exige versao.")
        if self.resumo is not None and len(self.resumo.strip()) > 500:
            raise ErroConteudo("resumo deve ter no maximo 500 caracteres.")
        if self.fonte not in {"INTERNO", "GMAIL", "API"}:
            raise ErroConteudo("fonte deve ser INTERNO, GMAIL ou API.")
        _validar_vigencia(self.exibir_a_partir_de, self.expira_em)


@dataclass(frozen=True, slots=True)
class PublicacaoUsuario:
    """Publicacao visivel e destacada do ORM para um usuario."""

    id_publicacao: int
    id_sistema: int
    tipo: str
    audiencia: str
    titulo: str
    resumo: str | None
    conteudo: str | None
    prioridade: str
    versao: str | None
    fixado: bool
    lida: bool
    exibir_a_partir_de: datetime | None
    expira_em: datetime | None
    data_publicacao: datetime | None

    def como_dict(self) -> dict[str, object]:
        """Serializa a publicacao sem expor uma entidade ORM."""

        return {
            "id_publicacao": self.id_publicacao,
            "id_sistema": self.id_sistema,
            "tipo": self.tipo,
            "audiencia": self.audiencia,
            "titulo": self.titulo,
            "resumo": self.resumo,
            "conteudo": self.conteudo,
            "prioridade": self.prioridade,
            "versao": self.versao,
            "fixado": self.fixado,
            "lida": self.lida,
            "exibir_a_partir_de": (
                self.exibir_a_partir_de.isoformat() if self.exibir_a_partir_de else None
            ),
            "expira_em": self.expira_em.isoformat() if self.expira_em else None,
            "data_publicacao": (self.data_publicacao.isoformat() if self.data_publicacao else None),
        }


@dataclass(frozen=True, slots=True)
class PaginaPublicacoes:
    """Janela limitada de publicacoes e cursor para retomada."""

    itens: tuple[PublicacaoUsuario, ...]
    proximo_cursor: int
    tem_mais: bool

    def como_dict(self) -> dict[str, object]:
        """Serializa a pagina para HTTP."""

        return {
            "itens": [item.como_dict() for item in self.itens],
            "proximo_cursor": self.proximo_cursor,
            "tem_mais": self.tem_mais,
        }


@dataclass(frozen=True, slots=True)
class ComunicadoExterno:
    """Modelo para comunicados importados de fontes externas (ex: GMAIL, API)."""

    id_externo: str
    fonte: str
    titulo: str
    conteudo: str
    criado_por: str = "EXTERNO"
    resumo: str | None = None
    url_externa: str | None = None
    data_publicacao: datetime | None = None
    expira_em: datetime | None = None
    prioridade: PrioridadePublicacao = PrioridadePublicacao.NORMAL
    versao: str | None = None
    metadados: Mapping[str, object] | None = None


class ProvedorComunicados:
    """Protocolo/interface para provedores externos de comunicados."""

    def obter_comunicados(self) -> Sequence[ComunicadoExterno]:
        """Obtem comunicados disponiveis no provedor externo."""
        raise NotImplementedError
