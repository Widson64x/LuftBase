"""Registro de temas e casos de uso de preferencia visual."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from luftbase.interface.modelos import ManifestoTema, PreferenciaTema, TemaResolvido
from luftbase.nucleo.excecoes import ErroConfiguracao
from luftbase.persistencia.core.preferencias import ModoTema


class PortaPreferenciasTema(Protocol):
    """Persistencia minima exigida pelo servico."""

    def obter(self, id_usuario: int) -> PreferenciaTema | None:
        """Busca uma preferencia."""

    def salvar(self, id_usuario: int, preferencia: PreferenciaTema) -> None:
        """Persiste uma preferencia."""


class RegistroTemas:
    """Registro explicito e isolado por aplicacao Flask."""

    def __init__(self, temas: Iterable[ManifestoTema] = ()) -> None:
        self._temas: dict[str, ManifestoTema] = {}
        for tema in temas:
            self.registrar(tema)

    def registrar(self, tema: ManifestoTema) -> None:
        """Registra uma familia e rejeita substituicao silenciosa."""

        if tema.identificador in self._temas:
            raise ErroConfiguracao(f"O tema {tema.identificador!r} ja foi registrado.")
        self._temas[tema.identificador] = tema

    def obter(self, identificador: str) -> ManifestoTema | None:
        """Busca um manifesto sem criar fallback implicitamente."""

        return self._temas.get(identificador)

    def listar(self) -> tuple[ManifestoTema, ...]:
        """Lista temas em ordem deterministica."""

        return tuple(self._temas[chave] for chave in sorted(self._temas))


class ServicoTemas:
    """Resolve e persiste preferencias com fallback corporativo controlado."""

    tema_padrao = "luft"

    def __init__(
        self,
        repositorio: PortaPreferenciasTema,
        registro: RegistroTemas,
    ) -> None:
        if registro.obter(self.tema_padrao) is None:
            raise ErroConfiguracao("O registro deve conter o tema corporativo 'luft'.")
        self._repositorio = repositorio
        self._registro = registro

    @property
    def registro(self) -> RegistroTemas:
        """Permite registrar extensoes antes de a aplicacao atender requisicoes."""

        return self._registro

    def obter_preferencia(self, id_usuario: int) -> PreferenciaTema:
        """Busca a preferencia e aplica fallback se a familia deixou de existir."""

        preferencia = self._repositorio.obter(id_usuario) or PreferenciaTema()
        if self._registro.obter(preferencia.tema) is None:
            return PreferenciaTema(modo=preferencia.modo)
        return preferencia

    def alterar_preferencia(
        self,
        id_usuario: int,
        tema: str,
        modo: str | ModoTema,
    ) -> PreferenciaTema:
        """Valida o tema e o modo e persiste a escolha corporativa.

        Tema e modo sao independentes: a luminosidade pedida e guardada mesmo que o tema
        escolhido nao a suporte. Assim, voltar a um tema completo restaura a preferencia
        do usuario; o que a tela exibe e resolvido por ``resolver``.
        """

        if self._registro.obter(tema) is None:
            raise ErroConfiguracao("Tema nao registrado.")
        try:
            modo_validado = modo if isinstance(modo, ModoTema) else ModoTema(modo.upper())
        except ValueError as erro:
            raise ErroConfiguracao("Modo deve ser CLARO, ESCURO ou SISTEMA.") from erro
        preferencia = PreferenciaTema(tema=tema, modo=modo_validado)
        self._repositorio.salvar(id_usuario, preferencia)
        return preferencia

    def resolver(self, preferencia: PreferenciaTema) -> TemaResolvido:
        """Combina a preferencia com o que o tema suporta (modo efetivo e bloqueio)."""

        manifesto = self.manifesto(preferencia)
        return TemaResolvido(
            manifesto=manifesto,
            modo_preferido=preferencia.modo,
            modo_efetivo=manifesto.resolver_modo(preferencia.modo),
        )

    def manifesto(self, preferencia: PreferenciaTema) -> ManifestoTema:
        """Resolve o manifesto efetivo com fallback sempre existente."""

        manifesto = self._registro.obter(preferencia.tema)
        if manifesto is not None:
            return manifesto
        padrao = self._registro.obter(self.tema_padrao)
        assert padrao is not None  # Garantido no construtor.
        return padrao


def criar_registro_padrao() -> RegistroTemas:
    """Cria o registro corporativo sem depender de estado global."""

    return RegistroTemas(
        (
            ManifestoTema(
                identificador="luft",
                nome="Luft Corporativo",
                versao="1.0.0",
                url_css="/_luftbase/static/css/temas/luft.css",
                descricao="Azul corporativo clássico",
                cores_previa=("#1d63d8", "#0f172a", "#e05a00"),
            ),
            ManifestoTema(
                identificador="luft-esg",
                nome="Luft ESG",
                versao="1.0.0",
                url_css="/_luftbase/static/css/temas/luft-esg.css",
                descricao="Verde sustentável para iniciativas ambientais, sociais e de governança",
                cores_previa=("#15803d", "#0f766e", "#a3e635"),
            ),
        )
    )
