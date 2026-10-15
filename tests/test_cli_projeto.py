"""Testes do gerador de projetos (padrao ADR-017) e do comando `projeto novo`."""

from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from core_sqlite import motor_sqlite
from sqlalchemy import select
from sqlalchemy.orm import Session

from luftbase.cli import cli
from luftbase.cli.operador import SessaoOperador
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.provisionamento_sistema import (
    DestinoProvisionamento,
    PlanoSistema,
)
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.seguranca import Permissao, PermissaoGrupo, Sistema

# `luftbase.cli.projeto` e `.sistema` sao tambem nomes de grupos Click no pacote `luftbase.cli`;
# o modulo real vem de sys.modules.
MODULO_PROJETO = sys.modules["luftbase.cli.projeto"]
MODULO_SISTEMA = sys.modules["luftbase.cli.sistema"]
RAIZ_SRC = Path(__file__).resolve().parents[1] / "src"


class ProvisionadorFalso:
    """Faz o papel do ProvisionadorSistema sem PostgreSQL nem Vault reais."""

    ambiente = "desenvolvimento"

    def __init__(self, engine: Any, *, falhar_no_vault: bool = False) -> None:
        self._engine = engine
        self._falhar_no_vault = falhar_no_vault
        self.segredos: dict[int, dict[str, object]] = {}
        self.planos: list[PlanoSistema] = []
        self.encerrado = False

    def engine_administrativo(self) -> Any:
        return self._engine

    def segredo_existe(self, sistema_id: int) -> bool:
        return sistema_id in self.segredos

    def provisionar_banco(self, plano: PlanoSistema) -> tuple[Segredo, bool]:
        self.planos.append(plano)
        return Segredo("senha-aleatoria"), True

    def gravar_segredo(
        self, plano: PlanoSistema, alias: str, senha: Segredo, *, substituir: bool = False
    ) -> str:
        if self._falhar_no_vault:
            raise RuntimeError("vault recusou")
        self.segredos[plano.sistema_id] = {"conexao": alias, "usuario": plano.role}
        return f"luft/desenvolvimento/bancos/postgresql/sistemas/{plano.sistema_id}"

    def remover_segredo(self, sistema_id: int) -> None:
        self.segredos.pop(sistema_id, None)

    def encerrar(self) -> None:
        self.encerrado = True


def _sessao_falsa(provisionador: ProvisionadorFalso) -> SessaoOperador:
    destino = DestinoProvisionamento(
        ambiente="desenvolvimento",
        namespace="luft",
        vault_url="http://vault:8200",
        host="localhost",
        porta=5432,
        banco="luft_web",
        sistema_referencia=0,
    )
    return SessaoOperador(provisionador, destino, "luft_dev")  # type: ignore[arg-type]


@pytest.fixture
def core() -> Any:
    return motor_sqlite(BaseLuft, "core")


def _usar_sessao(monkeypatch: pytest.MonkeyPatch, provisionador: ProvisionadorFalso) -> None:
    sessao = _sessao_falsa(provisionador)
    # O core SQLite dos testes nao tem core.alembic_version; a verificacao tem testes proprios.
    for modulo in (MODULO_PROJETO, MODULO_SISTEMA):
        monkeypatch.setattr(modulo, "exigir_core_atualizado", lambda _engine: None)
    for modulo in (MODULO_PROJETO, MODULO_SISTEMA):
        monkeypatch.setattr(modulo, "abrir_sessao_operador", lambda **_: sessao)


def test_projeto_criar_rejeita_nome_invalido() -> None:
    resultado = CliRunner().invoke(cli, ["projeto", "criar", "Identificador_Invalido!"])

    assert resultado.exit_code != 0
    assert "letras minusculas" in resultado.output.lower()


def test_projeto_criar_rejeita_nome_com_espaco() -> None:
    resultado = CliRunner().invoke(cli, ["projeto", "criar", "Meu Projeto"])

    assert resultado.exit_code != 0
    assert "espacos" in resultado.output


