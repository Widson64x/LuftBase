"""Catalogo das fronteiras de dados disponibilizadas para uma aplicacao."""

from __future__ import annotations

from dataclasses import dataclass

from luftbase.infraestrutura.banco.conexoes import ConstrutorEngines
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, TipoBanco
from luftbase.nucleo.excecoes import ErroCredencial


@dataclass(frozen=True, slots=True)
class CatalogoBancos:
    """Acessos separados por responsabilidade, ainda que compartilhem um pool."""

    diretorio: BancoSQLAlchemy
    core: BancoSQLAlchemy
    aplicacao: BancoSQLAlchemy

    def remover_sessoes_contextuais(self) -> None:
        """Limpa sessoes residuais ao final de cada contexto da aplicacao."""

        self.diretorio.remover_sessao_contextual()
        self.core.remover_sessao_contextual()
        self.aplicacao.remover_sessao_contextual()

    def verificar_saude(self) -> tuple[ResultadoSaude, ...]:
        """Verifica cada fronteira com nomes publicos e resultados sanitizados."""

        return (
            self.diretorio.verificar_saude(),
            self.core.verificar_saude(),
            self.aplicacao.verificar_saude(),
        )

    def descartar(self) -> None:
        """Descarta os pools proprietarios durante encerramento ou testes."""

        self.remover_sessoes_contextuais()
        self.diretorio.engine.dispose()
        # Core e aplicacao sao visoes do mesmo pool PostgreSQL.
        self.core.engine.dispose()


class FabricaCatalogoBancos:
    """Monta o catalogo sem duplicar o pool PostgreSQL da aplicacao."""

    def __init__(self, construtor: ConstrutorEngines | None = None) -> None:
        self._construtor = construtor or ConstrutorEngines()

    def criar(
        self,
        credencial_diretorio: CredencialBanco,
        credencial_postgresql: CredencialBanco,
    ) -> CatalogoBancos:
        """Cria diretorio somente leitura e fronteiras core/aplicacao separadas."""

        if credencial_diretorio.tipo is not TipoBanco.SQLSERVER:
            raise ErroCredencial("A credencial do diretorio deve ser SQL Server.")
        if credencial_postgresql.tipo is not TipoBanco.POSTGRESQL:
            raise ErroCredencial("A credencial sistemica deve ser PostgreSQL.")
        if credencial_postgresql.esquema is None:
            raise ErroCredencial("A credencial PostgreSQL deve informar o schema da aplicacao.")

        engine_diretorio = self._construtor.criar(credencial_diretorio)
        engine_postgresql = self._construtor.criar(credencial_postgresql)
        engine_aplicacao = self._construtor.para_aplicacao(
            engine_postgresql,
            credencial_postgresql.esquema,
        )
        return CatalogoBancos(
            diretorio=BancoSQLAlchemy(
                "diretorio_sqlserver", engine_diretorio, somente_leitura=True
            ),
            core=BancoSQLAlchemy("core_postgresql", engine_postgresql),
            aplicacao=BancoSQLAlchemy("aplicacao_postgresql", engine_aplicacao),
        )
