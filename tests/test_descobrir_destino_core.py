"""Descoberta do banco do ambiente no Vault pela CLI, com e sem o segredo do sistema de referencia."""

from __future__ import annotations

from typing import Any

import click
import pytest

from luftbase.cli.operador import pedir_banco_do_ambiente
from luftbase.infraestrutura.cadastro_sistema import ErroCadastroSistema, descobrir_destino_core
from luftbase.infraestrutura.provisionamento_sistema import (
    CredenciaisOperador,
    DestinoProvisionamento,
    ProvisionadorSistema,
)

RAIZ = "luft/desenvolvimento/bancos/postgresql"
CONEXAO = {"host": "172.19.85.111", "porta": "5432", "nome_banco": "luft_web"}


class InvalidPath(Exception):
    pass


class Kv2Falso:
    def __init__(self, segredos: dict[str, dict[str, Any]]) -> None:
        self.segredos = segredos

    def read_secret_version(self, path: str, mount_point: str, **_: object) -> dict[str, Any]:
        if path not in self.segredos:
            raise InvalidPath(path)
        return {"data": {"data": self.segredos[path]}}

    def list_secrets(self, path: str, mount_point: str) -> dict[str, Any]:
        prefixo = path.rstrip("/") + "/"
        chaves = [c[len(prefixo) :] for c in self.segredos if c.startswith(prefixo)]
        if not chaves:
            raise InvalidPath(path)
        return {"data": {"keys": chaves}}


def _vault(segredos: dict[str, dict[str, Any]]) -> Any:
    kv2 = Kv2Falso(segredos)
    return type("V", (), {"secrets": type("S", (), {"kv": type("K", (), {"v2": kv2})()})()})()


def _descobrir(segredos: dict[str, dict[str, Any]]) -> DestinoProvisionamento:
    return descobrir_destino_core(
        _vault(segredos),
        ambiente="desenvolvimento",
        namespace="luft",
        vault_url="http://v:8200",
    )


def test_usa_o_alias_do_sistema_de_referencia() -> None:
    destino = _descobrir(
        {f"{RAIZ}/sistemas/0": {"conexao": "luft-web"}, f"{RAIZ}/conexoes/luft-web": CONEXAO}
    )

    assert (destino.host, destino.porta, destino.banco) == ("172.19.85.111", 5432, "luft_web")
    assert destino.alias_conexao == "luft-web"


def test_sem_o_sistema_de_referencia_usa_a_unica_conexao_do_ambiente() -> None:
    destino = _descobrir({f"{RAIZ}/conexoes/luft-web": CONEXAO})

    assert destino.banco == "luft_web"
    assert destino.alias_conexao == "luft-web"


def test_alias_descoberto_dispensa_ler_o_segredo_do_sistema() -> None:
    destino = _descobrir({f"{RAIZ}/conexoes/luft-web": CONEXAO})
    provisionador = ProvisionadorSistema(
        destino,
        CredenciaisOperador("admin", "t", "s"),  # type: ignore[arg-type]
        criar_cliente_vault=lambda *_: _vault({}),
    )

    assert provisionador.alias_conexao() == "luft-web"


def test_varias_conexoes_sem_referencia_nao_adivinha() -> None:
    with pytest.raises(ErroCadastroSistema, match="nao ha como escolher"):
        _descobrir({f"{RAIZ}/conexoes/a": CONEXAO, f"{RAIZ}/conexoes/b": CONEXAO})


def test_erro_diz_o_caminho_e_o_tipo_sem_vazar_segredo() -> None:
    with pytest.raises(ErroCadastroSistema) as erro:
        _descobrir({})

    texto = erro.value.mensagem
    assert RAIZ in texto and "InvalidPath" in texto and "--banco-host" in texto


def test_cli_converte_a_falha_em_mensagem_sem_traceback() -> None:
    with pytest.raises(click.ClickException, match="Nao foi possivel descobrir"):
        pedir_banco_do_ambiente(
            _vault({}),
            ambiente="desenvolvimento",
            vault_url="http://v:8200",
            vault_mount="secret",
            namespace="luft",
            usuario="admin",
        )


# --- Core desatualizado e prompt de senha -------------------------------------------------


def _engine_core(revisao: str | None) -> Any:
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as conexao:
        conexao.execute(text("ATTACH DATABASE ':memory:' AS core"))
        conexao.execute(text("CREATE TABLE core.alembic_version (version_num VARCHAR(32))"))
        if revisao:
            conexao.execute(text(f"INSERT INTO core.alembic_version VALUES ('{revisao}')"))
    return engine


