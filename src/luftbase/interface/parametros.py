"""Parametros internos de uma aplicacao, exibidos em Painel de Controle > Configuracoes Gerais."""

from __future__ import annotations

import re
from dataclasses import dataclass

from luftbase.nucleo.excecoes import ErroConfiguracao

_PADRAO_ICONE = re.compile(r"^ph-(?:bold|fill|thin|light|regular|duotone) ph-[a-z0-9-]+$")


@dataclass(frozen=True, slots=True)
class ParametroAplicacao:
    """Um cartao da aba Configuracoes Gerais que leva a uma tela da propria aplicacao.

    `endpoint` e o nome da rota Flask (ex.: `Parametros.gerenciarCias`). `permissao` e opcional:
    quando informada, o cartao so aparece para quem a possui.
    """

    titulo: str
    descricao: str
    endpoint: str
    icone: str = "ph-bold ph-sliders"
    permissao: str | None = None
    acao: str = "Abrir"

    def __post_init__(self) -> None:
        if not self.titulo.strip() or not self.endpoint.strip():
            raise ErroConfiguracao("Todo parametro da aplicacao precisa de titulo e endpoint.")
        if not _PADRAO_ICONE.fullmatch(self.icone):
            raise ErroConfiguracao(
                f"Icone invalido {self.icone!r}: use o formato Phosphor 'ph-bold ph-nome'."
            )


__all__ = ["ParametroAplicacao"]
