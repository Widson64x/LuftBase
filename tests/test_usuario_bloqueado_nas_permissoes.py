"""Tela de permissoes: pessoa bloqueada aparece com tarja e nada nela pode ser alterado."""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from luftbase.web import seguranca

TEMPLATE = (
    Path(seguranca.__file__).resolve().parent.parent
    / "interface"
    / "templates"
    / "luftbase"
    / "seguranca"
    / "gerenciador.html"
)


class _Repo:
    def __init__(self, bloqueados: set[int]) -> None:
        self.bloqueados = bloqueados

    def esta_bloqueado(self, codigo: int) -> bool:
        return codigo in self.bloqueados


def _preparar(monkeypatch: pytest.MonkeyPatch, bloqueados: set[int]) -> None:
    estado = SimpleNamespace(usuarios_core=_Repo(bloqueados))
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)
    monkeypatch.setattr(seguranca, "validar_csrf_requisicao", lambda: None)
    monkeypatch.setattr(seguranca, "resolver_escopo_sistema", lambda _s: 1)


def _chamar(rota: Any, corpo: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Chama a rota sem os decoradores de login/permissao, como os demais testes de seguranca."""

    app = Flask(__name__)
    with app.test_request_context(method="POST", json=corpo):
        resposta = inspect.unwrap(rota)()
    corpo_resposta, codigo = resposta if isinstance(resposta, tuple) else (resposta, 200)
    return codigo, corpo_resposta.get_json()


def test_helper_recusa_so_usuario_bloqueado(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar(monkeypatch, {5})
    app = Flask(__name__)
    with app.app_context():
        recusa = seguranca._recusar_alteracao_de_bloqueado("Usuario", 5)  # noqa: SLF001
        assert recusa is not None and recusa[1] == 423
        assert seguranca._recusar_alteracao_de_bloqueado("Usuario", 6) is None  # noqa: SLF001
        # O codigo de um grupo pode coincidir com o de uma pessoa bloqueada: grupo nunca e recusado.
        assert seguranca._recusar_alteracao_de_bloqueado("Grupo", 5) is None  # noqa: SLF001


def test_salvar_permissao_de_usuario_bloqueado_e_recusado(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar(monkeypatch, {5})

    for acao in ("Permitir", "Bloquear", "Resetar"):
        codigo, corpo = _chamar(
            seguranca.salvar_vinculo,
            {"IdAlvo": 5, "IdPermissao": 10, "Tipo": "Usuario", "Acao": acao},
        )
        assert codigo == 423, acao
        assert "bloqueado" in corpo["message"].lower()


def test_limpar_regras_de_usuario_bloqueado_e_recusado(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar(monkeypatch, {5})

    codigo, _ = _chamar(seguranca.limpar_todas_regras, {"id_alvo": 5, "tipo": "Usuario"})

    assert codigo == 423


def test_espelhar_para_usuario_bloqueado_e_recusado(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar(monkeypatch, {5})

    codigo, _ = _chamar(
        seguranca.espelhar_permissoes,
        {"id_origem": 2, "id_destino": 5, "tipo_origem": "Grupo", "tipo_destino": "Usuario"},
    )

    assert codigo == 423


def test_codigos_bloqueados_vem_do_core() -> None:
    sessao = SimpleNamespace(
        execute=lambda _consulta: SimpleNamespace(scalars=lambda: iter([5, 9]))
    )

    @contextmanager
    def leitura():  # type: ignore[no-untyped-def]
        yield sessao

    estado = SimpleNamespace(bancos=SimpleNamespace(core=SimpleNamespace(leitura=leitura)))

    assert seguranca._codigos_bloqueados(estado) == {5, 9}  # noqa: SLF001


def test_core_fora_do_ar_abre_a_tela_sem_tarjas() -> None:
    @contextmanager
    def leitura():  # type: ignore[no-untyped-def]
        raise SQLAlchemyError("fora do ar")
        yield  # pragma: no cover

    estado = SimpleNamespace(bancos=SimpleNamespace(core=SimpleNamespace(leitura=leitura)))

    assert seguranca._codigos_bloqueados(estado) == set()  # noqa: SLF001


def test_usuario_item_traz_o_bloqueio() -> None:
    livre = seguranca.UsuarioItem(1, "Ana", "ana", None, None)
    preso = seguranca.UsuarioItem(2, "Bia", "bia", None, None, True)

    assert livre.bloqueado is False and preso.bloqueado is True


def test_tela_mostra_tarja_e_trava_a_edicao_da_pessoa_bloqueada() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")

    # Tarja e marcacao na lista lateral
    assert 'class="tarja-bloqueado"' in html and 'data-bloqueado="' in html
    assert "bloqueado: {{ 'true' if (user|attr('bloqueado')) else 'false' }}" in html
    # Toda acao que escreve passa pela trava do alvo, nao so pela permissao de editar
    for funcao in ("DefinirRegra", "AbrirModalEspelhar", "LimparTodasRegrasAlvo"):
        trecho = html.split(f"function {funcao}(", 1)[1][:160]
        assert "PodeAlterarAlvo()" in trecho, funcao
    assert "async function ResetarPermissao(idPerm) {\n        if (!PodeAlterarAlvo()) return;" in html
    # O destino do espelhamento nao oferece pessoas bloqueadas
    assert "document.getElementById('buscaDestino')?.value, null, true)" in html
    # O desbloqueio continua disponivel: o botao so depende de PodeBloquear
    assert "{% if PodeBloquear %}" in html and "AlternarBloqueioUsuario()" in html
