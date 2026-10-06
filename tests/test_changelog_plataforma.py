"""Markdown seguro das publicações e a nota global de lançamento da plataforma."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from luftbase import servidor
from luftbase.conteudo import changelog_plataforma as changelog
from luftbase.conteudo.markdown_seguro import renderizar
from luftbase.conteudo.modelos import TipoAudiencia, TipoPublicacao

IMAGENS = Path(servidor.__file__).resolve().parent / "interface" / "static" / "img" / "changelog"


def test_html_cru_e_escapado() -> None:
    html = str(renderizar("<script>alert(1)</script> <img src=x onerror=alert(1)>"))

    assert "<script" not in html and "<img" not in html
    assert "&lt;script&gt;" in html


def test_imagem_so_aceita_https_ou_estatico_do_luftbase() -> None:
    html = str(
        renderizar(
            "![a](javascript:alert(1)) ![b](http://x/y.png) ![c](luftbase:../segredo.svg) "
            "![d](https://x/y.png) ![e](luftbase:img/changelog/banner.png)"
        )
    )

    assert html.count("<img") == 2
    fontes = re.findall(r'src="([^"]+)"', html)
    assert sorted(fontes) == [
        "/_luftbase/static/img/changelog/banner.png",
        "https://x/y.png",
    ]


def test_link_so_http_e_atributos_nao_escapam() -> None:
    html = str(renderizar('[ok](https://a.com/"onmouseover="x) [mau](javascript:alert(1))'))

    assert 'onmouseover="x' not in html
    assert 'href="javascript' not in html


def test_marcador_interno_nao_e_forjavel() -> None:
    assert "\x00" not in str(renderizar("a \x000\x00 b"))


def test_blocos_destaque_cards_e_listas() -> None:
    html = str(renderizar(":::sucesso\n**ok**\n:::\n\n:::cards\n### A\ntexto\n### B\nx\n:::\n\n- um\n- dois\n\n1. a"))

    assert "md-destaque md-sucesso" in html and "<strong>ok</strong>" in html
    assert html.count('class="md-card"') == 2
    assert "<ul><li>um</li><li>dois</li></ul>" in html and "<ol><li>a</li></ol>" in html


def test_todas_as_imagens_do_changelog_existem() -> None:
    usadas = re.findall(r"luftbase:img/changelog/([\w.-]+)", changelog.CONTEUDO)

    assert usadas
    for nome in usadas:
        assert (IMAGENS / nome).is_file(), nome
        assert (IMAGENS / nome).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", nome


def test_changelog_renderiza_sem_sobras_de_marcacao() -> None:
    html = str(renderizar(changelog.CONTEUDO))

    assert "<img" in html and "md-destaque" in html and "md-alerta" in html
    assert ":::" not in html and "###" not in html and "![" not in html


class _ServicoFalso:
    def __init__(self, existentes=()) -> None:
        self.existentes = list(existentes)
        self.criadas: list = []
        self.atualizadas: list = []
        self.publicadas: list = []

    def listar_administracao(self, **_):
        return self.existentes

    def criar_rascunho(self, dados):
        self.criadas.append(dados)
        return 7

    def atualizar_rascunho(self, id_publicacao, dados):
        self.atualizadas.append(id_publicacao)
        return True

    def corrigir_texto(self, id_publicacao, dados):
        self.corrigidas = getattr(self, "corrigidas", [])
        self.corrigidas.append(id_publicacao)
        return True

    def publicar(self, id_publicacao):
        self.publicadas.append(id_publicacao)
        return True


def test_publica_como_nota_geral_com_notificacao() -> None:
    servico = _ServicoFalso()

    resultado = changelog.publicar_changelog_plataforma(servico, versao="2.0")

    dados = servico.criadas[0]
    assert (resultado.id_publicacao, resultado.acao) == (7, "criada")
    assert dados.tipo is TipoPublicacao.ATUALIZACAO and dados.audiencia is TipoAudiencia.GERAL
    assert dados.notificar is True and dados.versao == "2.0" and servico.publicadas == [7]


def test_nao_duplica_nota_ja_publicada_e_reaproveita_rascunho() -> None:
    publicada = SimpleNamespace(id_publicacao=3, titulo=changelog.TITULO, status_publicacao="PUBLICADO")
    servico = _ServicoFalso([publicada])
    resultado = changelog.publicar_changelog_plataforma(servico, versao="2.0")
    assert resultado.acao == "texto_corrigido" and not servico.criadas and not servico.publicadas
    assert servico.corrigidas == [3]  # texto novo, sem renotificar

    rascunho = SimpleNamespace(id_publicacao=4, titulo=changelog.TITULO, status_publicacao="RASCUNHO")
    servico = _ServicoFalso([rascunho])
    resultado = changelog.publicar_changelog_plataforma(servico, versao="2.0")
    assert (resultado.acao, servico.atualizadas, servico.publicadas) == ("atualizada", [4], [4])


def test_sem_publicar_so_deixa_rascunho() -> None:
    servico = _ServicoFalso()

    changelog.publicar_changelog_plataforma(servico, versao="2.0", publicar=False)

    assert servico.criadas and not servico.publicadas


@pytest.mark.parametrize("versao", ["2.0", "2026.10"])
def test_versao_e_obrigatoria_para_nota_de_atualizacao(versao: str) -> None:
    assert changelog.nova_publicacao(versao=versao).versao == versao


def test_a_nota_fala_ao_usuario_e_nao_de_infraestrutura() -> None:
    texto = changelog.CONTEUDO
    assert changelog.CONTEUDO.count("luftbase:img/changelog/") >= 12
    assert "Luft-Control" in texto and "sistemas web" in texto
    for proibido in ("Todos os sistemas Luft", "Horário de Brasília", "cofre", "Vault", "homologação", "auditoria"):
        assert proibido not in texto, proibido


def test_reconhece_a_nota_publicada_com_titulo_de_versao_anterior() -> None:
    antiga = SimpleNamespace(
        id_publicacao=9, titulo=changelog.TITULOS_ANTERIORES[-1], status_publicacao="PUBLICADO"
    )
    servico = _ServicoFalso([antiga])

    resultado = changelog.publicar_changelog_plataforma(servico, versao="2.0")

    assert resultado.id_publicacao == 9 and not servico.criadas and not servico.publicadas
    assert servico.corrigidas == [9]


def test_toda_imagem_citada_em_notas_antigas_ainda_existe() -> None:
    # Apagar uma imagem quebra notas ja publicadas: so se remove com a nota corrigida no banco.
    import re

    for nome in re.findall(r"luftbase:img/changelog/([\w.-]+)", changelog.CONTEUDO):
        assert (IMAGENS / nome).is_file(), nome
