"""Contratos imutaveis do design system."""

from __future__ import annotations

import re
from dataclasses import dataclass

from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema

_SLUG_TEMA = re.compile(r"^[a-z][a-z0-9-]{0,48}[a-z0-9]$")
_COR_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_MODOS_DE_TEMA = frozenset({ModoTema.CLARO, ModoTema.ESCURO})


@dataclass(frozen=True, slots=True)
class ManifestoTema:
    """Descreve uma familia visual e seu unico arquivo de tokens.

    O tema (familia de cores) e o modo (claro/escuro) sao eixos independentes: um tema
    declara em ``modos`` quais luminosidades suporta. Um tema com um unico modo e valido;
    nele o modo e fixo e a interface bloqueia a alternancia.
    """

    identificador: str
    nome: str
    versao: str
    url_css: str
    modos: frozenset[ModoTema] = frozenset({ModoTema.CLARO, ModoTema.ESCURO})
    descricao: str = ""
    cores_previa: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _SLUG_TEMA.fullmatch(self.identificador):
            raise ErroConfiguracao("O identificador do tema deve ser um slug minusculo.")
        if not self.nome.strip() or not self.versao.strip():
            raise ErroConfiguracao("Nome e versao do tema sao obrigatorios.")
        if not self.url_css.startswith("/") or self.url_css.startswith("//"):
            raise ErroConfiguracao("A URL do tema deve ser local e iniciar com '/'.")
        if not self.modos:
            raise ErroConfiguracao("Todo tema deve oferecer ao menos um modo (CLARO ou ESCURO).")
        if not self.modos <= _MODOS_DE_TEMA:
            raise ErroConfiguracao(
                "Os modos de um tema devem ser CLARO e/ou ESCURO; "
                "SISTEMA e uma preferencia do usuario, nao um modo do tema."
            )
        if len(self.cores_previa) > 4 or not all(_COR_HEX.fullmatch(c) for c in self.cores_previa):
            raise ErroConfiguracao("cores_previa aceita ate 4 cores no formato #RRGGBB.")

    @property
    def modo_unico(self) -> ModoTema | None:
        """Retorna o modo fixo do tema, ou ``None`` quando oferece claro e escuro."""

        if len(self.modos) == 1:
            return next(iter(self.modos))
        return None

    @property
    def oferece_alternancia(self) -> bool:
        """Indica se o usuario pode escolher entre claro, escuro e automatico."""

        return self.modo_unico is None

    def resolver_modo(self, preferido: ModoTema) -> ModoTema:
        """Aplica a preferencia de luminosidade ao que o tema suporta.

        Em temas de modo unico o modo e imposto. Em temas completos a preferencia e
        mantida, inclusive ``SISTEMA``, que o navegador resolve com ``prefers-color-scheme``.
        """

        unico = self.modo_unico
        return unico if unico is not None else preferido


@dataclass(frozen=True, slots=True)
class PreferenciaTema:
    """Preferencia visual compartilhada de um usuario."""

    tema: str = "luft"
    modo: ModoTema = ModoTema.SISTEMA

    def como_dict(self) -> dict[str, str]:
        """Serializa a preferencia para sessao e HTTP."""

        return {"tema": self.tema, "modo": self.modo.value}


@dataclass(frozen=True, slots=True)
class TemaResolvido:
    """Resultado de combinar a preferencia do usuario com as capacidades do tema."""

    manifesto: ManifestoTema
    modo_preferido: ModoTema
    modo_efetivo: ModoTema

    @property
    def modo_bloqueado(self) -> bool:
        """Verdadeiro quando o tema impede o usuario de alternar o modo."""

        return not self.manifesto.oferece_alternancia

    def como_dict(self) -> dict[str, object]:
        """Serializa o estado efetivo para a resposta HTTP."""

        return {
            "tema": self.manifesto.identificador,
            "modo": self.modo_preferido.value,
            "modo_efetivo": self.modo_efetivo.value,
            "modo_bloqueado": self.modo_bloqueado,
            "modos_suportados": sorted(m.value for m in self.manifesto.modos),
        }
