"""Limpar notificacao: some so para quem limpou; a notificacao continua no banco e para as demais pessoas."""

from __future__ import annotations

import pytest
from core_sqlite import motor_sqlite
from sqlalchemy import func, select

from luftbase.conteudo import repositorios
from luftbase.conteudo.modelos import NovaNotificacao
from luftbase.conteudo.repositorios import RepositorioNotificacoes
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.notificacoes import Notificacao, NotificacaoOculta
from luftbase.persistencia.core.seguranca import Sistema
from luftbase.persistencia.core.usuario import Usuario


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> tuple[RepositorioNotificacoes, BancoSQLAlchemy]:
    # O SQLite nao tem `AT TIME ZONE`; o resto da logica do repositorio roda de verdade.
    from sqlalchemy import literal_column

    monkeypatch.setattr(repositorios, "_AGORA_BANCO", literal_column("CURRENT_TIMESTAMP"))
    banco = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))
    with banco.unidade_trabalho() as s:
        s.add(Sistema(id_sistema=0, nome_sistema="Workspace", ativo=True))
        for codigo in (1, 2):
            s.add(Usuario(codigo_usuario=codigo, login_usuario=f"u{codigo}", nome_usuario=f"U{codigo}"))
    return RepositorioNotificacoes(banco), banco


def _titulos(repo: RepositorioNotificacoes, usuario: int) -> list[str]:
    pagina = repo.listar(id_sistema=0, id_usuario=usuario, id_grupo=None, depois_de=None, limite=50)
    return [item.titulo for item in pagina.itens]


def _criar(repo: RepositorioNotificacoes, titulo: str, **destino: int) -> int:
    return repo.criar(0, NovaNotificacao(titulo=titulo, mensagem="m", **destino))


def _ocultar(repo: RepositorioNotificacoes, usuario: int, id_notificacao: int) -> bool:
    return repo.ocultar(
        id_sistema=0, id_usuario=usuario, id_grupo=None, id_notificacao=id_notificacao
    )


def test_global_some_so_para_quem_limpou(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    n = _criar(r, "Aviso para todos")

    assert _ocultar(r, 1, n) is True

    assert _titulos(r, 1) == []
    assert _titulos(r, 2) == ["Aviso para todos"]  # a outra pessoa continua vendo


def test_notificacao_continua_no_banco(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    n = _criar(r, "Aviso", id_usuario_destino=1)

    _ocultar(r, 1, n)

    with banco.leitura() as s:
        assert s.execute(select(func.count()).select_from(Notificacao)).scalar_one() == 1
        assert s.execute(select(func.count()).select_from(NotificacaoOculta)).scalar_one() == 1
    assert _titulos(r, 1) == []


def test_pessoal_acesso_liberado_some_para_o_dono(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    n = _criar(r, "Acesso liberado: X", id_usuario_destino=1)
    _criar(r, "Outro", id_usuario_destino=1)

    _ocultar(r, 1, n)

    assert _titulos(r, 1) == ["Outro"]


def test_ocultar_e_idempotente(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    n = _criar(r, "A")

    assert _ocultar(r, 1, n) is True
    with pytest.raises(ConteudoNaoEncontrado):
        _ocultar(r, 1, n)  # ja nao e visivel para a pessoa: some de vez


def test_nao_oculta_notificacao_de_outra_pessoa(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    n = _criar(r, "So do usuario 2", id_usuario_destino=2)

    with pytest.raises(ConteudoNaoEncontrado):
        _ocultar(r, 1, n)
    assert _titulos(r, 2) == ["So do usuario 2"]


def test_contagem_de_nao_lidas_ignora_as_ocultas(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    a = _criar(r, "A")
    _criar(r, "B")
    assert r.contar_nao_lidas(id_sistema=0, id_usuario=1, id_grupo=None) == 2

    _ocultar(r, 1, a)

    assert r.contar_nao_lidas(id_sistema=0, id_usuario=1, id_grupo=None) == 1
    assert r.contar_nao_lidas(id_sistema=0, id_usuario=2, id_grupo=None) == 2


def test_ocultar_todas_e_so_as_lidas(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    lida = _criar(r, "Lida")
    _criar(r, "Nao lida")
    r.marcar_lida(id_sistema=0, id_usuario=1, id_grupo=None, id_notificacao=lida)

    so_lidas = r.ocultar_todas(id_sistema=0, id_usuario=1, id_grupo=None, apenas_lidas=True)
    assert so_lidas == 1 and _titulos(r, 1) == ["Nao lida"]

    todas = r.ocultar_todas(id_sistema=0, id_usuario=1, id_grupo=None)
    assert todas == 1 and _titulos(r, 1) == []
    assert _titulos(r, 2) == ["Lida", "Nao lida"]  # a outra pessoa nao foi afetada
    assert r.ocultar_todas(id_sistema=0, id_usuario=1, id_grupo=None) == 0


def test_filtro_de_visibilidade_consulta_a_tabela_de_ocultas() -> None:
    from sqlalchemy.dialects import postgresql

    sql = str(
        repositorios.filtro_notificacao_visivel(0, 1, None).compile(dialect=postgresql.dialect())
    )

    assert "tb_notificacao_oculta" in sql
