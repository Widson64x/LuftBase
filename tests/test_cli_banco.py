"""Testes dos comandos de banco sem acessar dependencias externas."""

from flask import Flask

from luftbase.cli.banco import (
    CONFIRMACAO_ADOCAO,
    CONFIRMACAO_ATUALIZACAO,
    TABELAS_BASELINE,
    banco,
    obter_metadados_baseline,
    resumir_diferencas,
)


def _app_cli() -> Flask:
    app = Flask(__name__)
    app.cli.add_command(banco)
    return app


def test_grupo_expoe_comandos_operacionais() -> None:
    assert set(banco.commands) == {
        "atualizar",
        "bootstrap",
        "conceder-permissoes",
        "historico",
        "pendencias",
        "retencao",
        "registrar-base",
        "tamanho-logs",
        "validar",
        "versao",
    }


def test_historico_lista_revisoes_do_pacote() -> None:
    resultado = _app_cli().test_cli_runner().invoke(args=["banco", "historico"])

    assert resultado.exit_code == 0
    assert "20260915_0001" in resultado.output
    assert "20260916_0005" in resultado.output
    assert "20260917_0006" in resultado.output


def test_baseline_contem_somente_as_quatorze_tabelas_migradas() -> None:
    metadados = obter_metadados_baseline()

    assert len(TABELAS_BASELINE) == 14
    assert set(metadados.tables) == {f"core.{nome}" for nome in TABELAS_BASELINE}
    assert "core.tb_preferenciausuario" not in metadados.tables
    assert "core.tb_revisaocache" not in metadados.tables


def test_resumo_de_diferencas_nao_expoe_conteudo() -> None:
    diferencas: list[object] = [
        ("add_table", object()),
        [("modify_type", "core", "tabela", "coluna", "segredo", "outro")],
    ]

    resumo = resumir_diferencas(diferencas)

    assert resumo == {"add_table": 1, "modify_type": 1}
    assert "segredo" not in str(resumo)


def test_atualizacao_exige_frase_explicita() -> None:
    resultado = _app_cli().test_cli_runner().invoke(args=["banco", "atualizar"])

    assert resultado.exit_code == 2
    assert CONFIRMACAO_ATUALIZACAO in resultado.output


def test_adocao_exige_frase_explicita() -> None:
    resultado = _app_cli().test_cli_runner().invoke(args=["banco", "registrar-base"])

    assert resultado.exit_code == 2
    assert CONFIRMACAO_ADOCAO in resultado.output


def test_validacao_documenta_modo_baseline() -> None:
    resultado = _app_cli().test_cli_runner().invoke(args=["banco", "validar", "--help"])

    assert resultado.exit_code == 0
    assert "--baseline-migrada" in resultado.output
