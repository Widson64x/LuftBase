"""Testes do gerador de projetos e scaffolding LuftBase."""

from __future__ import annotations

import compileall
from pathlib import Path

from click.testing import CliRunner

from luftbase.cli import cli


def test_projeto_criar_rejeita_identificador_invalido() -> None:
    runner = CliRunner()
    resultado = runner.invoke(
        cli,
        ["projeto", "criar", "Identificador_Invalido!", "--sistema-id", "7"],
    )
    assert resultado.exit_code != 0
    assert "letras minusculas" in resultado.output.lower() or "hifens" in resultado.output.lower()


def test_projeto_criar_gera_arvore_completa_e_deterministica(tmp_path: Path) -> None:
    runner = CliRunner()
    destino = tmp_path / "meu-projeto"

    resultado = runner.invoke(
        cli,
        [
            "projeto",
            "criar",
            "meu-projeto",
            "--sistema-id",
            "7",
            "--nome",
            "Meu Projeto Corporativo",
            "--destino",
            str(destino),
            "--schema",
            "meu_projeto_schema",
        ],
    )

    assert resultado.exit_code == 0
    assert "projeto=meu-projeto status=criado" in resultado.output

    # Conferir arquivos essenciais
    esperados = [
        destino / "pyproject.toml",
        destino / ".env.example",
        destino / ".gitignore",
        destino / "README.md",
        destino / "src" / "meu_projeto" / "__init__.py",
        destino / "src" / "meu_projeto" / "app.py",
        destino / "src" / "meu_projeto" / "rotas.py",
        destino / "src" / "meu_projeto" / "templates" / "meu_projeto" / "inicio.html",
        destino / "tests" / "__init__.py",
        destino / "tests" / "test_app.py",
        destino / "deploy" / "nginx.conf",
        destino / "deploy" / "nssm.ps1",
        destino / "deploy" / "README.md",
    ]

    for arq in esperados:
        assert arq.is_file(), f"Arquivo esperado nao encontrado: {arq}"

    # Conferir conteudo do app.py
    conteudo_app = (destino / "src" / "meu_projeto" / "app.py").read_text(encoding="utf-8")
    assert "from luftbase import PlataformaLuft" in conteudo_app
    assert "criar_app(" in conteudo_app

    # Conferir conteudo do template inicio.html
    conteudo_template = (
        destino / "src" / "meu_projeto" / "templates" / "meu_projeto" / "inicio.html"
    ).read_text(encoding="utf-8")
    assert '{% extends "luftbase/base.html" %}' in conteudo_template

    # Conferir conteudo do nginx.conf
    conteudo_nginx = (destino / "deploy" / "nginx.conf").read_text(encoding="utf-8")
    assert "location ~ ^/_luftbase/.+/eventos$" in conteudo_nginx
    assert "proxy_buffering off;" in conteudo_nginx
    assert "proxy_set_header X-Correlation-ID $request_id;" in conteudo_nginx

    # Conferir conteudo do nssm.ps1
    conteudo_nssm = (destino / "deploy" / "nssm.ps1").read_text(encoding="utf-8")
    assert '$ServiceName = "meu-projeto"' in conteudo_nssm
    assert "meu_projeto.app:criar_app" in conteudo_nssm

    # Compilacao sintatica de todos os arquivos gerados
    sucesso_compilacao = compileall.compile_dir(str(destino), quiet=1)
    assert sucesso_compilacao is True

    # Execucao dos testes da aplicacao gerada
    import sys

    import pytest

    caminho_src = str(destino / "src")
    sys.path.insert(0, caminho_src)
    try:
        codigo_retorno = pytest.main([str(destino / "tests"), "-q", "-p", "no:cacheprovider"])
        assert codigo_retorno == 0
    finally:
        if caminho_src in sys.path:
            sys.path.remove(caminho_src)


def test_projeto_criar_recusa_sobrescrever_diretorio_nao_vazio(tmp_path: Path) -> None:
    runner = CliRunner()
    destino = tmp_path / "existente"
    destino.mkdir()
    (destino / "arquivo_qualquer.txt").write_text("conteudo", encoding="utf-8")

    # Sem flag --forcar
    resultado = runner.invoke(
        cli,
        [
            "projeto",
            "criar",
            "app-teste",
            "--sistema-id",
            "7",
            "--destino",
            str(destino),
        ],
    )
    assert resultado.exit_code != 0
    assert "nao esta vazio" in resultado.output

    # Com flag --forcar
    resultado_forcar = runner.invoke(
        cli,
        [
            "projeto",
            "criar",
            "app-teste",
            "--sistema-id",
            "7",
            "--destino",
            str(destino),
            "--forcar",
        ],
    )
    assert resultado_forcar.exit_code == 0
    assert "status=criado" in resultado_forcar.output


def test_projeto_deploy_gera_somente_artefatos_de_deploy(tmp_path: Path) -> None:
    runner = CliRunner()
    destino_deploy = tmp_path / "deploy_out"

    resultado = runner.invoke(
        cli,
        ["projeto", "deploy", "servico-teste", "--destino", str(destino_deploy)],
    )

    assert resultado.exit_code == 0
    assert "deploy=servico-teste gerados=3" in resultado.output
    assert (destino_deploy / "nginx.conf").is_file()
    assert (destino_deploy / "nssm.ps1").is_file()
    assert (destino_deploy / "README.md").is_file()