def test_projeto_criar_gera_arvore_do_padrao_luft(tmp_path: Path) -> None:
    destino = tmp_path / "Luft-Exemplo"

    resultado = CliRunner().invoke(
        cli,
        [
            "projeto",
            "criar",
            "Luft-Exemplo",
            "--destino",
            str(destino),
            "--schema",
            "exemplo",
            "--porta",
            "9055",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    assert "projeto=Luft-Exemplo status=criado" in resultado.output
    for relativo in (
        "App.py",
        "Wsgi.py",
        "requirements.txt",
        ".env.example",
        ".gitignore",
        "README.md",
        "App/__init__.py",
        "App/_version.py",
        "App/Catalogo.py",
        "App/Buscas.py",
        "App/Conexoes.py",
        "App/Configuracoes.py",
        "App/Models/POSTGRES/Base.py",
        "App/Routes/Principal.py",
        "App/Services/LogService.py",
        "App/Templates/Layout/BaseLayout.html",
        "App/Templates/Pages/Inicio.html",
        "tests/test_app.py",
        "deploy/nginx.conf",
        "deploy/nssm.ps1",
        "Data/.gitkeep",
        "SQL/.gitkeep",
    ):
        assert (destino / relativo).exists(), relativo

    catalogo = (destino / "App/Catalogo.py").read_text(encoding="utf-8")
    assert "LUFT_EXEMPLO.SISTEMA.ACESSAR" in catalogo
    assert "Luft-Exemplo" in (destino / "App/Configuracoes.py").read_text(encoding="utf-8")
    assert "server 127.0.0.1:9055;" in (destino / "deploy/nginx.conf").read_text(encoding="utf-8")
    assert '"Wsgi.py"' in (destino / "deploy/nssm.ps1").read_text(encoding="utf-8")
    # Nenhum marcador do gerador pode sobrar no que foi escrito.
    for arquivo in destino.rglob("*"):
        if arquivo.is_file():
            assert "__NOME__" not in arquivo.read_text(encoding="utf-8"), arquivo
    assert compileall.compile_dir(str(destino), quiet=1) is True


def test_projeto_gerado_inicializa_com_infraestrutura_em_memoria(tmp_path: Path) -> None:
    destino = tmp_path / "Luft-Vivo"
    resultado = CliRunner().invoke(
        cli, ["projeto", "criar", "Luft-Vivo", "--destino", str(destino)]
    )
    assert resultado.exit_code == 0, resultado.output

    ambiente = {**os.environ, "PYTHONPATH": str(RAIZ_SRC)}
    execucao = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=destino,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert execucao.returncode == 0, execucao.stdout + execucao.stderr


def test_projeto_criar_recusa_sobrescrever_diretorio_nao_vazio(tmp_path: Path) -> None:
    destino = tmp_path / "existente"
    destino.mkdir()
    (destino / "arquivo_qualquer.txt").write_text("conteudo", encoding="utf-8")

    sem_forcar = CliRunner().invoke(
        cli, ["projeto", "criar", "App-Teste", "--destino", str(destino)]
    )
    com_forcar = CliRunner().invoke(
        cli, ["projeto", "criar", "App-Teste", "--destino", str(destino), "--forcar"]
    )

    assert sem_forcar.exit_code != 0
    assert "nao esta vazio" in sem_forcar.output
    assert com_forcar.exit_code == 0
    assert (destino / "arquivo_qualquer.txt").exists()


def test_projeto_deploy_gera_somente_artefatos_de_deploy(tmp_path: Path) -> None:
    destino_deploy = tmp_path / "deploy_out"

    resultado = CliRunner().invoke(
        cli, ["projeto", "deploy", "servico-teste", "--destino", str(destino_deploy)]
    )

    assert resultado.exit_code == 0
    assert "deploy=servico-teste gerados=3" in resultado.output
    assert (destino_deploy / "nginx.conf").is_file()


def test_projeto_novo_recusa_producao(tmp_path: Path) -> None:
    resultado = CliRunner().invoke(
        cli,
        ["projeto", "novo", "Luft-X", "--ambiente", "producao", "--destino", str(tmp_path / "x")],
    )

    assert resultado.exit_code != 0
    assert "Invalid value" in resultado.output or "producao" in resultado.output


def test_projeto_novo_somente_estrutura_nao_toca_em_banco(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def proibido(**_: object) -> None:
        raise AssertionError("nao deve abrir sessao de operador")

    monkeypatch.setattr(MODULO_PROJETO, "abrir_sessao_operador", proibido)
    destino = tmp_path / "Luft-Local"

    resultado = CliRunner().invoke(
        cli,
        [
            "projeto",
            "novo",
            "Luft-Local",
            "--destino",
            str(destino),
            "--somente-estrutura",
            "--sim",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    assert (destino / "App/__init__.py").is_file()
    assert not (destino / ".env").exists()


def test_projeto_novo_cadastra_sistema_e_escreve_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, core: Any
) -> None:
    provisionador = ProvisionadorFalso(core)
    _usar_sessao(monkeypatch, provisionador)
    referencia = tmp_path / "referencia.env"
    referencia.write_text(
        "LUFT_SISTEMA_ID=99\nLUFT_VAULT_TOKEN=token-protegido\nLUFT_TOKEN_ACESSO=chave\n"
        "LUFT_LDAP_DOMINIO=luftfarma\nSENHA_QUALQUER=nao-copiar\n",
        encoding="utf-8",
    )
    destino = tmp_path / "Luft-Control"

    resultado = CliRunner().invoke(
        cli,
        [
            "projeto",
            "novo",
            "Luft-Control",
            "--destino",
            str(destino),
            "--schema",
            "control",
            "--env-referencia",
            str(referencia),
            "--sim",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    with Session(core) as sessao:
        sistema = sessao.execute(select(Sistema)).scalar_one()
        permissao = sessao.execute(select(Permissao)).scalar_one()
        concessao = sessao.execute(select(PermissaoGrupo)).scalar_one()
    assert sistema.nome_sistema == "Luft-Control"
    assert sistema.schema_aplicacao == "control"
    assert sistema.integra_luftbase is True or sistema.integra_luftbase == 1
    assert permissao.chave_permissao == "LUFT_CONTROL.SISTEMA.ACESSAR"
    assert permissao.eh_acesso_sistema
    assert concessao.codigo_usuariogrupo == 6

    assert provisionador.planos[0].role.startswith("luft_control_")
    assert provisionador.planos[0].role.endswith("_app")
    assert provisionador.segredos[sistema.id_sistema]["conexao"] == "luft_dev"
    assert provisionador.encerrado

    env = (destino / ".env").read_text(encoding="utf-8")
    assert f"LUFT_SISTEMA_ID={sistema.id_sistema}" in env
    assert "LUFT_VAULT_TOKEN=token-protegido" in env
    assert "SENHA_QUALQUER" not in env
    assert "99" not in env.split("LUFT_SISTEMA_ID=")[1].splitlines()[0]
    exemplo = (destino / ".env.example").read_text(encoding="utf-8")
    assert "token-protegido" not in exemplo
    assert "senha-aleatoria" not in resultado.output + env + exemplo


def test_projeto_novo_vault_recusa_e_nao_deixa_nada_no_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, core: Any
) -> None:
    provisionador = ProvisionadorFalso(core, falhar_no_vault=True)
    _usar_sessao(monkeypatch, provisionador)

    resultado = CliRunner().invoke(
        cli,
        [
            "projeto",
            "novo",
            "Luft-Falha",
            "--destino",
            str(tmp_path / "f"),
            "--schema",
            "falha",
            "--sim",
        ],
    )

    assert resultado.exit_code != 0
    assert "Nada foi gravado" in resultado.output
    with Session(core) as sessao:
        assert sessao.execute(select(Sistema)).first() is None
    assert provisionador.segredos == {}
    assert not (tmp_path / "f" / ".env").exists()


def test_projeto_novo_nome_repetido_e_recusado(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, core: Any
) -> None:
    _usar_sessao(monkeypatch, ProvisionadorFalso(core))
    args = ["projeto", "novo", "Luft-Dup", "--schema", "dup", "--sim"]

    primeiro = CliRunner().invoke(cli, [*args, "--destino", str(tmp_path / "a")])
    segundo = CliRunner().invoke(cli, [*args, "--destino", str(tmp_path / "b")])

    assert primeiro.exit_code == 0, primeiro.output
    assert segundo.exit_code != 0
    assert "Ja existe" in segundo.output


def test_sistema_externo_grava_download_sem_schema_nem_vault(
    monkeypatch: pytest.MonkeyPatch, core: Any
) -> None:
    provisionador = ProvisionadorFalso(core)
    _usar_sessao(monkeypatch, provisionador)

    resultado = CliRunner().invoke(
        cli,
        [
            "sistema",
            "externo",
            "Luft-Informa",
            "--tipo-acesso",
            "download",
            "--url-download",
            "/Luft-Workspace/atualizador",
            "--sim",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    with Session(core) as sessao:
        sistema = sessao.execute(select(Sistema)).scalar_one()
    assert sistema.integra_luftbase is False or sistema.integra_luftbase == 0
    assert sistema.tipo_acesso == "DOWNLOAD"
    assert sistema.url_download == "/Luft-Workspace/atualizador"
    assert sistema.schema_aplicacao is None
    assert provisionador.planos == []
    assert provisionador.segredos == {}


def test_sistema_externo_download_sem_url_e_recusado(
    monkeypatch: pytest.MonkeyPatch, core: Any
) -> None:
    _usar_sessao(monkeypatch, ProvisionadorFalso(core))

    resultado = CliRunner().invoke(
        cli, ["sistema", "externo", "Luft-Informa", "--tipo-acesso", "download", "--sim"]
    )

    assert resultado.exit_code != 0
    assert "UrlDownload" in resultado.output
