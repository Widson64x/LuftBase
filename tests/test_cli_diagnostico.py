"""Testes dos comandos de diagnostico sanitizado."""

from __future__ import annotations

from click.testing import CliRunner
from flask import Flask

from luftbase import PlataformaLuft
from luftbase.cli import cli, registrar_comandos
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.fabrica import (
    FabricaInfraestruturaMemoria,
    RecursosInfraestrutura,
)


class DiretorioFalso:
    somente_leitura = True


class BancosFalsos:
    def __init__(self, bancos_base: object) -> None:
        self.diretorio = bancos_base.diretorio  # type: ignore[attr-defined]
        self.core = bancos_base.core  # type: ignore[attr-defined]
        self.aplicacao = bancos_base.aplicacao  # type: ignore[attr-defined]

    def remover_sessoes_contextuais(self) -> None:
        pass

    def verificar_saude(self) -> tuple[ResultadoSaude, ...]:
        return (
            ResultadoSaude("sqlserver", True, 1.2, "ok"),
            ResultadoSaude("postgresql_core", True, 0.8, "ok"),
        )


class ArmazenamentoFalso:
    def verificar_saude(self) -> bool:
        return True


class FabricaFalsa:
    def criar(self, configuracao, caminhos):  # type: ignore[no-untyped-def]
        base = FabricaInfraestruturaMemoria().criar(configuracao, caminhos)
        return RecursosInfraestrutura(
            bancos=BancosFalsos(base.bancos),  # type: ignore[arg-type]
            armazenamento_sessoes=ArmazenamentoFalso(),  # type: ignore[arg-type]
            chave_assinatura_sessao=Segredo("s" * 64),
            identificador_vault=base.identificador_vault,
        )


def test_diagnostico_configuracao_valida(monkeypatch) -> None:
    monkeypatch.setenv("LUFT_SISTEMA_ID", "9")
    monkeypatch.setenv("LUFT_AMBIENTE", "desenvolvimento")
    monkeypatch.setenv("LUFT_VAULT_ENDERECO", "http://vault:8200")
    monkeypatch.setenv("LUFT_LDAP_SERVIDOR", "ad.luft.interno")
    monkeypatch.setenv("LUFT_LDAP_DOMINIO", "LUFTFARMA")
    monkeypatch.setenv("LUFT_VAULT_TOKEN", "token_protegido_123")
    monkeypatch.setenv("LUFT_TOKEN_ACESSO", "chave_acesso_123")

    runner = CliRunner()
    resultado = runner.invoke(cli, ["diagnostico", "configuracao"])

    assert resultado.exit_code == 0
    assert "status=valida" in resultado.output
    assert "ambiente=desenvolvimento" in resultado.output
    assert "sistema_id=9" in resultado.output
    assert "token_protegido_123" not in resultado.output
    assert "chave_acesso_123" not in resultado.output


def test_diagnostico_configuracao_invalida(monkeypatch) -> None:
    monkeypatch.setenv("LUFT_SISTEMA_ID", "-1")

    runner = CliRunner()
    resultado = runner.invoke(cli, ["diagnostico", "configuracao"])

    assert resultado.exit_code != 0
    assert "status=invalida" in resultado.output


def test_diagnostico_saude_com_aplicacao_flask() -> None:
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=9,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft.interno",
        LUFT_LDAP_DOMINIO="LUFTFARMA",
    )
    PlataformaLuft(FabricaFalsa()).inicializar(app)  # type: ignore[arg-type]
    registrar_comandos(app)

    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["diagnostico", "saude"])

    assert resultado.exit_code == 0
    assert "status_geral=ok" in resultado.output
    assert "sqlserver: status=ok" in resultado.output
    assert "sessoes_redis: status=ok" in resultado.output
