"""Fronteiras transacionais e ciclo de vida das sessoes SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from time import perf_counter

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, scoped_session, sessionmaker

from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.nucleo.excecoes import ErroConexaoBanco


class BancoSQLAlchemy:
    """Banco nomeado com unidade de trabalho e limpeza contextual centralizadas."""

    def __init__(self, nome: str, engine: Engine, *, somente_leitura: bool = False) -> None:
        self.nome = nome
        self.engine = engine
        self.somente_leitura = somente_leitura
        self._sessoes = scoped_session(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        )

    @contextmanager
    def unidade_trabalho(self) -> Iterator[Session]:
        """Confirma a transacao no sucesso e executa rollback em qualquer erro."""

        if self.somente_leitura:
            raise ErroConexaoBanco(f"O banco {self.nome!r} foi registrado apenas para leitura.")
        sessao = self._sessoes()
        try:
            with sessao.begin():
                yield sessao
        finally:
            self._sessoes.remove()

    @contextmanager
    def escrita(self) -> Iterator[Session]:
        """Alias para unidade_trabalho que confirma no sucesso e executa rollback no erro."""

        with self.unidade_trabalho() as sessao:
            yield sessao

    @contextmanager
    def leitura(self) -> Iterator[Session]:
        """Abre uma sessao que nunca confirma alteracoes acidentalmente."""

        sessao = self._sessoes()
        try:
            yield sessao
        finally:
            # O rollback expira todo objeto ainda ligado à sessão; quem devolve entidades
            # lidas aqui as receberia vazias e sem sessão (DetachedInstanceError). Soltá-las
            # antes preserva os atributos já carregados para uso fora do bloco.
            sessao.expunge_all()
            sessao.rollback()
            self._sessoes.remove()

    def remover_sessao_contextual(self) -> None:
        """Remove uma sessao residual no encerramento do contexto Flask."""

        self._sessoes.remove()

    def verificar_saude(self) -> ResultadoSaude:
        """Executa uma consulta minima sem expor detalhes da conexao."""

        inicio = perf_counter()
        try:
            with self.engine.connect() as conexao:
                conexao.execute(text("SELECT 1"))
        except Exception:
            return ResultadoSaude(
                dependencia=self.nome,
                disponivel=False,
                latencia_ms=round((perf_counter() - inicio) * 1_000, 2),
                codigo="indisponivel",
            )
        return ResultadoSaude(
            dependencia=self.nome,
            disponivel=True,
            latencia_ms=round((perf_counter() - inicio) * 1_000, 2),
            codigo="ok",
        )
