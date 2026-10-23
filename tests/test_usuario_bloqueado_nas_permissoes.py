"""Tela de permissoes: pessoa bloqueada aparece com tarja e nada nela pode ser alterado.

Dois bloqueios contam: `core.tb_usuario.bloqueado` (do LuftBase) e `usuario.Usuario_Bloqueado` do Luftinforma
(cadastro corporativo).
"""

from __future__ import annotations

import inspect
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError

from luftbase.persistencia.diretorio import UsuarioDiretorio
from luftbase.web import seguranca

TEMPLATE = (
    Path(seguranca.__file__).resolve().parent.parent
    / "interface"
    / "templates"
    / "luftbase"
    / "seguranca"
    / "gerenciador.html"
)


def _banco(*, valores: list[int] | None = None, escalar: Any = None, primeira: Any = None, quebra: bool = False):  # type: ignore[no-untyped-def]
    """Banco falso: cada consulta devolve o que o teste preparou."""

    @contextmanager
    def leitura():  # type: ignore[no-untyped-def]
        if quebra:
            raise SQLAlchemyError("fora do ar")
        yield SimpleNamespace(
            execute=lambda _consulta: SimpleNamespace(
                scalars=lambda: iter(valores or []),
                scalar_one_or_none=lambda: escalar,
                first=lambda: primeira,
            )
        )

    return SimpleNamespace(leitura=leitura)


class _Repo:
    def __init__(self, bloqueado: bool) -> None:
        self.bloqueado = bloqueado

    def esta_bloqueado(self, _codigo: int) -> bool:
        return self.bloqueado


def _preparar(monkeypatch: pytest.MonkeyPatch, *, no_core: bool = False, no_diretorio: bool = False) -> None:
    estado = SimpleNamespace(
        usuarios_core=_Repo(no_core),
        bancos=SimpleNamespace(
            core=_banco(primeira=(no_core, "desligamento")),
            diretorio=_banco(escalar=1 if no_diretorio else 0),
        ),
    )
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)
    monkeypatch.setattr(seguranca, "validar_csrf_requisicao", lambda: None)
    monkeypatch.setattr(seguranca, "resolver_escopo_sistema", lambda _s: 1)


def _chamar(rota: Any, corpo: dict[str, Any] | None = None, metodo: str = "POST", **kw: Any) -> tuple[int, dict[str, Any]]:
    """Chama a rota sem os decoradores de login/permissao, como os demais testes de seguranca."""

    app = Flask(__name__)
    with app.test_request_context(method=metodo, json=corpo):
        resposta = inspect.unwrap(rota)(**kw)
    corpo_resposta, codigo = resposta if isinstance(resposta, tuple) else (resposta, 200)
    return codigo, corpo_resposta.get_json()


ORIGENS = pytest.mark.parametrize("origem", ["core", "diretorio"])


def _bloquear(monkeypatch: pytest.MonkeyPatch, origem: str) -> None:
    _preparar(monkeypatch, no_core=origem == "core", no_diretorio=origem == "diretorio")


@ORIGENS
def test_helper_recusa_pessoa_bloqueada_em_qualquer_dos_bloqueios(monkeypatch: pytest.MonkeyPatch, origem: str) -> None:
    _bloquear(monkeypatch, origem)

    with Flask(__name__).app_context():
        recusa = seguranca._recusar_alteracao_de_bloqueado("Usuario", 5)  # noqa: SLF001

    assert recusa is not None and recusa[1] == 423


def test_helper_nao_recusa_pessoa_livre_nem_grupo(monkeypatch: pytest.MonkeyPatch) -> None:
    with Flask(__name__).app_context():
        _preparar(monkeypatch)
        assert seguranca._recusar_alteracao_de_bloqueado("Usuario", 6) is None  # noqa: SLF001

        # O codigo de um grupo pode coincidir com o de uma pessoa bloqueada: grupo nunca e recusado.
        _preparar(monkeypatch, no_core=True, no_diretorio=True)
        assert seguranca._recusar_alteracao_de_bloqueado("Grupo", 5) is None  # noqa: SLF001


@ORIGENS
def test_salvar_permissao_de_pessoa_bloqueada_e_recusado(monkeypatch: pytest.MonkeyPatch, origem: str) -> None:
    _bloquear(monkeypatch, origem)

    for acao in ("Permitir", "Bloquear", "Resetar"):
        codigo, corpo = _chamar(
            seguranca.salvar_vinculo, {"IdAlvo": 5, "IdPermissao": 10, "Tipo": "Usuario", "Acao": acao}
        )
        assert codigo == 423, acao
        assert "bloqueado" in corpo["message"].lower()


