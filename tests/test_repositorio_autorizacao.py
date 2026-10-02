"""Testes da consulta seletiva de permissoes sem PostgreSQL real."""

from contextlib import contextmanager

from luftbase.autorizacao.repositorio import RepositorioAutorizacao


class ResultadoLinhas:
    def __init__(self, linhas: list[tuple[object, ...]], escalar: int = 0) -> None:
        self._linhas = linhas
        self._escalar = escalar

    def all(self) -> list[tuple[object, ...]]:
        return self._linhas

    def scalar_one(self) -> int:
        return self._escalar


class SessaoFalsa:
    def __init__(self, linhas: list[tuple[object, ...]], revisao: int = 0) -> None:
        self.linhas = linhas
        self.revisao = revisao
        self.declaracoes: list[object] = []

    def execute(self, declaracao: object) -> ResultadoLinhas:
        self.declaracoes.append(declaracao)
        return ResultadoLinhas(self.linhas, self.revisao)

    def scalar(self, declaracao: object) -> int:
        self.declaracoes.append(declaracao)
        return self.revisao


class BancoFalso:
    def __init__(self, sessao: SessaoFalsa) -> None:
        self.sessao = sessao

    @contextmanager
    def leitura(self):  # type: ignore[no-untyped-def]
        yield self.sessao

    @contextmanager
    def unidade_trabalho(self):  # type: ignore[no-untyped-def]
        yield self.sessao


def test_consulta_aplica_precedencia_e_nega_chave_desconhecida() -> None:
    sessao = SessaoFalsa(
        [
            ("RELATORIOS.VER", 2, 0, True, False, 10, False, 20, True),
            ("RELATORIOS.EDITAR", 2, 0, True, False, 11, True, None, None),
            ("RELATORIOS.EXPORTAR", 2, 0, True, False, None, None, 21, True),
        ]
    )
    repositorio = RepositorioAutorizacao(BancoFalso(sessao))  # type: ignore[arg-type]

    resultado = repositorio.consultar(
        id_sistema=2,
        id_usuario=2759,
        id_grupo=7,
        chaves=(
            "RELATORIOS.VER",
            "RELATORIOS.EDITAR",
            "RELATORIOS.EXPORTAR",
            "RELATORIOS.DESCONHECIDA",
        ),
    )

    assert resultado == {
        "RELATORIOS.VER": False,
        "RELATORIOS.EDITAR": True,
        "RELATORIOS.EXPORTAR": True,
        "RELATORIOS.DESCONHECIDA": False,
    }
    declaracao = sessao.declaracoes[0]
    parametros = declaracao.compile().params  # type: ignore[attr-defined]
    assert any(valor == [0, 2] for valor in parametros.values())
    assert any(
        isinstance(valor, (list, tuple, set)) and "RELATORIOS.DESCONHECIDA" in valor
        for valor in parametros.values()
    )
    assert "tb_sistema.ativo IS true" in str(declaracao)


def test_consulta_herda_escopo_global_e_prioriza_decisao_da_aplicacao() -> None:
    sessao = SessaoFalsa(
        [
            ("PORTAL.VER", 0, 0, True, False, None, None, 20, True),
            ("PORTAL.EDITAR", 0, 0, True, False, 10, True, None, None),
            ("PORTAL.EDITAR", 2, 0, True, False, 11, False, 20, True),
        ]
    )
    repositorio = RepositorioAutorizacao(BancoFalso(sessao))  # type: ignore[arg-type]

    resultado = repositorio.consultar(
        id_sistema=2,
        id_usuario=2759,
        id_grupo=7,
        chaves=("PORTAL.VER", "PORTAL.EDITAR", "PORTAL.DESCONHECIDO"),
    )

    assert resultado == {
        "PORTAL.VER": True,
        "PORTAL.EDITAR": False,
        "PORTAL.DESCONHECIDO": False,
    }
    parametros = sessao.declaracoes[0].compile().params  # type: ignore[attr-defined]
    assert any(valor == [0, 2] for valor in parametros.values())


def test_regra_filha_bloqueia_concessao_mestre_e_pode_ser_reativada() -> None:
    sessao = SessaoFalsa(
        [
            ("SEGURANCA.PERMISSOES.EDITAR", 0, 0, True, True, 11, False, None, None),
            ("SEGURANCA.PERMISSOES.EDITAR", 0, 1, True, True, None, None, None, None),
            ("SEGURANCA.PERMISSOES.EDITAR", 0, 2, True, False, None, None, 20, True),
        ]
    )
    repositorio = RepositorioAutorizacao(BancoFalso(sessao))  # type: ignore[arg-type]

    negado = repositorio.consultar(
        id_sistema=0,
        id_usuario=2759,
        id_grupo=6,
        chaves=("SEGURANCA.PERMISSOES.EDITAR",),
    )

    assert negado == {"SEGURANCA.PERMISSOES.EDITAR": False}

    sessao.linhas[0] = (
        "SEGURANCA.PERMISSOES.EDITAR",
        0,
        0,
        True,
        True,
        11,
        True,
        None,
        None,
    )
    permitido = repositorio.consultar(
        id_sistema=0,
        id_usuario=2759,
        id_grupo=6,
        chaves=("SEGURANCA.PERMISSOES.EDITAR",),
    )

    assert permitido == {"SEGURANCA.PERMISSOES.EDITAR": True}


def test_permissao_inativa_em_qualquer_ancestral_nega_acesso() -> None:
    sessao = SessaoFalsa(
        [
            ("CONTEUDO.COMUNICADOS.PUBLICAR", 0, 0, True, True, None, None, None, None),
            ("CONTEUDO.COMUNICADOS.PUBLICAR", 0, 1, False, False, None, None, 20, True),
        ]
    )
    repositorio = RepositorioAutorizacao(BancoFalso(sessao))  # type: ignore[arg-type]

    resultado = repositorio.consultar(
        id_sistema=0,
        id_usuario=2759,
        id_grupo=6,
        chaves=("CONTEUDO.COMUNICADOS.PUBLICAR",),
    )

    assert resultado == {"CONTEUDO.COMUNICADOS.PUBLICAR": False}


def test_le_e_incrementa_revisao_global() -> None:
    sessao = SessaoFalsa([], revisao=9)
    repositorio = RepositorioAutorizacao(BancoFalso(sessao))  # type: ignore[arg-type]

    assert repositorio.obter_revisao() == 9
    assert repositorio.incrementar_revisao() == 9
