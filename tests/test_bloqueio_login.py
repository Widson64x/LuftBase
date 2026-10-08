"""Bloqueio de login (fail-closed) e aviso de sessao encerrada por um administrador."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from core_sqlite import motor_sqlite
from flask import Flask
from sqlalchemy import insert, select

from luftbase import PlataformaLuft
from luftbase.identidade.modelos import UsuarioAutenticado
from luftbase.identidade.repositorio_core import RepositorioUsuariosPostgreSQL
from luftbase.identidade.servico import ServicoAutenticacao
from luftbase.identidade.sessoes import (
    CHAVE_AVISO_ENCERRAMENTO,
    InterfaceSessaoCompartilhada,
)
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.nucleo.excecoes import ErroAutenticacao, ErroUsuarioBloqueado
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.usuario import Usuario
from luftbase.web import seguranca


def _usuario() -> UsuarioAutenticado:
    return UsuarioAutenticado(
        id_usuario=5,
        login="ana",
        nome_completo="Ana",
        email="ana@luft.com",
        id_grupo=7,
        nome_grupo="TI",
    )


class _Senha:
    def autenticar(self, login: str, senha: str) -> bool:
        return senha == "ok"


class _Diretorio:
    def obter_por_login(self, identificador: str) -> UsuarioAutenticado | None:
        return _usuario()


class _Core:
    """Substitui o repositorio do core; `bloqueado` pode ser um valor ou uma excecao."""

    def __init__(self, bloqueado: bool | Exception) -> None:
        self._bloqueado = bloqueado
        self.sincronizados = 0

    def esta_bloqueado(self, codigo: int) -> bool:
        if isinstance(self._bloqueado, Exception):
            raise self._bloqueado
        return self._bloqueado

    def garantir_usuario_do_diretorio(self, **_: Any) -> Any:
        self.sincronizados += 1
        return SimpleNamespace(
            nome_usuario="Ana",
            foto_perfil=None,
            cargo_usuario=None,
            departamento_usuario=None,
            telefone_usuario=None,
            celular_usuario=None,
            unidade_filial=None,
            tema_preferido="luft",
            modo_tema="SISTEMA",
            idioma="pt-BR",
        )


def _servico(core: _Core) -> ServicoAutenticacao:
    return ServicoAutenticacao(_Senha(), _Diretorio(), core)  # type: ignore[arg-type]


def test_usuario_bloqueado_com_senha_correta_nao_entra() -> None:
    core = _Core(True)

    with pytest.raises(ErroUsuarioBloqueado):
        _servico(core).autenticar("ana", "ok")

    assert core.sincronizados == 0  # nem chega a atualizar o cadastro


def test_usuario_liberado_entra() -> None:
    assert _servico(_Core(False)).autenticar("ana", "ok") is not None


def test_senha_errada_continua_sendo_credencial_invalida_e_nao_revela_bloqueio() -> None:
    assert _servico(_Core(True)).autenticar("ana", "errada") is None


def test_falha_ao_conferir_o_bloqueio_nega_o_acesso() -> None:
    with pytest.raises(ErroAutenticacao):
        _servico(_Core(RuntimeError("banco caiu"))).autenticar("ana", "ok")


def _repositorio() -> tuple[RepositorioUsuariosPostgreSQL, BancoSQLAlchemy]:
    banco = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))
    with banco.unidade_trabalho() as s:
        s.execute(
            insert(Usuario).values(
                codigo_usuario=5,
                login_usuario="ana",
                nome_usuario="Ana",
                ativo=True,
                bloqueado=False,
                status_online=False,
            )
        )
    return RepositorioUsuariosPostgreSQL(banco), banco


def test_repositorio_bloqueia_e_desbloqueia() -> None:
    repositorio, banco = _repositorio()

    assert repositorio.esta_bloqueado(5) is False
    assert repositorio.definir_bloqueio(5, True, "  desligamento em curso  ") is True
    assert repositorio.esta_bloqueado(5) is True
    with banco.leitura() as s:
        assert s.execute(select(Usuario.motivo_bloqueio)).scalar_one() == "desligamento em curso"

    assert repositorio.definir_bloqueio(5, False) is True
    assert repositorio.esta_bloqueado(5) is False
    with banco.leitura() as s:
        assert s.execute(select(Usuario.motivo_bloqueio)).scalar_one() is None


def test_repositorio_usuario_inexistente() -> None:
    repositorio, _ = _repositorio()

    assert repositorio.definir_bloqueio(999, True, "x") is False
    assert repositorio.esta_bloqueado(999) is False


def _app() -> tuple[Flask, Any]:
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)
    return app, estado


def test_tela_de_login_responde_403_para_usuario_bloqueado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, estado = _app()

    def bloqueado(_servico: Any, _login: str, _senha: str) -> None:
        raise ErroUsuarioBloqueado("bloqueado")

    monkeypatch.setattr(type(estado.autenticacao), "autenticar", bloqueado)
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao["luftbase_csrf"] = "t"

    resposta = cliente.post("/login", data={"login": "ana", "senha": "ok", "csrf_token": "t"})

    texto = resposta.get_data(as_text=True)
    assert resposta.status_code == 403
    assert "Seu acesso está bloqueado" in texto
    assert "desligamento" not in texto  # o motivo interno nunca aparece


def test_login_mostra_aviso_de_sessao_encerrada_uma_unica_vez() -> None:
    app, _ = _app()
    cliente = app.test_client()
    with cliente.session_transaction() as sessao:
        sessao[CHAVE_AVISO_ENCERRAMENTO] = "REVOGADA_ADMIN"

    primeira = cliente.get("/login").get_data(as_text=True)
    segunda = cliente.get("/login").get_data(as_text=True)

    assert "encerrada por um administrador" in primeira
    assert "encerrada por um administrador" not in segunda


class _Armazenamento:
    def __init__(self, motivo: str | None, falhar: bool = False) -> None:
        self.motivo = motivo
        self.falhar = falhar

    def obter(self, chave: str) -> bytes | None:
        return None  # sessao nao esta mais ativa

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None: ...

    def remover(self, chave: str) -> None: ...

    def verificar_saude(self) -> bool:
        return True

    def motivo_encerramento(self, chave: str) -> str | None:
        if self.falhar:
            raise RuntimeError("banco")
        return self.motivo


def _abrir_sessao(armazenamento: _Armazenamento) -> Any:
    app = Flask(__name__)
    interface = InterfaceSessaoCompartilhada(armazenamento, "k" * 40)  # type: ignore[arg-type]
    cookie = interface._assinar("sessao-derrubada")  # noqa: SLF001
    with app.test_request_context(headers={"Cookie": f"session={cookie}"}):
        from flask import request

        return interface.open_session(app, request)


@pytest.mark.parametrize("motivo", ["REVOGADA_ADMIN", "BLOQUEIO_ADMIN"])
def test_sessao_derrubada_por_admin_gera_aviso(motivo: str) -> None:
    assert _abrir_sessao(_Armazenamento(motivo)).get(CHAVE_AVISO_ENCERRAMENTO) == motivo


@pytest.mark.parametrize("motivo", [None, "LOGOUT_VOLUNTARIO", "TIMEOUT_INATIVIDADE"])
def test_outros_motivos_nao_geram_aviso(motivo: str | None) -> None:
    assert CHAVE_AVISO_ENCERRAMENTO not in _abrir_sessao(_Armazenamento(motivo))


def test_falha_ao_consultar_o_motivo_nao_quebra_a_requisicao() -> None:
    assert CHAVE_AVISO_ENCERRAMENTO not in _abrir_sessao(_Armazenamento("x", falhar=True))


class _RepoBloqueio:
    def __init__(self) -> None:
        self.bloqueado = False
        self.motivo: str | None = None
        self.sessoes = [{"id_sessao": "s1"}, {"id_sessao": "s2"}]

    def esta_bloqueado(self, codigo: int) -> bool:
        return self.bloqueado

    def definir_bloqueio(self, codigo: int, bloqueado: bool, motivo: str | None = None) -> bool:
        self.bloqueado, self.motivo = bloqueado, motivo
        return True

    def listar_sessoes_usuario(self, codigo: int) -> list[dict[str, str]]:
        return self.sessoes


def _preparar_rota(monkeypatch: pytest.MonkeyPatch, usuario_logado: int | None = 1) -> tuple[Any, list[Any]]:
    revogadas: list[Any] = []
    repo = _RepoBloqueio()
    armazenamento = SimpleNamespace(
        revogar_sessao=lambda sid, motivo: revogadas.append((sid, motivo)) or True
    )
    estado = SimpleNamespace(
        usuarios_core=repo,
        infraestrutura=SimpleNamespace(armazenamento_sessoes=armazenamento),
        autorizacao=SimpleNamespace(invalidar_cache=lambda: None),
    )
    auditados: list[Any] = []
    monkeypatch.setattr(seguranca, "obter_luftbase", lambda: estado)
    monkeypatch.setattr(seguranca, "validar_csrf_requisicao", lambda: None)
    monkeypatch.setattr(seguranca, "garantir_usuario_no_core", lambda _c: True)
    monkeypatch.setattr(
        seguranca, "registrar_alteracao_auditoria", lambda **k: auditados.append(k) or 1
    )
    monkeypatch.setattr(
        seguranca, "current_user", SimpleNamespace(id_usuario=usuario_logado)
    )
    repo.auditados = auditados  # type: ignore[attr-defined]
    repo.revogadas = revogadas  # type: ignore[attr-defined]
    return repo, revogadas


def _chamar(bloquear: bool, corpo: dict[str, Any]) -> Any:
    app = Flask(__name__)
    with app.test_request_context(method="POST", json=corpo):
        resposta = seguranca._alterar_bloqueio(bloquear)  # noqa: SLF001
    corpo_resposta, codigo = resposta if isinstance(resposta, tuple) else (resposta, 200)
    return codigo, corpo_resposta.get_json()


def test_rota_bloquear_derruba_as_sessoes_e_audita(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, revogadas = _preparar_rota(monkeypatch)

    codigo, corpo = _chamar(True, {"IdUsuario": 5, "Motivo": "desligamento"})

    assert codigo == 200 and corpo["sessoes_encerradas"] == 2
    assert repo.bloqueado is True and repo.motivo == "desligamento"
    assert revogadas == [("s1", "BLOQUEIO_ADMIN"), ("s2", "BLOQUEIO_ADMIN")]
    assert repo.auditados[0]["acao"] == "USUARIO_BLOQUEADO"  # type: ignore[attr-defined]


def test_rota_bloquear_exige_motivo(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _preparar_rota(monkeypatch)

    codigo, _ = _chamar(True, {"IdUsuario": 5, "Motivo": "  "})

    assert codigo == 400 and repo.bloqueado is False


def test_rota_nao_deixa_bloquear_a_si_mesmo(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, _ = _preparar_rota(monkeypatch, usuario_logado=5)

    codigo, _ = _chamar(True, {"IdUsuario": 5, "Motivo": "teste de bloqueio"})

    assert codigo == 400 and repo.bloqueado is False


def test_rota_desbloquear_devolve_o_acesso(monkeypatch: pytest.MonkeyPatch) -> None:
    repo, revogadas = _preparar_rota(monkeypatch)
    repo.bloqueado = True

    codigo, corpo = _chamar(False, {"IdUsuario": 5})

    assert codigo == 200 and repo.bloqueado is False
    assert revogadas == []
    assert repo.auditados[0]["acao"] == "USUARIO_DESBLOQUEADO"  # type: ignore[attr-defined]


def test_rota_rejeita_usuario_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar_rota(monkeypatch)

    assert _chamar(True, {"IdUsuario": "abc", "Motivo": "motivo valido"})[0] == 400
    assert _chamar(True, {"Motivo": "motivo valido"})[0] == 400


def test_novas_rotas_exigem_a_permissao_de_bloqueio() -> None:
    from pathlib import Path

    codigo = Path(seguranca.__file__).read_text(encoding="utf-8")
    for nome in ("def bloquear_usuario", "def desbloquear_usuario"):
        cabecalho = codigo[codigo.rindex("@SegurancaBp", 0, codigo.index(nome)) : codigo.index(nome)]
        assert "exigir_permissao(PermissaoLuftBase.USUARIOS_DESATIVAR)" in cabecalho
        assert "@login_required" in cabecalho
