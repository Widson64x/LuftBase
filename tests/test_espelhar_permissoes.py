"""Espelhar/atribuir permissoes a usuario que ainda nao fez login, e a tela de copia."""

from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from luftbase.web import seguranca

TEMPLATE = (
    Path(seguranca.__file__).resolve().parent.parent
    / "interface"
    / "templates"
    / "luftbase"
    / "seguranca"
    / "gerenciador.html"
)


def _estado(*, no_core: bool, no_diretorio: bool):  # type: ignore[no-untyped-def]
    sessao_core = MagicMock()
    sessao_core.execute.return_value.first.return_value = (1,) if no_core else None
    origem = (
        SimpleNamespace(
            login=" joerdson.nascimento ",
            nome_completo="Joerdson Martins",
            email=None,
            id_grupo=7,
            grupo=SimpleNamespace(sigla="ARMAZEM"),
        )
        if no_diretorio
        else None
    )
    sessao_dir = MagicMock()
    sessao_dir.get.return_value = origem

    @contextmanager
    def leitura_core():  # type: ignore[no-untyped-def]
        yield sessao_core

    @contextmanager
    def leitura_dir():  # type: ignore[no-untyped-def]
        yield sessao_dir

    return SimpleNamespace(
        bancos=SimpleNamespace(
            core=SimpleNamespace(leitura=leitura_core),
            diretorio=SimpleNamespace(leitura=leitura_dir),
        ),
        usuarios_core=MagicMock(),
    )


def test_usuario_que_nunca_logou_e_criado_a_partir_do_diretorio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    estado = _estado(no_core=False, no_diretorio=True)
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)

    assert seguranca.garantir_usuario_no_core(2259) is True

    estado.usuarios_core.garantir_usuario_do_diretorio.assert_called_once_with(
        codigo_usuario=2259,
        login_usuario="joerdson.nascimento",
        nome_usuario="Joerdson Martins",
        email_usuario=None,
        codigo_usuariogrupo=7,
        sigla_usuariogrupo="ARMAZEM",
    )


def test_usuario_que_ja_existe_nao_e_recriado(monkeypatch: pytest.MonkeyPatch) -> None:
    estado = _estado(no_core=True, no_diretorio=True)
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)

    assert seguranca.garantir_usuario_no_core(2259) is True
    estado.usuarios_core.garantir_usuario_do_diretorio.assert_not_called()


def test_usuario_que_nem_o_diretorio_conhece_e_recusado(monkeypatch: pytest.MonkeyPatch) -> None:
    estado = _estado(no_core=False, no_diretorio=False)
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)

    assert seguranca.garantir_usuario_no_core(999999) is False
    estado.usuarios_core.garantir_usuario_do_diretorio.assert_not_called()


def test_rotas_garantem_o_usuario_antes_de_gravar() -> None:
    codigo = Path(seguranca.__file__).read_text(encoding="utf-8")

    espelhar = codigo[codigo.index("def espelhar_permissoes") :]
    salvar = codigo[codigo.index("def salvar_vinculo") : codigo.index("def resumo_regras_origem")]

    assert espelhar.index("garantir_usuario_no_core(id_destino)") < espelhar.index(
        "estado.bancos.core.escrita()"
    )
    assert salvar.index("garantir_usuario_no_core(id_alvo)") < salvar.index(
        "estado.bancos.core.escrita()"
    )


def test_ids_usados_pelo_javascript_do_modal_existem_no_html() -> None:
    texto = TEMPLATE.read_text(encoding="utf-8")
    html = texto[
        texto.index("modalEspelharPermissoes") : texto.index(
            "{% endcall %}", texto.index("modalEspelharPermissoes")
        )
    ]
    js = texto[
        texto.index("function AbrirModalEspelhar()") : texto.index(
            "async function LimparTodasRegrasAlvo"
        )
    ]

    ids_html = set(re.findall(r'id="([^"]+)"', html))
    ids_js = set(re.findall(r"getElementById\('([^']+)'\)", js)) | set(
        re.findall(r"getElementById\(`btn\$\{prefixo\}(\w+)`\)", js)
    )
    # Os botoes de tipo sao montados com o prefixo (Origem/Destino).
    esperados = {i for i in ids_js if not i.startswith("btn") or i in ids_html}
    faltando = {i for i in esperados if i not in ids_html} - {"TipoGrupo", "TipoUsuario"}

    assert not faltando, f"ids do JS sem elemento no modal: {sorted(faltando)}"
    for prefixo in ("Origem", "Destino"):
        assert f"btn{prefixo}TipoGrupo" in ids_html and f"btn{prefixo}TipoUsuario" in ids_html


def test_modal_usa_linguagem_simples_e_nao_usa_alert_para_erros() -> None:
    texto = TEMPLATE.read_text(encoding="utf-8")
    modal = texto[
        texto.index("modalEspelharPermissoes") : texto.index(
            "{% endcall %}", texto.index("modalEspelharPermissoes")
        )
    ]
    envio = texto[
        texto.index("async function SubmeterEspelhamento") : texto.index(
            "async function LimparTodasRegrasAlvo"
        )
    ]

    for termo in ("Copiar de quem?", "Quem vai receber?", "Como aplicar?", "Deixar igual à origem"):
        assert termo in modal
    assert "Estratégia" not in modal
    assert "alert('Erro" not in envio and "confirm(" not in envio
