"""Servicos das aplicacoes no host: nome pelo sistema, status, acoes e rotas protegidas."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from luftbase.infraestrutura.servicos_host import (
    ErroServicoHost,
    PlataformaHost,
    ResultadoComando,
    StatusServico,
    consultar_status,
    executar_acao,
    nome_do_servico,
)

LINUX = PlataformaHost.LINUX
WINDOWS = PlataformaHost.WINDOWS


@pytest.mark.parametrize(
    ("nome", "plataforma", "esperado"),
    [
        ("Luft-ConnectAir", LINUX, "luft-connectair.service"),
        ("Luft-Workspace", LINUX, "luft-workspace.service"),
        ("Luft-ConnectAir", WINDOWS, "Luft-ConnectAir"),
        ("Luft-Integrador", WINDOWS, "Luft-Integrador"),
        ("  Luft-Integrador  ", LINUX, "luft-integrador.service"),
    ],
)
def test_nome_do_servico_vem_do_nome_do_sistema(
    nome: str, plataforma: PlataformaHost, esperado: str
) -> None:
    assert nome_do_servico(nome, plataforma) == esperado


@pytest.mark.parametrize(
    "nome",
    ["", "   ", "Luft ConnectAir", "x; rm -rf /", "a&&b", "$(id)", "../etc", "-rf", "a" * 200],
)
def test_nome_inseguro_nao_vira_servico(nome: str) -> None:
    assert nome_do_servico(nome, LINUX) is None
    assert nome_do_servico(nome, WINDOWS) is None


def _executor(resultado: ResultadoComando, chamadas: list[list[str]] | None = None):  # type: ignore[no-untyped-def]
    def executar(argumentos: list[str]) -> ResultadoComando:
        if chamadas is not None:
            chamadas.append(argumentos)
        return resultado

    return executar


@pytest.mark.parametrize(
    ("saida", "esperado"),
    [
        ("LoadState=loaded\nActiveState=active\n", StatusServico.EM_EXECUCAO),
        ("LoadState=loaded\nActiveState=inactive\n", StatusServico.PARADO),
        ("LoadState=loaded\nActiveState=failed\n", StatusServico.PARADO),
        ("LoadState=loaded\nActiveState=activating\n", StatusServico.INICIANDO),
        ("LoadState=not-found\nActiveState=inactive\n", StatusServico.NAO_ENCONTRADO),
        ("lixo", StatusServico.INDISPONIVEL),
    ],
)
def test_status_no_linux(saida: str, esperado: StatusServico) -> None:
    chamadas: list[list[str]] = []

    status = consultar_status(
        "luft-x.service", LINUX, _executor(ResultadoComando(0, saida, ""), chamadas)
    )

    assert status is esperado
    # sem sudo e sem shell: so leitura
    assert chamadas == [
        ["systemctl", "show", "luft-x.service", "-p", "LoadState", "-p", "ActiveState"]
    ]


@pytest.mark.parametrize(
    ("saida", "esperado"),
    [
        ("        STATE              : 4  RUNNING", StatusServico.EM_EXECUCAO),
        ("        STATE              : 1  STOPPED", StatusServico.PARADO),
        ("        STATE              : 2  START_PENDING", StatusServico.INICIANDO),
        ("        ESTADO             : 4  RUNNING", StatusServico.EM_EXECUCAO),  # pt-BR
        ("[SC] OpenService FAILED 1060:", StatusServico.NAO_ENCONTRADO),
    ],
)
def test_status_no_windows(saida: str, esperado: StatusServico) -> None:
    assert (
        consultar_status("Luft-X", WINDOWS, _executor(ResultadoComando(0, saida, ""))) is esperado
    )


def test_status_nunca_levanta_quando_o_comando_falha() -> None:
    falha = _executor(ResultadoComando(127, "", "comando nao encontrado: systemctl"))

    assert consultar_status("luft-x.service", LINUX, falha) is StatusServico.INDISPONIVEL


@pytest.mark.parametrize(
    ("acao", "verbo"), [("iniciar", "start"), ("parar", "stop"), ("reiniciar", "restart")]
)
def test_acao_no_linux_usa_sudo_systemctl_sem_shell(acao: str, verbo: str) -> None:
    chamadas: list[list[str]] = []

    executar_acao("luft-x.service", acao, LINUX, _executor(ResultadoComando(0, "", ""), chamadas))

    assert chamadas == [["sudo", "-n", "systemctl", verbo, "luft-x.service"]]


def test_acao_no_linux_explica_a_falta_de_sudo() -> None:
    sem_sudo = _executor(ResultadoComando(1, "", "sudo: a password is required"))

    with pytest.raises(ErroServicoHost, match="sudo"):
        executar_acao("luft-x.service", "parar", LINUX, sem_sudo)


def test_reiniciar_no_windows_para_espera_e_inicia() -> None:
    chamadas: list[list[str]] = []
    estados = iter(["RUNNING", "STOPPED"])

    def executor(argumentos: list[str]) -> ResultadoComando:
        chamadas.append(argumentos)
        if argumentos[:2] == ["sc", "query"]:
            return ResultadoComando(0, f"STATE : 4 {next(estados)}", "")
        return ResultadoComando(0, "", "")

    executar_acao("Luft-X", "reiniciar", WINDOWS, executor, espera=lambda _s: None)

    verbos = [c[1] for c in chamadas]
    assert verbos[0] == "stop" and verbos[-1] == "start" and "query" in verbos


def test_acao_invalida_ou_nome_invalido_e_recusado_antes_de_executar() -> None:
    chamadas: list[list[str]] = []
    executor = _executor(ResultadoComando(0, "", ""), chamadas)

    with pytest.raises(ErroServicoHost):
        executar_acao("luft-x.service", "apagar", LINUX, executor)
    with pytest.raises(ErroServicoHost):
        executar_acao("x; reboot", "parar", LINUX, executor)

    assert chamadas == []


# ---- Rotas ---------------------------------------------------------------------------------


def _app(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    from flask import Flask

    from luftbase import PermissaoLuftBase
    from luftbase.configuracao import ConfiguracaoLuftBase
    from luftbase.identidade import UsuarioAutenticado
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
    from luftbase.plataforma import PlataformaLuft
    from luftbase.web import configuracoes as modulo

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
    estado.autorizacao.possui = lambda _u, chave, *_: (
        chave
        in {
            PermissaoLuftBase.SERVICOS_VISUALIZAR,
            PermissaoLuftBase.SERVICOS_EXECUTAR,
        }
    )
    estado.auditoria.registrar_alteracao = MagicMock()  # type: ignore[method-assign]
    sistemas = [
        SimpleNamespace(id_sistema=0, nome_sistema="Luft-Workspace", descricao_sistema="Hub"),
        SimpleNamespace(id_sistema=1, nome_sistema="Luft-ConnectAir", descricao_sistema="Air"),
        SimpleNamespace(id_sistema=3, nome_sistema="Luft x", descricao_sistema=None),
    ]
    monkeypatch.setattr(modulo, "_sistemas_com_servico", lambda: sistemas)
    monkeypatch.setattr(modulo, "plataforma_do_host", lambda: LINUX)
    monkeypatch.setattr(modulo, "consultar_status", lambda nome, _p: StatusServico.EM_EXECUCAO)
    cliente = app.test_client()
    usuario = UsuarioAutenticado(
        id_usuario=10,
        login="op",
        nome_completo="Op",
        email="op@luft.com.br",
        id_grupo=1,
        nome_grupo="TI",
    )
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
        sessao["luftbase_csrf"] = "c" * 32
        sessao["luftbase_preferencia_tema"] = {"tema": "luft", "modo": "SISTEMA"}
    return cliente, estado, modulo


_URL = "/configuracoes/api/configuracoes/ambiente/servicos"
_CSRF = {"X-CSRF-Token": "c" * 32}


def test_get_devolve_o_servico_de_cada_sistema_pelo_nome(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, _, _ = _app(monkeypatch)

    resposta = cliente.get(_URL)

    assert resposta.status_code == 200
    servicos = {s["idServico"]: s for s in resposta.get_json()["data"]["servicos"]}
    assert servicos["1"]["nomeServico"] == "luft-connectair.service"
    assert servicos["1"]["status"] == "RUNNING"
    assert servicos["0"]["protegido"] is True  # o Hub (e a propria aplicacao) so se monitoram
    assert servicos["1"]["protegido"] is False
    assert servicos["3"]["nomeServico"] is None  # nome com espaco: nao e um servico valido
    assert servicos["3"]["status"] == "UNAVAILABLE"


def test_post_executa_so_em_servico_cadastrado_e_nao_protegido(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cliente, estado, modulo = _app(monkeypatch)
    executadas: list[tuple[str, str]] = []
    monkeypatch.setattr(
        modulo, "executar_acao", lambda nome, acao, _p: executadas.append((nome, acao))
    )

    ok = cliente.post(_URL + "/acao", json={"idServico": "1", "acao": "reiniciar"}, headers=_CSRF)
    protegido = cliente.post(
        _URL + "/acao", json={"idServico": "0", "acao": "parar"}, headers=_CSRF
    )
    desconhecido = cliente.post(
        _URL + "/acao", json={"idServico": "99", "acao": "parar"}, headers=_CSRF
    )
    nome_livre = cliente.post(
        _URL + "/acao", json={"idServico": "sshd", "acao": "parar"}, headers=_CSRF
    )
    acao_ruim = cliente.post(
        _URL + "/acao", json={"idServico": "1", "acao": "apagar"}, headers=_CSRF
    )

    assert ok.status_code == 200 and executadas == [("luft-connectair.service", "reiniciar")]
    assert protegido.status_code == 403
    assert desconhecido.status_code == 404 and nome_livre.status_code == 404
    assert acao_ruim.status_code == 400
    assert len(executadas) == 1
    assert estado.auditoria.registrar_alteracao.call_count == 1


def test_post_exige_csrf_e_permissao(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase import PermissaoLuftBase

    cliente, estado, modulo = _app(monkeypatch)
    monkeypatch.setattr(modulo, "executar_acao", lambda *_a: pytest.fail("nao deveria executar"))

    sem_csrf = cliente.post(_URL + "/acao", json={"idServico": "1", "acao": "parar"})
    estado.autorizacao.possui = lambda _u, chave, *_: chave == PermissaoLuftBase.SERVICOS_VISUALIZAR
    sem_permissao = cliente.post(
        _URL + "/acao", json={"idServico": "1", "acao": "parar"}, headers=_CSRF
    )

    assert sem_csrf.status_code == 403
    assert sem_permissao.status_code == 403


def test_post_devolve_502_e_audita_quando_o_host_recusa(monkeypatch: pytest.MonkeyPatch) -> None:
    cliente, estado, modulo = _app(monkeypatch)

    def recusar(*_a: object) -> None:
        raise ErroServicoHost("sem sudo")

    monkeypatch.setattr(modulo, "executar_acao", recusar)

    resposta = cliente.post(_URL + "/acao", json={"idServico": "1", "acao": "parar"}, headers=_CSRF)

    assert resposta.status_code == 502
    assert resposta.get_json()["message"] == "sem sudo"
    assert estado.auditoria.registrar_alteracao.call_args.kwargs["acao"] == "FALHA_PARAR_SERVICO"