@ORIGENS
def test_limpar_regras_de_pessoa_bloqueada_e_recusado(monkeypatch: pytest.MonkeyPatch, origem: str) -> None:
    _bloquear(monkeypatch, origem)

    codigo, _ = _chamar(seguranca.limpar_todas_regras, {"id_alvo": 5, "tipo": "Usuario"})

    assert codigo == 423


@ORIGENS
def test_espelhar_para_pessoa_bloqueada_e_recusado(monkeypatch: pytest.MonkeyPatch, origem: str) -> None:
    _bloquear(monkeypatch, origem)

    codigo, _ = _chamar(
        seguranca.espelhar_permissoes,
        {"id_origem": 2, "id_destino": 5, "tipo_origem": "Grupo", "tipo_destino": "Usuario"},
    )

    assert codigo == 423


def test_codigos_bloqueados_separam_core_e_cadastro_corporativo() -> None:
    estado = SimpleNamespace(bancos=SimpleNamespace(core=_banco(valores=[5, 9]), diretorio=_banco(valores=[7])))

    assert seguranca._codigos_bloqueados(estado) == ({5, 9}, {7})  # noqa: SLF001


def test_um_banco_fora_do_ar_nao_apaga_o_bloqueio_do_outro() -> None:
    sem_core = SimpleNamespace(bancos=SimpleNamespace(core=_banco(quebra=True), diretorio=_banco(valores=[7])))
    sem_diretorio = SimpleNamespace(bancos=SimpleNamespace(core=_banco(valores=[5]), diretorio=_banco(quebra=True)))

    assert seguranca._codigos_bloqueados(sem_core) == (set(), {7})  # noqa: SLF001
    assert seguranca._codigos_bloqueados(sem_diretorio) == ({5}, set())  # noqa: SLF001


def test_rota_de_consulta_informa_o_bloqueio_do_cadastro_corporativo(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar(monkeypatch, no_core=False, no_diretorio=True)
    monkeypatch.setattr(seguranca, "consultar_permissoes", lambda _chaves: {})

    codigo, corpo = _chamar(seguranca.consultar_bloqueio_usuario, metodo="GET", codigo_usuario=5)

    assert codigo == 200
    assert corpo["data"]["bloqueado"] is False and corpo["data"]["bloqueado_diretorio"] is True


def test_coluna_do_cadastro_corporativo_so_e_lida_quando_pedida() -> None:
    coluna = UsuarioDiretorio.__table__.c["Usuario_Bloqueado"]

    assert coluna.name == "Usuario_Bloqueado"
    assert UsuarioDiretorio.bloqueado.property.deferred is True  # as demais consultas nao dependem dela


def test_usuario_item_traz_os_bloqueios() -> None:
    livre = seguranca.UsuarioItem(1, "Ana", "ana", None, None)
    do_core = seguranca.UsuarioItem(2, "Bia", "bia", None, None, True)
    do_cadastro = seguranca.UsuarioItem(3, "Cid", "cid", None, None, True, True)

    assert (livre.bloqueado, livre.bloqueado_diretorio) == (False, False)
    assert (do_core.bloqueado, do_core.bloqueado_diretorio) == (True, False)
    assert (do_cadastro.bloqueado, do_cadastro.bloqueado_diretorio) == (True, True)


def test_tela_mostra_tarja_e_trava_a_edicao_da_pessoa_bloqueada() -> None:
    html = TEMPLATE.read_text(encoding="utf-8")

    # Tarja e marcacao na lista lateral
    assert 'class="tarja-bloqueado"' in html and 'data-bloqueado="' in html and 'data-bloqueado-dir="' in html
    assert "bloqueado: {{ 'true' if (user|attr('bloqueado')) else 'false' }}" in html
    # Toda acao que escreve passa pela trava do alvo, nao so pela permissao de editar
    for funcao in ("DefinirRegra", "AbrirModalEspelhar", "LimparTodasRegrasAlvo"):
        trecho = html.split(f"function {funcao}(", 1)[1][:160]
        assert "PodeAlterarAlvo()" in trecho, funcao
    assert "async function ResetarPermissao(idPerm) {\n        if (!PodeAlterarAlvo()) return;" in html
    # O destino do espelhamento nao oferece pessoas bloqueadas
    assert "document.getElementById('buscaDestino')?.value, null, true)" in html
    # A consulta do bloqueio nao pode destravar a tela de quem esta bloqueado so no cadastro corporativo
    assert "const efetivo = BLOQUEADO_ATUAL || !!d.data.bloqueado_diretorio;" in html
    assert "if (!d.data.pode_alterar || soDiretorio) return;" in html
    # O desbloqueio continua disponivel para o bloqueio do core
    assert "{% if PodeBloquear %}" in html and "AlternarBloqueioUsuario()" in html
