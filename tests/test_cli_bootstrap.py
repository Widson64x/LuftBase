"""Testes do comando interativo bootstrap."""

from click.testing import CliRunner

from luftbase.cli.bootstrap import SISTEMAS_PADRAO, bootstrap


def test_bootstrap_expoe_opcoes_e_ajuda() -> None:
    runner = CliRunner()
    resultado = runner.invoke(bootstrap, ["--help"])

    assert resultado.exit_code == 0
    assert "Assistente interativo" in resultado.output
    assert "--ambiente" in resultado.output
    assert "--host" in resultado.output
    assert "--porta" in resultado.output
    assert "--banco" in resultado.output
    assert "--admin-user" in resultado.output
    assert "--vault-url" in resultado.output
    assert "--alias-conexao" in resultado.output


def test_sistemas_padrao_contem_sistema_zero_workspace() -> None:
    assert len(SISTEMAS_PADRAO) == 1
    app = SISTEMAS_PADRAO[0]
    assert app.sistema_id == 0
    assert app.identificador == "luft-workspace"
    assert app.esquema == "workspace"
    assert app.usuario == "luft_workspace_app"


def test_bootstrap_recusa_confirmacao_invalida() -> None:
    runner = CliRunner()
    # Simula entrada com cancelamento na confirmação
    entradas = "\n".join(
        [
            "producao",  # ambiente
            "http://vault.invalid:8200",  # vault_url
            "s.token-invalido",  # vault_token
            "127.0.0.1",  # host
            "5432",  # porta
            "luft_web",  # banco
            "LUFT_WEB_OWNER",  # admin_user
            "senha_secreta",  # admin_password
            "luft-web",  # alias
            "y",  # usar padrao
            "NAO_CONFIRMAR",  # confirmacao errada
        ]
    )
    resultado = runner.invoke(bootstrap, input=entradas)

    assert resultado.exit_code != 0
    assert "Confirmacao cancelada" in resultado.output


def test_bootstrap_atualizar_recusa_confirmacao_invalida() -> None:
    runner = CliRunner()
    entradas = "\n".join(
        [
            "127.0.0.1",  # host
            "5432",  # porta
            "luft_web",  # banco
            "admin",  # admin_user
            "senha_secreta",  # senha
            "CONFIRMACAO_ERRADA",  # confirmacao incorreta
        ]
    )
    resultado = runner.invoke(bootstrap, ["--atualizar"], input=entradas)

    assert resultado.exit_code != 0
    assert "Confirmacao cancelada" in resultado.output


def test_bootstrap_atualizar_nao_acessa_vault_e_executa_sincronizacao(monkeypatch) -> None:
    import sys
    from unittest.mock import MagicMock

    from luftbase.persistencia.core.catalogo import ResultadoSincronizacaoCatalogo

    mod_bootstrap = sys.modules["luftbase.cli.bootstrap"]

    upgrade_mock = MagicMock()
    sincronizar_mock = MagicMock(return_value=ResultadoSincronizacaoCatalogo(9, 49, 6))

    mock_conexao = MagicMock()
    mock_conexao.scalar.return_value = "luft_web"

    class EngineMock:
        def begin(self):
            class Contexto:
                def __enter__(self_ctx):
                    return mock_conexao

                def __exit__(self_ctx, *args):
                    pass

            return Contexto()

        def dispose(self):
            pass

    monkeypatch.setattr(mod_bootstrap, "create_engine", lambda *args, **kwargs: EngineMock())
    monkeypatch.setattr(mod_bootstrap.command, "upgrade", upgrade_mock)
    monkeypatch.setattr(mod_bootstrap, "sincronizar_catalogo_workspace", sincronizar_mock)

    runner = CliRunner()
    entradas = "\n".join(
        [
            "127.0.0.1",  # host
            "5432",  # porta
            "luft_web",  # banco
            "admin",  # admin_user
            "senha_secreta",  # senha
            "ATUALIZAR-DESENVOLVIMENTO-LUFT_WEB",  # confirmacao exata
        ]
    )
    resultado = runner.invoke(
        bootstrap,
        ["--atualizar", "--ambiente", "desenvolvimento", "--grupo-administrador", "6"],
        input=entradas,
    )

    assert resultado.exit_code == 0
    assert "Vault=nao acessado" in resultado.output
    assert "roles=nao alteradas" in resultado.output
    assert "dados existentes=preservados" in resultado.output
    assert "modulos_sincronizados=9" in resultado.output
    assert "permissoes_sincronizadas=49" in resultado.output
    assert "grupo_administrador=6" in resultado.output
    upgrade_mock.assert_called_once()
    sincronizar_mock.assert_called_once()
