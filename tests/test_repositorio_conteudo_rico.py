"""Repositorio de publicacoes com conteudo rico: formato, imagens, itens do changelog e notificacao."""

from __future__ import annotations

import pytest
from core_sqlite import motor_sqlite
from sqlalchemy import literal_column, select

from luftbase.conteudo import repositorios
from luftbase.conteudo.modelos import (
    ItemNotaAtualizacao,
    NovaPublicacao,
    TipoItemAtualizacao,
    TipoPublicacao,
)
from luftbase.conteudo.repositorios import RepositorioPublicacoes
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.notificacoes import Notificacao
from luftbase.persistencia.core.publicacoes import Publicacao, PublicacaoImagem
from luftbase.persistencia.core.seguranca import Sistema
from luftbase.persistencia.core.usuario import Usuario

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> tuple[RepositorioPublicacoes, BancoSQLAlchemy]:
    monkeypatch.setattr(repositorios, "_AGORA_BANCO", literal_column("CURRENT_TIMESTAMP"))
    banco = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))
    with banco.unidade_trabalho() as s:
        s.add(Sistema(id_sistema=0, nome_sistema="Workspace", ativo=True))
        s.add(Usuario(codigo_usuario=1, login_usuario="u1", nome_usuario="U1"))
    return RepositorioPublicacoes(banco), banco


def _html(**extra):  # type: ignore[no-untyped-def]
    base = {
        "titulo": "Aviso",
        "conteudo": "<h2>Ola</h2><p>Corpo <strong>rico</strong></p>",
        "criado_por": "Widson",
        "formato": "HTML",
    }
    base.update(extra)
    return NovaPublicacao(**base)


def test_grava_formato_e_resumo_automatico(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo

    id_publicacao = r.criar_rascunho(0, _html()).id_publicacao

    with banco.leitura() as s:
        linha = s.get(Publicacao, id_publicacao)
        assert linha.formato_conteudo == "HTML"
        assert linha.resumo == "Ola Corpo rico"


def test_conteudo_antigo_continua_markdown(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo

    id_publicacao = r.criar_rascunho(0, NovaPublicacao(titulo="A", conteudo="**x**", criado_por="u")).id_publicacao

    with banco.leitura() as s:
        assert s.get(Publicacao, id_publicacao).formato_conteudo == "MARKDOWN"


def test_imagens_soltas_sao_vinculadas_ao_salvar(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    id_imagem = r.salvar_imagem(dados=PNG, mime="image/png", nome="a.png", criado_por="Widson")
    outra = r.salvar_imagem(dados=PNG, mime="image/png", nome="b.png", criado_por="Widson")

    id_publicacao = r.criar_rascunho(0, _html(conteudo=f'<p>x</p><img src="luftimg:{id_imagem}">')).id_publicacao

    with banco.leitura() as s:
        assert s.get(PublicacaoImagem, id_imagem).id_publicacao == id_publicacao
        assert s.get(PublicacaoImagem, outra).id_publicacao is None  # nao citada: continua solta


def test_imagem_de_outra_publicacao_nao_e_roubada(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    id_imagem = r.salvar_imagem(dados=PNG, mime="image/png", nome=None, criado_por="Widson")
    dona = r.criar_rascunho(0, _html(conteudo=f'<img src="luftimg:{id_imagem}">')).id_publicacao

    r.criar_rascunho(0, _html(titulo="Outra", conteudo=f'<p>copia</p><img src="luftimg:{id_imagem}">'))

    with banco.leitura() as s:
        assert s.get(PublicacaoImagem, id_imagem).id_publicacao == dona


def test_obter_imagem_devolve_bytes_e_hash(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    id_imagem = r.salvar_imagem(dados=PNG, mime="image/png", nome="a.png", criado_por="Widson")

    mime, dados, hash_sha256, id_publicacao = r.obter_imagem(id_imagem)

    assert (mime, dados, id_publicacao) == ("image/png", PNG, None)
    assert len(hash_sha256) == 64
    with pytest.raises(ConteudoNaoEncontrado):
        r.obter_imagem(9999)


def test_edicao_troca_formato_e_conteudo(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    id_publicacao = r.criar_rascunho(
        0, NovaPublicacao(titulo="A", conteudo="## Antigo", criado_por="u")
    ).id_publicacao

    r.atualizar_rascunho(0, id_publicacao, _html(titulo="A", conteudo="<p>novo</p>"))

    with banco.leitura() as s:
        linha = s.get(Publicacao, id_publicacao)
        assert (linha.formato_conteudo, linha.conteudo) == ("HTML", "<p>novo</p>")


def test_obter_traz_formato_autor_e_itens_do_changelog(repo) -> None:  # type: ignore[no-untyped-def]
    r, _ = repo
    id_publicacao = r.criar_rascunho(
        0,
        _html(
            tipo=TipoPublicacao.ATUALIZACAO,
            versao="2.0.0",
            itens_atualizacao=(
                ItemNotaAtualizacao("Segundo", None, TipoItemAtualizacao.CORRECAO, 1),
                ItemNotaAtualizacao("Primeiro", "detalhe", TipoItemAtualizacao.NOVO, 0),
            ),
        ),
    ).id_publicacao
    r.publicar(0, id_publicacao)

    item = r.obter(id_sistema=0, id_usuario=1, id_grupo=None, id_publicacao=id_publicacao)

    assert item.formato == "HTML"
    assert item.criado_por == "Widson"
    assert [i.titulo for i in item.itens_atualizacao] == ["Primeiro", "Segundo"]
    assert item.itens_atualizacao[0].tipo is TipoItemAtualizacao.NOVO


def test_notificacao_usa_texto_puro_e_nao_html(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    # Resumo vazio de proposito: a notificacao precisa sair do texto, sem tags.
    id_publicacao = r.criar_rascunho(0, _html(resumo="")).id_publicacao

    r.publicar(0, id_publicacao)

    with banco.leitura() as s:
        mensagem = s.scalars(select(Notificacao.mensagem)).one()
    assert mensagem == "Ola Corpo rico"
    assert "<" not in mensagem


def test_corrigir_texto_preserva_formato(repo) -> None:  # type: ignore[no-untyped-def]
    r, banco = repo
    id_publicacao = r.criar_rascunho(0, _html()).id_publicacao
    r.publicar(0, id_publicacao)

    mudou = r.corrigir_texto(0, id_publicacao, titulo="Aviso", resumo="r", conteudo="<p>b</p>", formato="HTML")

    assert mudou is True
    with banco.leitura() as s:
        assert s.get(Publicacao, id_publicacao).formato_conteudo == "HTML"