def test_core_em_revisao_antiga_orienta_atualizar_core() -> None:
    from luftbase.infraestrutura.cadastro_sistema import exigir_core_atualizado

    with pytest.raises(ErroCadastroSistema, match="atualizar-core") as erro:
        exigir_core_atualizado(_engine_core("20261008_0015"), cabeca="20261015_0016")

    assert "20261008_0015" in erro.value.mensagem and "20261015_0016" in erro.value.mensagem


def test_core_na_revisao_certa_passa() -> None:
    from luftbase.infraestrutura.cadastro_sistema import exigir_core_atualizado

    exigir_core_atualizado(_engine_core("20261015_0016"), cabeca="20261015_0016")


def test_core_sem_tabela_de_versao_diz_o_que_fazer() -> None:
    from sqlalchemy import create_engine

    from luftbase.infraestrutura.cadastro_sistema import exigir_core_atualizado

    with pytest.raises(ErroCadastroSistema, match="core.alembic_version"):
        exigir_core_atualizado(create_engine("sqlite+pysqlite:///:memory:"), cabeca="x")


@pytest.mark.parametrize(
    ("ambiente", "tem_dica"), [("desenvolvimento", False), ("homologacao", True)]
)
def test_dica_de_senha_so_aparece_fora_do_desenvolvimento(
    monkeypatch: pytest.MonkeyPatch, ambiente: str, tem_dica: bool
) -> None:
    from luftbase.cli import operador
    from luftbase.infraestrutura.cofre.credenciais import Segredo

    pedidos: list[str] = []
    monkeypatch.setattr(
        operador, "_solicitar_segredo", lambda rotulo: pedidos.append(rotulo) or "x"
    )
    kv = {f"luft/{ambiente}/bancos/postgresql/conexoes/c": CONEXAO}

    pedir = operador.pedir_banco_do_ambiente
    destino, login, senha = pedir(
        _vault(kv),
        ambiente=ambiente,
        vault_url="http://v",
        vault_mount="secret",
        namespace="luft",
        usuario="admin",
    )

    assert isinstance(senha, Segredo) and login == "admin" and destino.banco == "luft_web"
    assert ("nao a do PostgreSQL local" in pedidos[-1]) is tem_dica


# --- banco atualizar-core -----------------------------------------------------------------


def _preparar_atualizar_core(monkeypatch: pytest.MonkeyPatch, engine: Any) -> list[str]:
    import sys

    from luftbase.cli import operador
    from luftbase.infraestrutura.cofre.credenciais import Segredo

    modulo_banco = sys.modules["luftbase.cli.banco"]
    destino = DestinoProvisionamento(
        "desenvolvimento", "luft", "http://v", "h", 5432, "luft_web_dev", 0
    )
    monkeypatch.setattr(operador, "abrir_cliente_vault", lambda **_: object())
    monkeypatch.setattr(
        operador, "pedir_banco_do_ambiente", lambda *_a, **_k: (destino, "dono", Segredo("s"))
    )
    monkeypatch.setattr(operador, "engine_do_operador", lambda *_a: engine)
    chamadas: list[str] = []
    monkeypatch.setattr(modulo_banco.command, "upgrade", lambda _cfg, alvo: chamadas.append(alvo))
    monkeypatch.setattr(
        modulo_banco, "sincronizar_catalogo_workspace", lambda _c: chamadas.append("catalogo")
    )
    return chamadas


def test_atualizar_core_sem_pendencia_nao_faz_nada(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from luftbase.cli import cli
    from luftbase.infraestrutura.cadastro_sistema import revisao_cabeca

    chamadas = _preparar_atualizar_core(monkeypatch, _engine_core(revisao_cabeca()))

    resultado = CliRunner().invoke(cli, ["banco", "atualizar-core"])

    assert resultado.exit_code == 0, resultado.output
    assert "atualizacao=nada_a_fazer" in resultado.output
    assert chamadas == []


def test_atualizar_core_antigo_aplica_head_e_sincroniza_o_catalogo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from click.testing import CliRunner

    from luftbase.cli import cli

    chamadas = _preparar_atualizar_core(monkeypatch, _engine_core("20261008_0015"))

    resultado = CliRunner().invoke(cli, ["banco", "atualizar-core", "--sim"])

    assert resultado.exit_code == 0, resultado.output
    assert "revisao_atual=20261008_0015" in resultado.output
    assert "atualizacao=concluida" in resultado.output
    assert chamadas == ["head", "catalogo"]


def test_atualizar_core_so_aceita_desenvolvimento() -> None:
    from click.testing import CliRunner

    from luftbase.cli import cli

    resultado = CliRunner().invoke(cli, ["banco", "atualizar-core", "--ambiente", "homologacao"])

    assert resultado.exit_code != 0
