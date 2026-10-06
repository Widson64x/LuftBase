"""Variaveis do .env na tela de Ambiente: so as nao sensiveis, validadas e sem vazar o resto."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from luftbase.infraestrutura.variaveis_ambiente import (
    PERMITIDAS,
    ErroVariavel,
    gravar_variavel,
    ler_variaveis,
)

ENV = """# Luft-Teste
LUFT_SISTEMA_ID=3
LUFT_VAULT_TOKEN=gAAAA-token-protegido
LUFT_TOKEN_ACESSO=chave-de-acesso-secreta
LUFT_SESSAO_TTL_MINUTOS=30   # minutos
# LUFT_LDAP_TIMEOUT_SEGUNDOS=5
HOST=127.0.0.1
"""


def _env(tmp_path: Path, texto: str = ENV, quebra: str = "\n") -> Path:
    caminho = tmp_path / ".env"
    caminho.write_bytes(texto.replace("\n", quebra).encode("utf-8"))
    return caminho


def test_so_as_chaves_permitidas_saem_e_nenhum_segredo_vaza(tmp_path: Path) -> None:
    variaveis = ler_variaveis(_env(tmp_path))

    chaves = {v["chave"] for v in variaveis}
    assert chaves == {p.chave for p in PERMITIDAS}
    texto = str(variaveis)
    for segredo in ("gAAAA-token-protegido", "chave-de-acesso-secreta", "LUFT_VAULT_TOKEN", "HOST"):
        assert segredo not in texto
    ttl = next(v for v in variaveis if v["chave"] == "LUFT_SESSAO_TTL_MINUTOS")
    assert ttl["valor"] == "30"  # comentario inline nao faz parte do valor
    ausente = next(v for v in variaveis if v["chave"] == "EMAIL_LINK_VALIDADE_DIAS")
    assert ausente["valor"] == ""


def test_gravar_preserva_comentarios_ordem_e_faz_backup(tmp_path: Path) -> None:
    arquivo = _env(tmp_path)

    anterior, novo = gravar_variavel(arquivo, "LUFT_SESSAO_TTL_MINUTOS", "45")

    assert (anterior, novo) == ("30", "45")
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    assert linhas[0] == "# Luft-Teste"
    assert "LUFT_VAULT_TOKEN=gAAAA-token-protegido" in linhas  # o resto fica intacto
    assert linhas.index("LUFT_SESSAO_TTL_MINUTOS=45") == 4
    assert (tmp_path / ".env.bak").read_text(encoding="utf-8") == ENV
    assert not (tmp_path / ".env.tmp").exists()


def test_gravar_descomenta_a_linha_modelo_ou_acrescenta_no_fim(tmp_path: Path) -> None:
    arquivo = _env(tmp_path)

    gravar_variavel(arquivo, "LUFT_LDAP_TIMEOUT_SEGUNDOS", "10")
    gravar_variavel(arquivo, "EMAIL_LINK_VALIDADE_DIAS", "14")

    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    assert "# LUFT_LDAP_TIMEOUT_SEGUNDOS=5" not in linhas
    assert linhas.index("LUFT_LDAP_TIMEOUT_SEGUNDOS=10") == 5  # no lugar do comentario
    assert linhas[-1] == "EMAIL_LINK_VALIDADE_DIAS=14"


def test_gravar_mantem_a_quebra_de_linha_do_arquivo(tmp_path: Path) -> None:
    arquivo = _env(tmp_path, quebra="\r\n")

    gravar_variavel(arquivo, "LUFT_SESSAO_TTL_MINUTOS", "60")

    bruto = arquivo.read_bytes()
    assert b"\r\n" in bruto and b"\n" not in bruto.replace(b"\r\n", b"")


@pytest.mark.parametrize(
    ("chave", "valor"),
    [
        ("LUFT_SESSAO_TTL_MINUTOS", "0"),
        ("LUFT_SESSAO_TTL_MINUTOS", "999999"),
        ("LUFT_SESSAO_TTL_MINUTOS", "abc"),
        ("LUFT_SESSAO_TTL_MINUTOS", "30\nLUFT_VAULT_TOKEN=roubado"),  # injecao de linha
        ("LUFT_SESSAO_TTL_MINUTOS", "30 # x"),
        ("SQLSERVER_NEGOCIO_AMBIENTE", "outro"),
        ("LUFT_VAULT_TOKEN", "x"),  # fora da lista
        ("LUFT_AMBIENTE", "producao"),
        ("HOST", "0.0.0.0"),
        ("", "1"),
    ],
)
def test_valor_invalido_ou_chave_fora_da_lista_nao_toca_no_arquivo(
    tmp_path: Path, chave: str, valor: str
) -> None:
    arquivo = _env(tmp_path)

    with pytest.raises(ErroVariavel):
        gravar_variavel(arquivo, chave, valor)

    assert arquivo.read_text(encoding="utf-8") == ENV
    assert not (tmp_path / ".env.bak").exists()


def test_enum_normaliza_maiusculas(tmp_path: Path) -> None:
    arquivo = _env(tmp_path)

    gravar_variavel(arquivo, "SQLSERVER_NEGOCIO_AMBIENTE", "  Producao ")

    assert "SQLSERVER_NEGOCIO_AMBIENTE=producao" in arquivo.read_text(encoding="utf-8")


# ---- Rotas ---------------------------------------------------------------------------------

_URL = "/configuracoes/api/configuracoes/ambiente/variaveis"
_CSRF = {"X-CSRF-Token": "c" * 32}


def _app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):  # type: ignore[no-untyped-def]
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
            PermissaoLuftBase.VARIAVEIS_VISUALIZAR,
            PermissaoLuftBase.VARIAVEIS_EDITAR,
        }
    )
    estado.auditoria.registrar_alteracao = MagicMock()  # type: ignore[method-assign]

    envs = {}
    for id_sistema, nome in ((0, "Luft-Workspace"), (1, "Luft-ConnectAir")):
        pasta = tmp_path / nome
        pasta.mkdir()
        envs[id_sistema] = _env(pasta)
    sistemas = [
        SimpleNamespace(id_sistema=0, nome_sistema="Luft-Workspace"),
        SimpleNamespace(id_sistema=1, nome_sistema="Luft-ConnectAir"),
        SimpleNamespace(id_sistema=9, nome_sistema="../../etc"),
    ]
    monkeypatch.setattr(modulo, "_sistemas_com_servico", lambda: sistemas)
    monkeypatch.setattr(modulo, "plataforma_do_host", lambda: modulo.PlataformaHost.LINUX)
    monkeypatch.setattr(modulo, "_arquivo_env", lambda s: envs.get(s.id_sistema))

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
    return cliente, estado, envs


def test_get_lista_so_as_variaveis_permitidas_do_projeto(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cliente, _, _ = _app(monkeypatch, tmp_path)

    resposta = cliente.get(_URL + "?idProjeto=1")

    assert resposta.status_code == 200
    texto = resposta.get_data(as_text=True)
    assert "LUFT_SESSAO_TTL_MINUTOS" in texto
    assert "gAAAA-token-protegido" not in texto and "LUFT_VAULT_TOKEN" not in texto
    assert cliente.get(_URL + "?idProjeto=99").status_code == 404
    assert cliente.get(_URL + "?idProjeto=9").status_code == 404  # nome inseguro/sem .env
    assert cliente.get(_URL + "?idProjeto=../../etc").status_code == 404


def test_post_grava_audita_e_avisa_do_reinicio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cliente, estado, envs = _app(monkeypatch, tmp_path)

    resposta = cliente.post(
        _URL + "/salvar",
        json={"idProjeto": "1", "chave": "LUFT_SESSAO_TTL_MINUTOS", "valor": "50"},
        headers=_CSRF,
    )

    assert resposta.status_code == 200
    assert "luft-connectair.service" in resposta.get_json()["message"]
    assert "LUFT_SESSAO_TTL_MINUTOS=50" in envs[1].read_text(encoding="utf-8")
    assert "LUFT_SESSAO_TTL_MINUTOS=30" in envs[0].read_text(encoding="utf-8")  # outro projeto
    chamada = estado.auditoria.registrar_alteracao.call_args.kwargs
    assert chamada["dados_anteriores"] == {"LUFT_SESSAO_TTL_MINUTOS": "30"}
    assert chamada["dados_novos"] == {"LUFT_SESSAO_TTL_MINUTOS": "50"}


def test_post_recusa_chave_sensivel_valor_ruim_csrf_e_falta_de_permissao(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from luftbase import PermissaoLuftBase

    cliente, estado, envs = _app(monkeypatch, tmp_path)
    original = envs[1].read_text(encoding="utf-8")

    sensivel = cliente.post(
        _URL + "/salvar",
        json={"idProjeto": "1", "chave": "LUFT_VAULT_TOKEN", "valor": "x"},
        headers=_CSRF,
    )
    ruim = cliente.post(
        _URL + "/salvar",
        json={"idProjeto": "1", "chave": "LUFT_SESSAO_TTL_MINUTOS", "valor": "-1"},
        headers=_CSRF,
    )
    sem_csrf = cliente.post(
        _URL + "/salvar",
        json={"idProjeto": "1", "chave": "LUFT_SESSAO_TTL_MINUTOS", "valor": "50"},
    )
    estado.autorizacao.possui = lambda _u, chave, *_: (
        chave == PermissaoLuftBase.VARIAVEIS_VISUALIZAR
    )
    sem_permissao = cliente.post(
        _URL + "/salvar",
        json={"idProjeto": "1", "chave": "LUFT_SESSAO_TTL_MINUTOS", "valor": "50"},
        headers=_CSRF,
    )

    assert sensivel.status_code == 400 and ruim.status_code == 400
    assert sem_csrf.status_code == 403 and sem_permissao.status_code == 403
    assert envs[1].read_text(encoding="utf-8") == original


def test_arquivo_env_resolve_pasta_irma_pelo_nome_do_sistema(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from flask import Flask

    from luftbase.web import configuracoes as modulo

    (tmp_path / "Luft-Workspace" / "App").mkdir(parents=True)
    (tmp_path / "Luft-Workspace" / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / "Luft-ConnectAir").mkdir()
    (tmp_path / "Luft-ConnectAir" / ".env").write_text("A=1\n", encoding="utf-8")
    (tmp_path / "Luft-Integrador").mkdir()  # sem .env
    app = Flask("x", root_path=str(tmp_path / "Luft-Workspace" / "App"))
    monkeypatch.setattr(modulo, "sistema_aplicacao_atual", lambda: 0)

    def achado(nome: str, ident: int) -> Path | None:
        return modulo._arquivo_env(SimpleNamespace(id_sistema=ident, nome_sistema=nome))

    with app.test_request_context():
        assert achado("Luft-Workspace", 0) == tmp_path / "Luft-Workspace" / ".env"
        assert achado("Luft-ConnectAir", 1) == tmp_path / "Luft-ConnectAir" / ".env"
        assert achado("Luft-Integrador", 3) is None
        assert achado("../Luft-ConnectAir", 5) is None
        assert achado("a/b", 6) is None
