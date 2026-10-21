"""Editor rico: sanitizacao do HTML, formatos de conteudo, imagens e telas de leitura."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from luftbase import PlataformaLuft
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.conteudo.formatacao import (
    detectar_tipo_imagem,
    renderizar_conteudo,
    resumo_automatico,
)
from luftbase.conteudo.html_seguro import ids_imagens, sanitizar, texto_puro
from luftbase.conteudo.modelos import (
    ItemNotaAtualizacao,
    NovaPublicacao,
    PublicacaoUsuario,
    TipoItemAtualizacao,
)
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.nucleo.excecoes import ConteudoNaoEncontrado, ErroConteudo

# ---------------------------------------------------------------- sanitizador


def test_remove_script_e_conteudo_executavel() -> None:
    html = '<p>Oi</p><script>alert(1)</script><style>p{x:y}</style><iframe src="https://x.com"></iframe>'

    assert sanitizar(html) == "<p>Oi</p>"


def test_remove_atributos_de_evento_e_url_perigosa() -> None:
    html = '<p onclick="x()" style="color:red">a</p><a href="javascript:alert(1)">b</a><img src="data:image/png;base64,AA" onerror="x()">'

    limpo = sanitizar(html)

    assert "onclick" not in limpo
    assert "onerror" not in limpo
    assert "javascript" not in limpo
    assert "data:" not in limpo
    assert 'style="color: red"' in limpo
    assert "<a" not in limpo  # sem href valido, o link some e o texto fica
    assert "<img" not in limpo


def test_link_externo_ganha_rel_e_target() -> None:
    limpo = sanitizar('<a href="https://luft.com.br/x?a=1&b=2">site</a>')

    assert 'href="https://luft.com.br/x?a=1&amp;b=2"' in limpo
    assert 'target="_blank"' in limpo
    assert 'rel="noopener noreferrer"' in limpo


@pytest.mark.parametrize(
    "estilo, esperado",
    [
        ("font-size: 28px", "font-size: 28px"),
        ("font-size: 400px", ""),
        ("font-size: 2px", ""),
        ("color: #1d4ed8", "color: #1d4ed8"),
        ("background-color: rgb(253, 230, 138)", "background-color: rgb(253, 230, 138)"),
        ("text-align: center", "text-align: center"),
        ("position: fixed; top: 0", ""),
        ("color: red; background: url(http://x/y.png)", "color: red"),
        ("width: 50%", ""),  # largura so vale em imagem e tabela
    ],
)
def test_estilos_sao_filtrados_por_lista_fechada(estilo: str, esperado: str) -> None:
    limpo = sanitizar(f'<p style="{estilo}">t</p>')

    if esperado:
        assert f'style="{esperado}"' in limpo
    else:
        assert "style=" not in limpo


def test_imagens_aceitas_so_internas_estaticas_ou_https() -> None:
    limpo = sanitizar(
        '<img src="/ConnectAir/publicacoes/imagem/12" alt="a">'
        '<img src="luftimg:7">'
        '<img src="https://cdn.exemplo.com/x.png">'
        '<img src="http://inseguro.com/x.png">'
        '<img src="/_luftbase/static/img/changelog/banner.png">'
        '<img src="/static/../../etc/passwd">'
    )

    assert 'src="luftimg:12"' in limpo
    assert 'src="luftimg:7"' in limpo
    assert 'src="https://cdn.exemplo.com/x.png"' in limpo
    assert "http://inseguro" not in limpo
    assert 'src="luftbase:img/changelog/banner.png"' in limpo
    assert "passwd" not in limpo
    assert ids_imagens(limpo) == {7, 12}


def test_classe_so_vale_nos_destaques_conhecidos() -> None:
    limpo = sanitizar('<div class="pub-callout pub-alerta evil"><p>x</p></div><div class="outra">y</div>')

    assert 'class="pub-callout pub-alerta"' in limpo
    assert "evil" not in limpo
    assert 'class="outra"' not in limpo


def test_sanitizar_fecha_tags_abertas_e_e_idempotente() -> None:
    limpo = sanitizar("<p><strong>aberto <em>sem fechar")

    assert limpo == "<p><strong>aberto <em>sem fechar</em></strong></p>"
    assert sanitizar(limpo) == limpo


def test_equivalencias_e_tags_desconhecidas() -> None:
    limpo = sanitizar("<h1>T</h1><b>n</b><i>i</i><font size=7>f</font><marquee>m</marquee>")

    assert limpo == "<h2>T</h2><strong>n</strong><em>i</em>fm"


def test_texto_dentro_de_tag_e_escapado() -> None:
    assert sanitizar("<p>a &lt;script&gt; b</p>") == "<p>a &lt;script&gt; b</p>"


def test_tabela_preserva_estrutura() -> None:
    limpo = sanitizar('<table style="width: 100%"><tbody><tr><th colspan="2">T</th></tr><tr><td>a</td><td>b</td></tr></tbody></table>')

    assert '<table style="width: 100%">' in limpo
    assert '<th colspan="2">' in limpo
    assert limpo.count("<td>") == 2


def test_texto_puro_separa_blocos() -> None:
    assert texto_puro("<h2>Titulo</h2><p>um <strong>dois</strong></p><ul><li>a</li><li>b</li></ul>") == "Titulo um dois a b"


# ---------------------------------------------------------------- formatos


def test_resumo_automatico_corta_em_palavra_e_ignora_marcacao() -> None:
    html = "<p>" + ("palavra " * 80) + "</p>"

    resumo = resumo_automatico(html, "HTML")

    assert len(resumo) <= 281
    assert resumo.endswith("…")
    assert "<" not in resumo


def test_resumo_automatico_de_markdown_remove_sintaxe() -> None:
    assert resumo_automatico("## Titulo\n\nTexto **forte** aqui", "MARKDOWN") == "Titulo Texto forte aqui"


def test_renderizar_conteudo_html_resolve_imagens() -> None:
    saida = renderizar_conteudo(
        '<p>x</p><img src="luftimg:5" alt="a"><img src="luftbase:img/a.png">',
        "HTML",
        lambda caminho: f"/_luftbase/static/{caminho}",
        lambda id_imagem: f"/publicacoes/imagem/{id_imagem}",
    )

    assert 'src="/publicacoes/imagem/5"' in saida
    assert 'src="/_luftbase/static/img/a.png"' in saida
    assert "luftimg:" not in saida


def test_renderizar_conteudo_markdown_continua_funcionando() -> None:
    saida = renderizar_conteudo("**oi**", "MARKDOWN", lambda c: c, lambda i: str(i))

    assert "<strong>oi</strong>" in saida


def test_detectar_tipo_imagem_pelos_bytes() -> None:
    assert detectar_tipo_imagem(b"\x89PNG\r\n\x1a\n....") == "image/png"
    assert detectar_tipo_imagem(b"\xff\xd8\xff\xe0....") == "image/jpeg"
    assert detectar_tipo_imagem(b"GIF89a....") == "image/gif"
    assert detectar_tipo_imagem(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert detectar_tipo_imagem(b"<svg onload=alert(1)>") is None
    assert detectar_tipo_imagem(b"MZ\x90\x00") is None


# ---------------------------------------------------------------- dominio


def test_nova_publicacao_html_sanitiza_e_gera_resumo() -> None:
    dados = NovaPublicacao(
        titulo="Aviso",
        conteudo='<h2>Ola</h2><p onclick="x()">Corpo <strong>forte</strong></p><script>1</script>',
        criado_por="ti",
        formato="HTML",
    )

    assert "script" not in dados.conteudo
    assert "onclick" not in dados.conteudo
    assert dados.resumo == "Ola Corpo forte"


def test_nova_publicacao_respeita_resumo_do_autor() -> None:
    dados = NovaPublicacao(titulo="A", conteudo="<p>x</p>", criado_por="ti", formato="HTML", resumo="Meu resumo")

    assert dados.resumo == "Meu resumo"


def test_nova_publicacao_html_vazio_e_rejeitado() -> None:
    with pytest.raises(ErroConteudo):
        NovaPublicacao(titulo="A", conteudo="<p><br></p>", criado_por="ti", formato="HTML")


def test_nova_publicacao_html_so_com_imagem_vale() -> None:
    dados = NovaPublicacao(titulo="A", conteudo='<img src="luftimg:3">', criado_por="ti", formato="HTML")

    assert 'src="luftimg:3"' in dados.conteudo


def test_formato_invalido_e_rejeitado() -> None:
    with pytest.raises(ErroConteudo):
        NovaPublicacao(titulo="A", conteudo="x", criado_por="ti", formato="RTF")


# ---------------------------------------------------------------- telas

TOKEN = "t" * 40


def _aplicacao() -> tuple[Flask, object]:
    app = Flask(__name__)
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": 0,
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
            "LUFT_LDAP_SERVIDOR": "ldap.invalid",
            "LUFT_LDAP_DOMINIO": "luft",
        }
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app, configuracao)
    app.testing = True
    return app, estado


def _autenticar(cliente) -> None:  # type: ignore[no-untyped-def]
    usuario = UsuarioAutenticado(7, "teste", "Usuario Teste", None, 2, "TI")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}
        sessao["luftbase_csrf"] = TOKEN


def _liberar(monkeypatch, estado) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(type(estado.autorizacao), "possui", lambda _s, _u, _c: True)
    monkeypatch.setattr(
        type(estado.autorizacao),
        "consultar",
        lambda _s, _u, chaves: {chave: True for chave in chaves},
    )


def _publicacao(**extra) -> PublicacaoUsuario:  # type: ignore[no-untyped-def]
    base = {
        "id_publicacao": 9,
        "id_sistema": 0,
        "tipo": "ATUALIZACAO",
        "audiencia": "GERAL",
        "titulo": "Versao 2",
        "resumo": "Resumo curto",
        "conteudo": '<h2>Novidades</h2><p style="font-size: 28px">grande</p><img src="luftimg:4" alt="foto">',
        "prioridade": "ALTA",
        "versao": "2.0.0",
        "fixado": False,
        "lida": False,
        "exibir_a_partir_de": None,
        "expira_em": None,
        "data_publicacao": datetime(2026, 10, 21, 9, 30),
        "formato": "HTML",
        "criado_por": "Widson Araujo",
        "itens_atualizacao": (
            ItemNotaAtualizacao("Editor rico", "Formatacao como e-mail", TipoItemAtualizacao.NOVO, 0),
        ),
    }
    base.update(extra)
    return PublicacaoUsuario(**base)


def test_leitura_mostra_html_formatado_autor_e_itens(monkeypatch) -> None:
    app, estado = _aplicacao()
    monkeypatch.setattr(type(estado.publicacoes), "obter_para_usuario", lambda _s, _u, _g, _i: _publicacao())
    monkeypatch.setattr(type(estado.publicacoes), "marcar_lida", lambda _s, _u, _g, _i: True)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/9")

    assert resposta.status_code == 200
    assert '<p style="font-size: 28px">grande</p>' in resposta.text
    assert 'src="/publicacoes/imagem/4"' in resposta.text
    assert "Widson Araujo" in resposta.text
    assert "O que mudou" in resposta.text
    assert "Editor rico" in resposta.text
    assert "21/10/2026" in resposta.text


def test_leitura_nao_executa_html_malicioso(monkeypatch) -> None:
    app, estado = _aplicacao()
    malicioso = _publicacao(conteudo='<p>ok</p><script>alert(1)</script><img src=x onerror="alert(2)">')
    monkeypatch.setattr(type(estado.publicacoes), "obter_para_usuario", lambda _s, _u, _g, _i: malicioso)
    monkeypatch.setattr(type(estado.publicacoes), "marcar_lida", lambda _s, _u, _g, _i: True)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/9")

    assert "<script>alert" not in resposta.text
    assert "onerror" not in resposta.text


def test_feed_lista_mais_novo_primeiro_com_fixados_no_topo(monkeypatch) -> None:
    app, estado = _aplicacao()
    itens = (
        _publicacao(id_publicacao=1, titulo="Antiga"),
        _publicacao(id_publicacao=2, titulo="Fixa antiga", fixado=True),
        _publicacao(id_publicacao=3, titulo="Recente"),
    )
    monkeypatch.setattr(
        type(estado.publicacoes),
        "listar_para_usuario",
        lambda _s, _u, _g, **_o: SimpleNamespace(itens=itens),
    )
    cliente = app.test_client()
    _autenticar(cliente)

    texto = cliente.get("/publicacoes/atualizacoes").text

    assert texto.index("Fixa antiga") < texto.index("Recente") < texto.index("Antiga")
    assert "Fixados" in texto
    assert "pub-msg" in texto


def test_upload_de_imagem_valida_tipo_e_entrega(monkeypatch) -> None:
    import io

    app, estado = _aplicacao()
    _liberar(monkeypatch, estado)
    guardadas: dict[int, tuple[str, bytes, str, int | None]] = {}

    def _salvar(_s, *, dados, mime, nome, criado_por):  # type: ignore[no-untyped-def]
        guardadas[1] = (mime, dados, "abc123", None)
        return 1

    monkeypatch.setattr(type(estado.publicacoes), "salvar_imagem", _salvar)
    monkeypatch.setattr(
        type(estado.publicacoes),
        "obter_imagem",
        lambda _s, id_imagem: guardadas[id_imagem] if id_imagem in guardadas else (_ for _ in ()).throw(ConteudoNaoEncontrado("x")),
    )
    cliente = app.test_client()
    _autenticar(cliente)
    cabecalho = {"X-CSRF-Token": TOKEN}
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    ok = cliente.post(
        "/publicacoes/api/imagens",
        data={"arquivo": (io.BytesIO(png), "foto.png")},
        headers=cabecalho,
        content_type="multipart/form-data",
    )
    falso = cliente.post(
        "/publicacoes/api/imagens",
        data={"arquivo": (io.BytesIO(b"<svg onload=alert(1)>"), "x.png")},
        headers=cabecalho,
        content_type="multipart/form-data",
    )
    entrega = cliente.get("/publicacoes/imagem/1")
    ausente = cliente.get("/publicacoes/imagem/99")

    assert ok.status_code == 200
    assert ok.get_json()["dados"] == {"id_imagem": 1, "url": "/publicacoes/imagem/1"}
    assert falso.status_code == 400
    assert entrega.status_code == 200
    assert entrega.mimetype == "image/png"
    assert entrega.headers["X-Content-Type-Options"] == "nosniff"
    assert entrega.data == png
    assert ausente.status_code == 404


def test_upload_sem_permissao_e_negado(monkeypatch) -> None:
    import io

    app, estado = _aplicacao()
    monkeypatch.setattr(
        type(estado.autorizacao),
        "consultar",
        lambda _s, _u, chaves: {chave: False for chave in chaves},
    )
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.post(
        "/publicacoes/api/imagens",
        data={"arquivo": (io.BytesIO(b"\x89PNG\r\n\x1a\n"), "a.png")},
        headers={"X-CSRF-Token": TOKEN},
        content_type="multipart/form-data",
    )

    assert resposta.status_code == 403


def test_previa_devolve_html_sanitizado(monkeypatch) -> None:
    app, estado = _aplicacao()
    _liberar(monkeypatch, estado)
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.post(
        "/publicacoes/api/previa",
        json={"conteudo": '<p style="color: red" onclick="x()">oi</p><script>1</script>', "formato": "HTML"},
        headers={"X-CSRF-Token": TOKEN},
    )

    assert resposta.status_code == 200
    assert resposta.get_json()["dados"]["html"] == '<p style="color: red">oi</p>'


def test_painel_renderiza_indicadores_e_previa_das_publicacoes(monkeypatch) -> None:
    import luftbase.web.publicacoes as modulo

    app, estado = _aplicacao()
    _liberar(monkeypatch, estado)

    def _admin(id_publicacao: int, status: str) -> dict[str, object]:
        return {
            "id": id_publicacao,
            "id_publicacao": id_publicacao,
            "id_sistema": 0,
            "tipo": "COMUNICADO",
            "tipo_publicacao": "COMUNICADO",
            "status": status,
            "tipo_audiencia": "GERAL",
            "ids_grupos": [],
            "titulo": f"Aviso {id_publicacao}",
            "resumo": "",
            "previa": "Texto de previa <b>sem html</b>",
            "conteudo": "<p>x</p>",
            "formato": "HTML",
            "conteudo_editor": "<p>x</p>",
            "prioridade": "NORMAL",
            "versao": None,
            "notificar": True,
            "fixado": False,
            "criado_por": "Widson",
            "fonte": "INTERNO",
            "data_criacao": "2026-10-21T09:00:00",
            "data_publicacao": None,
            "exibir_a_partir_de": None,
            "expira_em": None,
            "itens_atualizacao": [],
        }

    monkeypatch.setattr(
        modulo,
        "_listar_administracao",
        lambda _tipo: [_admin(1, "PUBLICADO"), _admin(2, "RASCUNHO"), _admin(3, "RASCUNHO")],
    )
    monkeypatch.setattr(modulo, "_listar_sistemas", lambda: [{"id": 0, "nome": "Todos"}])
    cliente = app.test_client()
    _autenticar(cliente)

    resposta = cliente.get("/publicacoes/painel/comunicados")

    assert resposta.status_code == 200
    assert 'data-filtro="RASCUNHO"' in resposta.text
    assert "<strong>2</strong><span>Rascunhos</span>" in resposta.text
    assert "<strong>1</strong><span>Publicados</span>" in resposta.text
    assert "Texto de previa &lt;b&gt;sem html&lt;/b&gt;" in resposta.text
    assert "js/editor_rico.js" in resposta.text
    assert 'id="publicacaoEditor"' in resposta.text
    assert "/publicacoes/api/imagens" in resposta.text


def test_bloco_de_codigo_preserva_texto_e_remove_perigo() -> None:
    limpo = sanitizar('<pre onclick="x()"><code>linha 1\n  linha 2 &lt;b&gt;</code></pre><pre><script>1</script></pre>')

    assert limpo.startswith("<pre><code>linha 1\n  linha 2 &lt;b&gt;</code></pre>")
    assert "onclick" not in limpo and "script" not in limpo


def test_lista_do_painel_nao_carrega_o_texto_completo() -> None:
    import luftbase.web.publicacoes as modulo

    app, _estado = _aplicacao()
    item = SimpleNamespace(
        id_publicacao=5, id_sistema=0, tipo_publicacao="COMUNICADO", status_publicacao="RASCUNHO",
        tipo_audiencia="GERAL", grupos=[], titulo="T", resumo="r", conteudo="<p>" + "x" * 5000 + "</p>",
        formato_conteudo="HTML", prioridade="NORMAL", versao=None, notificar=True, fixado=False,
        criado_por="W", fonte="INTERNO", data_criacao=None, data_publicacao=None,
        exibir_a_partir_de=None, expira_em=None, itens_atualizacao=[],
    )

    leve = modulo._publicacao_administracao(item)
    with app.test_request_context("/"):
        completo = modulo._publicacao_administracao(item, completo=True)

    assert "conteudo" not in leve and "conteudo_editor" not in leve
    assert leve["resumo"] == "r" and leve["formato"] == "HTML"
    assert completo["conteudo"].startswith("<p>xxx")
    assert completo["conteudo_editor"].startswith("<p>xxx")
