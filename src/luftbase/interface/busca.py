"""Busca global da barra superior: contrato dos provedores que cada aplicacao registra.

A barra pesquisa, no navegador, os itens do menu lateral que o usuario ja pode ver. Para ir alem
(CTCs, aeroportos, clientes...), a aplicacao registra provedores de busca::

    PlataformaLuft(fabrica, buscas=[
        ProvedorBusca(
            id="aeroportos",
            titulo="Aeroportos",
            icone="ph-bold ph-airplane",
            permissao="CADASTROS.AEROPORTOS.VISUALIZAR",
            buscar=lambda termo, limite: [
                ResultadoBusca("GRU", url_for("Aeroporto.gerenciar"), "Guarulhos")
            ],
        ),
    ])

O LuftBase chama `buscar(termo, limite)` dentro da requisicao (entao `url_for` e a sessao
funcionam), so para quem tem a `permissao`, com limite de tempo, e descarta URLs que nao sejam
do proprio sistema.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from luftbase.nucleo.excecoes import ErroConfiguracao

_PADRAO_ICONE = re.compile(r"^ph-(?:bold|fill|thin|light|regular|duotone) ph-[a-z0-9-]+$")
_PADRAO_ID = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")


@dataclass(frozen=True, slots=True)
class ResultadoBusca:
    """Um item da lista de resultados. `url` deve ser um caminho do proprio sistema."""

    titulo: str
    url: str
    subtitulo: str | None = None
    icone: str | None = None


@dataclass(frozen=True, slots=True)
class ProvedorBusca:
    """Uma fonte de resultados (um grupo na lista da barra de busca)."""

    id: str
    titulo: str
    buscar: Callable[[str, int], Iterable[ResultadoBusca]]
    permissao: str | None = None
    icone: str = "ph-bold ph-magnifying-glass"
    minimo_caracteres: int = 2
    limite: int = 5
    # So para fontes cujos links apontam para outros enderecos (ex.: o catalogo de sistemas do Hub).
    urls_externas: bool = False

    def __post_init__(self) -> None:
        if not _PADRAO_ID.fullmatch(self.id):
            raise ErroConfiguracao(
                f"Id de busca invalido {self.id!r}: use minusculas, numeros, '-' ou '_'."
            )
        if not self.titulo.strip():
            raise ErroConfiguracao("Todo provedor de busca precisa de titulo.")
        if not _PADRAO_ICONE.fullmatch(self.icone):
            raise ErroConfiguracao(
                f"Icone invalido {self.icone!r}: use o formato Phosphor 'ph-bold ph-nome'."
            )
        if not 1 <= self.minimo_caracteres <= 10 or not 1 <= self.limite <= 20:
            raise ErroConfiguracao("minimo_caracteres deve ir de 1 a 10 e limite de 1 a 20.")


def url_do_proprio_sistema(url: str) -> bool:
    """Aceita so caminhos relativos ('/x'); recusa '//host', 'http://...' e esquemas."""

    return url.startswith("/") and not url.startswith("//") and "\\" not in url


def url_aceita(url: str, *, permitir_externas: bool = False) -> bool:
    """Caminho do proprio sistema ou, se o provedor declarou, um endereco http(s) completo."""

    if url_do_proprio_sistema(url):
        return True
    return permitir_externas and re.fullmatch(r"https?://[^\s\\]+", url) is not None


__all__ = ["ProvedorBusca", "ResultadoBusca", "url_aceita", "url_do_proprio_sistema"]
