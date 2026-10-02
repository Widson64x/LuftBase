"""Objetos imutaveis trocados entre a aplicacao e o servico de e-mail."""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage


@dataclass(frozen=True, slots=True)
class Anexo:
    """Arquivo anexado a mensagem; o conteudo nunca aparece em `repr` ou logs."""

    nome: str
    conteudo: bytes = field(repr=False)
    tipo_mime: str = "application/octet-stream"


@dataclass(frozen=True, slots=True)
class ImagemEmbutida:
    """Imagem referenciada no HTML por `src="cid:<cid>"`."""

    cid: str
    conteudo: bytes = field(repr=False)
    tipo_mime: str = "image/png"


@dataclass(frozen=True, slots=True)
class EnvioPreparado:
    """Mensagem montada e pronta para o transporte, com o destino ja resolvido."""

    assunto: str
    destinatarios: tuple[str, ...]
    destinatarios_originais: tuple[str, ...]
    redirecionado: bool
    anexos: tuple[str, ...]
    mensagem: EmailMessage = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class ResultadoEnvio:
    """Desfecho de uma mensagem; falhas de entrega nao geram excecao."""

    sucesso: bool
    assunto: str
    destinatarios: tuple[str, ...]
    destinatarios_originais: tuple[str, ...]
    redirecionado: bool
    erro: str | None = None
    recusados: tuple[str, ...] = ()

    def como_dict(self) -> dict[str, object]:
        """Representacao serializavel para respostas JSON e auditoria."""

        return {
            "sucesso": self.sucesso,
            "assunto": self.assunto,
            "destinatarios": list(self.destinatarios),
            "destinatarios_originais": list(self.destinatarios_originais),
            "redirecionado": self.redirecionado,
            "erro": self.erro,
            "recusados": list(self.recusados),
        }
