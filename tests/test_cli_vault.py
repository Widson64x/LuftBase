"""Testes dos comandos de inspecao do Vault."""

from __future__ import annotations

import sys

import hvac
from click.testing import CliRunner

from luftbase.cli import cli
from luftbase.infraestrutura.cofre.credenciais import (
    CredencialBanco,
    CredencialRedis,
    Segredo,
    TipoBanco,
)
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet


class SistemaVaultSemListagem:
    def list_mounted_secrets_engines(self) -> object:
        raise hvac.exceptions.Forbidden()


class ClienteOperadorSemListagem:
    def __init__(self, **_opcoes: object) -> None:
        self.sys = SistemaVaultSemListagem()

    def is_authenticated(self) -> bool:
        return True


class ClienteVaultFalso:
    def __init__(self, endereco: str, token: Segredo) -> None:
        pass

    def validar_acesso(self) -> None:
        pass


class CarregadorCredenciaisFalso:
    def __init__(self, provedor: object) -> None:
        pass

    def carregar_banco(self, caminho: str, tipo: TipoBanco, **opcoes: object) -> CredencialBanco:
        return CredencialBanco(
            tipo=tipo,
            host="db.interno",
            porta=1433 if tipo is TipoBanco.SQLSERVER else 5432,
            nome_banco="banco",
            usuario="user",
            senha=Segredo("senha"),
            esquema="luft_teste" if tipo is TipoBanco.POSTGRESQL else None,
        )

    def carregar_banco_composto(
        self,
        caminho_app: str,
        caminho_conexao: str,
        tipo: TipoBanco = TipoBanco.POSTGRESQL,
    ) -> CredencialBanco:
        return CredencialBanco(
            tipo=tipo,
            host="db.interno",
            porta=5432,
            nome_banco="banco",
            usuario="user",
            senha=Segredo("senha"),
            esquema="luft_teste",
        )

    def carregar_aplicacao_postgresql(
        self,
        caminho: str,
        raiz_conexoes: str,
        *,
        sistema_id_esperado: int,
    ) -> object:
        del caminho, raiz_conexoes, sistema_id_esperado
        return object()

    def carregar_redis(self, caminho: str) -> CredencialRedis:
        return CredencialRedis(
            host="redis.interno",
            porta=6379,
            banco=0,
            senha=Segredo("senha_redis"),
            chave_assinatura_sessao=Segredo("x" * 64),
        )

    def carregar_email(self, caminho: str) -> object:
        from luftbase.nucleo.excecoes import SegredoNaoEncontrado

        raise SegredoNaoEncontrado(caminho)


def _configurar_ambiente(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    protetor = DesprotetorFernet("chave_teste_123")
    monkeypatch.setenv("LUFT_SISTEMA_ID", "0")
    monkeypatch.setenv("LUFT_AMBIENTE", "desenvolvimento")
    monkeypatch.setenv("LUFT_VAULT_ENDERECO", "http://vault:8200")
    monkeypatch.setenv("LUFT_LDAP_SERVIDOR", "ad.luft.interno")
    monkeypatch.setenv("LUFT_LDAP_DOMINIO", "LUFTFARMA")
    monkeypatch.setenv("LUFT_VAULT_TOKEN", protetor.proteger("token_vault_real"))
    monkeypatch.setenv("LUFT_TOKEN_ACESSO", "chave_teste_123")


def test_vault_caminhos_deriva_corretamente(monkeypatch) -> None:
    _configurar_ambiente(monkeypatch)
    runner = CliRunner()
    resultado = runner.invoke(cli, ["vault", "caminhos"])

    assert resultado.exit_code == 0
    assert (
        "sqlserver=luft/desenvolvimento/bancos/sqlserver/conexoes/user.services" in resultado.output
    )
    assert "sqlserver_legado=luft/desenvolvimento/sqlserver" in resultado.output
    esperado_pg = "postgresql=luft/desenvolvimento/bancos/postgresql/sistemas/0"
    assert esperado_pg in resultado.output
    assert "sistema_id=0" in resultado.output
    assert "sessoes_redis=luft/desenvolvimento/redis/sessoes" in resultado.output
    assert "email=luft/desenvolvimento/integracoes/email" in resultado.output


def test_vault_verificar_sem_conectar(monkeypatch) -> None:
    _configurar_ambiente(monkeypatch)
    runner = CliRunner()
    resultado = runner.invoke(cli, ["vault", "verificar"])

    assert resultado.exit_code == 0
    assert "validacao_estrutural=concluida" in resultado.output


def test_vault_verificar_com_conectar(monkeypatch) -> None:
    _configurar_ambiente(monkeypatch)
    modulo_vault = sys.modules["luftbase.cli.vault"]
    monkeypatch.setattr(modulo_vault, "ClienteVaultHvac", ClienteVaultFalso)
    monkeypatch.setattr(modulo_vault, "CarregadorCredenciais", CarregadorCredenciaisFalso)

    runner = CliRunner()
    resultado = runner.invoke(cli, ["vault", "verificar", "--conectar"])

    assert resultado.exit_code == 0
    assert "conexao=ok" in resultado.output
    assert "segredos=validos" in resultado.output
    assert "email_status=ausente" in resultado.output
    assert "senha" not in resultado.output.lower()


def test_cliente_operador_aceita_policy_sem_permissao_de_listar_mounts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    modulo_vault = sys.modules["luftbase.cli.vault"]
    monkeypatch.setattr(hvac, "Client", ClienteOperadorSemListagem)

    cliente = modulo_vault._criar_cliente_hvac_operador(  # type: ignore[attr-defined]
        "http://vault:8200",
        "token",
        "secret",
    )

    assert isinstance(cliente, ClienteOperadorSemListagem)
