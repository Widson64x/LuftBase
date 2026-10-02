"""Testes dos contratos, casos de uso, filtros e sinais de conteudo."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from luftbase.conteudo.modelos import (
    CategoriaNotificacao,
    NovaNotificacao,
    NovaPublicacao,
    PaginaNotificacoes,
    PaginaPublicacoes,
    PublicacaoUsuario,
    TipoAudiencia,
    TipoPublicacao,
)
from luftbase.conteudo.repositorios import (
    ResultadoPublicacao,
    filtro_notificacao_visivel,
    filtro_publicacao_visivel,
)
from luftbase.conteudo.servicos import ServicoNotificacoes, ServicoPublicacoes
from luftbase.conteudo.sinalizacao import SinalizadorConteudoRedis
from luftbase.nucleo import ErroConteudo
from luftbase.persistencia.core.notificacoes import Notificacao
from luftbase.persistencia.core.publicacoes import Publicacao


class ArmazenamentoFalso:
    """Chave-valor em memoria com falha opcional."""

    def __init__(self, *, falhar: bool = False) -> None:
        self.dados: dict[str, bytes] = {}
        self.falhar = falhar

    def obter(self, chave: str) -> bytes | None:
        if self.falhar:
            raise RuntimeError("redis indisponivel")
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        del ttl_segundos
        if self.falhar:
            raise RuntimeError("redis indisponivel")
        self.dados[chave] = valor


class RepositorioNotificacoesFalso:
    """Repositorio observavel sem banco real."""

    def __init__(self) -> None:
        self.criadas: list[tuple[int, NovaNotificacao]] = []
        self.consulta: dict[str, object] = {}
        self.leituras = 0

    def criar(self, id_sistema: int, dados: NovaNotificacao) -> int:
        self.criadas.append((id_sistema, dados))
        return 41

    def listar(self, **opcoes: object) -> PaginaNotificacoes:
        self.consulta = opcoes
        return PaginaNotificacoes((), int(opcoes.get("depois_de") or 0), False)

    def marcar_lida(self, **opcoes: object) -> bool:
        self.consulta = opcoes
        self.leituras += 1
        return self.leituras == 1


class RepositorioPublicacoesFalso:
    """Repositorio observavel para publicacao atomica."""

    def __init__(self) -> None:
        self.consulta: dict[str, object] = {}
        self.resultado = ResultadoPublicacao(8, (31, 32))

    def criar_rascunho(self, id_sistema: int, dados: NovaPublicacao) -> ResultadoPublicacao:
        self.consulta = {"id_sistema": id_sistema, "dados": dados}
        return ResultadoPublicacao(8)

    def publicar(self, id_sistema: int, id_publicacao: int) -> ResultadoPublicacao:
        self.consulta = {"id_sistema": id_sistema, "id_publicacao": id_publicacao}
        return self.resultado

    def listar(self, **opcoes: object) -> PaginaPublicacoes:
        self.consulta = opcoes
        return PaginaPublicacoes((), int(opcoes.get("depois_de") or 0), False)

    def obter(self, **opcoes: object) -> PublicacaoUsuario:
        self.consulta = opcoes
        return _publicacao()

    def marcar_lida(self, **opcoes: object) -> bool:
        self.consulta = opcoes
        return True


def _publicacao() -> PublicacaoUsuario:
    return PublicacaoUsuario(
        id_publicacao=8,
        id_sistema=2,
        tipo="COMUNICADO",
        audiencia="GERAL",
        titulo="Aviso",
        resumo="Resumo",
        conteudo=None,
        prioridade="NORMAL",
        versao=None,
        fixado=False,
        lida=False,
        exibir_a_partir_de=None,
        expira_em=None,
        data_publicacao=datetime(2026, 9, 16, 10, 0),
    )


def test_valida_audiencia_vigencia_e_nota_de_atualizacao() -> None:
    with pytest.raises(ErroConteudo, match="usuario ou grupo"):
        NovaNotificacao("Titulo", "Mensagem", id_usuario_destino=1, id_grupo_destino=2)
    with pytest.raises(ErroConteudo, match="ao menos um grupo"):
        NovaPublicacao(
            "Titulo",
            "Conteudo",
            "autor",
            audiencia=TipoAudiencia.GRUPOS,
        )
    with pytest.raises(ErroConteudo, match="exige versao"):
        NovaPublicacao(
            "Titulo",
            "Conteudo",
            "autor",
            tipo=TipoPublicacao.ATUALIZACAO,
        )


def test_filtro_notificacao_contem_usuario_grupo_sistema_e_vigencia() -> None:
    consulta = select(Notificacao.id_notificacao).where(filtro_notificacao_visivel(9, 27, 4))
    sql = str(
        consulta.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "id_usuario_destino = 27" in sql
    assert "id_grupo_destino = 4" in sql
    assert "id_sistema = 9" in sql
    assert "id_sistema = 0" in sql
    assert "expira_em" in sql
    assert "exibir_a_partir_de" in sql


def test_filtro_publicacao_isola_sistema_grupo_status_e_vigencia() -> None:
    consulta = select(Publicacao.id_publicacao).where(filtro_publicacao_visivel(9, 4))
    sql = str(
        consulta.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()

    assert "id_sistema in (0, 9)" in sql
    assert "id_grupo = 4" in sql
    assert "status_publicacao" in sql
    assert "expira_em" in sql


def test_notificacao_confirma_postgresql_antes_de_sinalizar() -> None:
    repositorio = RepositorioNotificacoesFalso()
    armazenamento = ArmazenamentoFalso()
    servico = ServicoNotificacoes(
        2,
        repositorio,  # type: ignore[arg-type]
        SinalizadorConteudoRedis(armazenamento),
    )

    identificador = servico.criar(
        NovaNotificacao(
            "Processo concluido",
            "A importacao terminou.",
            categoria=CategoriaNotificacao.INTEGRACAO,
        )
    )

    assert identificador == 41
    assert repositorio.criadas[0][0] == 2
    assert servico.ultimo_cursor_sinalizado() == 41


def test_falha_do_redis_nao_reverte_conteudo_persistido() -> None:
    repositorio = RepositorioNotificacoesFalso()
    servico = ServicoNotificacoes(
        2,
        repositorio,  # type: ignore[arg-type]
        SinalizadorConteudoRedis(ArmazenamentoFalso(falhar=True)),
    )

    assert servico.criar(NovaNotificacao("Titulo", "Mensagem")) == 41
    assert len(repositorio.criadas) == 1
    assert servico.ultimo_cursor_sinalizado() is None


def test_consulta_incremental_tem_limite_e_cursor_explicitos() -> None:
    repositorio = RepositorioNotificacoesFalso()
    servico = ServicoNotificacoes(
        7,
        repositorio,  # type: ignore[arg-type]
        SinalizadorConteudoRedis(ArmazenamentoFalso()),
    )

    servico.listar_para_usuario(12, 5, cursor=100, limite=25)

    assert repositorio.consulta == {
        "id_sistema": 7,
        "id_usuario": 12,
        "id_grupo": 5,
        "depois_de": 100,
        "limite": 25,
        "apenas_nao_lidas": False,
    }
    with pytest.raises(ErroConteudo, match="entre 1 e 100"):
        servico.listar_para_usuario(12, 5, limite=101)


def test_publicacao_sinaliza_feed_e_notificacoes_apos_transacao() -> None:
    repositorio = RepositorioPublicacoesFalso()
    armazenamento = ArmazenamentoFalso()
    sinalizador = SinalizadorConteudoRedis(armazenamento)
    servico = ServicoPublicacoes(2, repositorio, sinalizador)  # type: ignore[arg-type]

    alterada = servico.publicar(8)

    assert alterada is True
    assert sinalizador.obter_cursor("publicacoes", 2) == 8
    assert sinalizador.obter_cursor("notificacoes", 2) == 32


def test_publicacao_idempotente_nao_gera_novo_sinal() -> None:
    repositorio = RepositorioPublicacoesFalso()
    repositorio.resultado = ResultadoPublicacao(8, alterada=False)
    armazenamento = ArmazenamentoFalso()
    sinalizador = SinalizadorConteudoRedis(armazenamento)
    servico = ServicoPublicacoes(2, repositorio, sinalizador)  # type: ignore[arg-type]

    assert servico.publicar(8) is False
    assert sinalizador.obter_cursor("publicacoes", 2) is None


def test_serializacao_do_feed_nao_inclui_conteudo_completo() -> None:
    dados = _publicacao().como_dict()

    assert dados["conteudo"] is None
    assert dados["data_publicacao"] == "2026-09-16T10:00:00"
