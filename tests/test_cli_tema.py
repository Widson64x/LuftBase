"""Testes dos comandos de listagem e validacao de temas."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from luftbase.cli import cli


def test_tema_listar_exibe_temas_registrados() -> None:
    runner = CliRunner()
    resultado = runner.invoke(cli, ["tema", "listar"])

    assert resultado.exit_code == 0
    assert "temas_registrados=" in resultado.output
    assert "luft:" in resultado.output
    assert "url=/_luftbase/static/css/temas/luft.css" in resultado.output


def test_tema_validar_css_corporativo() -> None:
    css_corporativo = (
        Path(__file__).parent.parent
        / "src"
        / "luftbase"
        / "interface"
        / "static"
        / "css"
        / "temas"
        / "luft.css"
    )
    runner = CliRunner()
    resultado = runner.invoke(cli, ["tema", "validar", str(css_corporativo)])

    assert resultado.exit_code == 0
    assert "status=valido tokens=completos" in resultado.output


def test_tema_validar_css_incompleto(tmp_path: Path) -> None:
    css_ruim = tmp_path / "tema_ruim.css"
    css_ruim.write_text("body { color: red; }", encoding="utf-8")

    runner = CliRunner()
    resultado = runner.invoke(cli, ["tema", "validar", str(css_ruim)])

    assert resultado.exit_code != 0
    assert "status=invalido" in resultado.output
    assert "token ausente" in resultado.output


def test_tema_validar_manifesto_json(tmp_path: Path) -> None:
    manifesto_bom = tmp_path / "tema.json"
    manifesto_bom.write_text(
        """{
            "identificador": "operacoes",
            "nome": "Operacoes",
            "versao": "1.0.0",
            "url_css": "/static/operacoes.css"
        }""",
        encoding="utf-8",
    )

    runner = CliRunner()
    resultado = runner.invoke(cli, ["tema", "validar", str(manifesto_bom)])

    assert resultado.exit_code == 0
    assert "manifesto=operacoes status=valido" in resultado.output


def test_tema_validar_manifesto_json_invalido(tmp_path: Path) -> None:
    manifesto_ruim = tmp_path / "tema_invalido.json"
    manifesto_ruim.write_text(
        """{
            "identificador": "Nome Com Espaco Invalido",
            "nome": "Operacoes",
            "versao": "1.0.0",
            "url_css": "https://cdn.externo/style.css"
        }""",
        encoding="utf-8",
    )

    runner = CliRunner()
    resultado = runner.invoke(cli, ["tema", "validar", str(manifesto_ruim)])

    assert resultado.exit_code != 0
    assert "status=invalido" in resultado.output


def test_tema_listar_inclui_luft_esg() -> None:
    resultado = CliRunner().invoke(cli, ["tema", "listar"])

    assert resultado.exit_code == 0
    assert "luft-esg:" in resultado.output
    assert "temas/luft-esg.css" in resultado.output


def test_tema_validar_css_luft_esg() -> None:
    css = (
        Path(__file__).parent.parent
        / "src"
        / "luftbase"
        / "interface"
        / "static"
        / "css"
        / "temas"
        / "luft-esg.css"
    )
    resultado = CliRunner().invoke(cli, ["tema", "validar", str(css)])

    assert resultado.exit_code == 0
    assert "status=valido tokens=completos" in resultado.output


def test_tema_validar_css_de_modo_unico_nao_exige_o_outro_modo(tmp_path: Path) -> None:
    tokens = "\n".join(
        f"  {t}: #123456;"
        for t in (
            "--luft-cor-fundo",
            "--luft-cor-superficie",
            "--luft-cor-texto",
            "--luft-cor-borda",
            "--luft-cor-destaque",
            "--luft-cor-foco",
            "--luft-cor-sucesso",
            "--luft-cor-alerta",
            "--luft-cor-perigo",
        )
    )
    css = tmp_path / "so_claro.css"
    css.write_text(f"[data-luft-theme='x'] {{\n  color-scheme: light;\n{tokens}\n}}\n", "utf-8")

    padrao = CliRunner().invoke(cli, ["tema", "validar", str(css)])
    so_claro = CliRunner().invoke(cli, ["tema", "validar", str(css), "--modos", "claro"])

    assert padrao.exit_code != 0
    assert "modo escuro ausente" in padrao.output
    assert so_claro.exit_code == 0
    assert "status=valido" in so_claro.output


def test_tema_validar_manifesto_json_de_modo_unico(tmp_path: Path) -> None:
    manifesto = tmp_path / "tema.json"
    manifesto.write_text(
        """{
            "identificador": "so-claro",
            "nome": "So Claro",
            "versao": "1.0.0",
            "url_css": "/static/so-claro.css",
            "modos": ["claro"]
        }""",
        encoding="utf-8",
    )

    resultado = CliRunner().invoke(cli, ["tema", "validar", str(manifesto)])

    assert resultado.exit_code == 0
    assert "manifesto=so-claro status=valido" in resultado.output

