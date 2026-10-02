"""Testes unitarios e estruturais do catalogo, hierarquia e precedencias."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from luftbase.autorizacao.catalogo import (
    ACOES_PERMISSAO,
    MODULOS_PADRAO,
    PERMISSOES_PADRAO,
    AcaoPermissao,
    PermissaoLuftBase,
)
from luftbase.autorizacao.repositorio import RepositorioAutorizacao, _RegraHierarquia
from luftbase.persistencia.core.catalogo import sincronizar_catalogo_workspace


def test_catalogo_contem_exatamente_nove_modulos() -> None:
    """O catalogo canonico deve conter exatamente 9 modulos padrao."""
    assert len(MODULOS_PADRAO) == 9
    codigos = [m.codigo for m in MODULOS_PADRAO]
    assert codigos == [
        "PLATAFORMA",
        "INICIO",
        "CONFIGURACOES",
        "SEGURANCA",
        "OBSERVABILIDADE",
        "AMBIENTE",
        "CONTEUDO",
        "NOTIFICACOES",
        "DESENVOLVIMENTO",
    ]


def test_catalogo_contem_exatamente_quarenta_e_oito_permissoes() -> None:
    """O catalogo canonico deve conter exatamente 49 permissoes canonicas."""
    assert len(PERMISSOES_PADRAO) == 49
    chaves = [p.chave.value for p in PERMISSOES_PADRAO]
    assert len(set(chaves)) == 49


def test_todas_as_chaves_possuem_tres_segmentos() -> None:
    """Toda chave de permissao deve seguir rigorosamente o padrao MODULO.RECURSO.ACAO."""
    for definicao in PERMISSOES_PADRAO:
        partes = definicao.chave.value.split(".")
        assert len(partes) == 3, f"A chave {definicao.chave.value} deve ter 3 segmentos."
        assert partes[0] == definicao.modulo
        assert partes[1] == definicao.recurso
        assert partes[2] == definicao.acao.value


def test_todas_as_acoes_pertencem_ao_enum_acao_permissao() -> None:
    """Toda acao associada a uma permissao deve ser membro valido de AcaoPermissao."""
    acoes_validas = {acao.value for acao in AcaoPermissao}
    assert acoes_validas == set(ACOES_PERMISSAO)
    for definicao in PERMISSOES_PADRAO:
        assert definicao.acao in AcaoPermissao
        assert definicao.acao.value in acoes_validas


def test_pais_declarados_antes_dos_filhos_na_tupla() -> None:
    """Para sincronizacao sem falhas de FK, os pais devem preceder seus filhos."""
    declarados: set[PermissaoLuftBase] = set()
    for definicao in PERMISSOES_PADRAO:
        if definicao.pai is not None:
            assert definicao.pai in declarados, (
                f"O pai {definicao.pai} da permissao {definicao.chave} deve vir antes dela."
            )
        declarados.add(definicao.chave)


def test_arvore_de_permissoes_sem_ciclos() -> None:
    """A navegacao da arvore de heranca nunca pode gerar ciclos."""
    mapa_pais = {p.chave: p.pai for p in PERMISSOES_PADRAO}
    for chave in mapa_pais:
        visitados: set[PermissaoLuftBase] = set()
        atual: PermissaoLuftBase | None = chave
        while atual is not None:
            assert atual not in visitados, f"Ciclo detectado ao seguir ancestrais de {chave}."
            visitados.add(atual)
            atual = mapa_pais.get(atual)
            assert len(visitados) <= 32, f"Profundidade excessiva para {chave}."


def test_master_herda_filhos_e_netos() -> None:
    """Uma concessao no no raiz (distancia 2) deve conceder o neto (distancia 0)."""
    regras = [
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=None,
            grupo_concede=None,
        ),
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=1,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=None,
            grupo_concede=None,
        ),
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=2,
            ativo=True,
            possui_pai=False,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
    ]
    decisao = RepositorioAutorizacao._decidir(regras)
    assert decisao is True


def test_bloqueio_explicito_do_filho_sobrepoe_concessao_do_pai() -> None:
    """Um bloqueio explicito (distancia 0) prevalece sobre a concessao do pai (distancia 1)."""
    regras = [
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=False,
        ),
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=1,
            ativo=True,
            possui_pai=False,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
    ]
    decisao = RepositorioAutorizacao._decidir(regras)
    assert decisao is False


def test_restauracao_da_heranca_ao_remover_regra() -> None:
    """Ao remover a regra especifica do filho, a concessao do pai volta a ser herdada."""
    # Sem regra na distancia 0, regra na distancia 1 concede
    regras = [
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=None,
            grupo_concede=None,
        ),
        _RegraHierarquia(
            chave="SEGURANCA.PERMISSOES.CRIAR",
            escopo=0,
            distancia=1,
            ativo=True,
            possui_pai=False,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
    ]
    decisao = RepositorioAutorizacao._decidir(regras)
    assert decisao is True


def test_prioridade_de_usuario_sobre_grupo() -> None:
    """Regra de usuario vence a de grupo, mesmo que o grupo conceda e o usuario negue."""
    regras = [
        _RegraHierarquia(
            chave="INICIO.PAINEL.VISUALIZAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=False,
            vinculo_usuario=10,
            usuario_concede=False,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
    ]
    assert RepositorioAutorizacao._decidir(regras) is False

    # Usuario concedendo supera grupo negando
    regras_inversas = [
        _RegraHierarquia(
            chave="INICIO.PAINEL.VISUALIZAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=False,
            vinculo_usuario=10,
            usuario_concede=True,
            vinculo_grupo=6,
            grupo_concede=False,
        ),
    ]
    assert RepositorioAutorizacao._decidir(regras_inversas) is True


def test_ancestral_inativo_nega_acesso_a_toda_subarvore() -> None:
    """Qualquer ancestral com ativo=False nega a permissao, independente de concessoes."""
    regras = [
        _RegraHierarquia(
            chave="CONTEUDO.COMUNICADOS.PUBLICAR",
            escopo=0,
            distancia=0,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=10,
            usuario_concede=True,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
        _RegraHierarquia(
            chave="CONTEUDO.COMUNICADOS.PUBLICAR",
            escopo=0,
            distancia=1,
            ativo=False,  # Ancestral inativo!
            possui_pai=False,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=True,
        ),
    ]
    assert RepositorioAutorizacao._decidir(regras) is False


def test_chave_desconhecida_e_lista_vazia_negam_acesso() -> None:
    """Lista de regras vazia nega imediatamente (fail-closed)."""
    assert RepositorioAutorizacao._decidir([]) is False


def test_profundidade_maior_que_limite_nega_acesso() -> None:
    """Se a profundidade alcancar 32 e ainda houver pai, nega o acesso."""
    regras = [
        _RegraHierarquia(
            chave="CHAVE.PROFUNDA",
            escopo=0,
            distancia=32,
            ativo=True,
            possui_pai=True,
            vinculo_usuario=None,
            usuario_concede=None,
            vinculo_grupo=6,
            grupo_concede=True,
        )
    ]
    assert RepositorioAutorizacao._decidir(regras) is False


def test_sincronizacao_catalogo_grupo_invalido_dispara_erro() -> None:
    """Codigo de grupo administrador negativo ou zero dispara ValueError."""
    conexao = MagicMock()
    with pytest.raises(ValueError, match="positivo"):
        sincronizar_catalogo_workspace(conexao, grupo_administrador=0)
    with pytest.raises(ValueError, match="positivo"):
        sincronizar_catalogo_workspace(conexao, grupo_administrador=-5)


def test_sincronizacao_catalogo_retorna_resumo_correto() -> None:
    """Mock de conexao confirma contagem de 9 modulos e 49 permissoes."""
    conexao = MagicMock()
    conexao.scalar.side_effect = lambda _query: 1  # Retorna ID simulado

    resumo = sincronizar_catalogo_workspace(conexao, grupo_administrador=6)

    assert resumo.modulos == 9
    assert resumo.permissoes == 49
    assert resumo.grupo_administrador == 6
    assert conexao.execute.call_count >= 1 + 9 + 1 + 49 + 1
