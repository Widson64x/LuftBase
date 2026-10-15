"""Espelho local do banco: regras de seguranca, comandos, roles e orquestracao (sem PostgreSQL real)."""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from luftbase.cli import cli
from luftbase.cli.operador import SessaoOperador
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.infraestrutura.cofre.credenciais import CredencialBanco, Segredo, TipoBanco
from luftbase.infraestrutura.espelho_banco import (
    ErroEspelho,
    RoleAplicacao,
    Servidor,
    aplicar_roles,
    comando_dump,
    comando_restore,
    configurar_env,
    copiar_dados,
    espelhar,
    exigir_destino_local,
    ler_roles_aplicacao,
    localizar_ferramentas,
    recriar_banco,
    validar_nome_banco,
)
from luftbase.infraestrutura.provisionamento_sistema import DestinoProvisionamento
from luftbase.nucleo.excecoes import ErroConfiguracao

MODULO_BANCO = sys.modules["luftbase.cli.banco"]
ORIGEM = Servidor("172.19.85.111", 5432, "luft_web", "admin", "senha-da-origem")
DESTINO = Servidor("localhost", 5432, "luft_web", "postgres", "senha-local")
VERIFICADOR = "SCRAM-SHA-256$4096:salt$stored:server"


class CursorFalso:
    def __init__(self, conexao: ConexaoFalsa) -> None:
        self._conexao = conexao
        self._ultimo: str = ""

    def __enter__(self) -> CursorFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, consulta: Any, parametros: Any = None) -> None:
        texto = consulta if isinstance(consulta, str) else consulta.as_string(None)
        self._ultimo = texto
        self._conexao.comandos.append((texto, parametros))

    def fetchall(self) -> list[tuple[str, str]]:
        return self._conexao.roles

    def fetchone(self) -> tuple[int] | None:
        if "pg_database" in self._ultimo:
            return (1,) if self._conexao.banco_existe else None
        if "pg_roles" in self._ultimo:
            return (1,) if self._conexao.role_existe else None
        return None


class ConexaoFalsa:
    def __init__(self, *, roles: list[tuple[str, str]] | None = None) -> None:
        self.roles = roles or []
        self.comandos: list[tuple[str, Any]] = []
        self.banco_existe = False
        self.role_existe = False

    def cursor(self) -> CursorFalso:
        return CursorFalso(self)

    def __enter__(self) -> ConexaoFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None


class ProcessoFalso:
    def __init__(self, comando: list[str], retorno: int, erro: bytes, **opcoes: Any) -> None:
        self.comando = comando
        self.opcoes = opcoes
        self.returncode = retorno
        self.stdout = io.BytesIO(b"dump")
        self.stderr = io.BytesIO(erro)

    def communicate(self) -> tuple[bytes, bytes]:
        return b"", self.stderr.read()

    def wait(self) -> int:
        return self.returncode


class FabricaDeProcessos:
    def __init__(self, retornos: tuple[int, int] = (0, 0), erro: bytes = b"") -> None:
        self.retornos = list(retornos)
        self.erro = erro
        self.processos: list[ProcessoFalso] = []

    def __call__(self, comando: list[str], **opcoes: Any) -> ProcessoFalso:
        processo = ProcessoFalso(comando, self.retornos[len(self.processos)], self.erro, **opcoes)
        self.processos.append(processo)
        return processo


# --- Regras de seguranca -------------------------------------------------------------------


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", " LOCALHOST "])
def test_destino_local_aceito(host: str) -> None:
    assert exigir_destino_local(host) == host.strip()


@pytest.mark.parametrize("host", ["172.19.85.111", "db.luft.interno", "0.0.0.0"])
def test_destino_remoto_e_recusado(host: str) -> None:
    with pytest.raises(ErroEspelho, match="propria maquina"):
        exigir_destino_local(host)


def test_nome_de_banco_invalido_e_recusado() -> None:
    with pytest.raises(ErroEspelho):
        validar_nome_banco('luft"; DROP DATABASE x; --')
    assert validar_nome_banco("luft_web") == "luft_web"


def test_senha_vai_por_ambiente_e_nunca_por_argumento() -> None:
    fabrica = FabricaDeProcessos()
    ferramentas = {"pg_dump": "pg_dump", "pg_restore": "pg_restore"}

    copiar_dados(ferramentas, ORIGEM, DESTINO, iniciar=fabrica)

    dump, restore = fabrica.processos
    for processo, senha in ((dump, "senha-da-origem"), (restore, "senha-local")):
        assert senha not in " ".join(processo.comando)
        assert processo.opcoes["env"]["PGPASSWORD"] == senha
    assert "--format=custom" in dump.comando
    assert "--no-owner" in restore.comando
    assert "--dbname=luft_web" in restore.comando


def test_comandos_nao_tem_senha_no_repr_do_servidor() -> None:
    assert "senha-local" not in repr(DESTINO)
    assert "senha-da-origem" not in " ".join(comando_dump("pg_dump", ORIGEM))
    assert "senha-local" not in " ".join(comando_restore("pg_restore", DESTINO))


def test_falha_do_dump_e_do_restore_sao_reportadas() -> None:
    ferramentas = {"pg_dump": "pg_dump", "pg_restore": "pg_restore"}

    with pytest.raises(ErroEspelho, match="pg_dump falhou"):
        copiar_dados(
            ferramentas, ORIGEM, DESTINO, iniciar=FabricaDeProcessos((1, 0), b"sem permissao")
        )
    with pytest.raises(ErroEspelho, match="pg_restore falhou"):
        copiar_dados(ferramentas, ORIGEM, DESTINO, iniciar=FabricaDeProcessos((0, 1), b"erro x"))


def _erro_restore(*linhas: str) -> bytes:
    return os.linesep.join(linhas).encode("utf-8")


ERRO_ROLE_DBA = 'pg_restore: error: could not execute query: ERROR:  role "dba" does not exist'


def test_grant_para_role_inexistente_e_tolerado_e_informado() -> None:
    ferramentas = {"pg_dump": "pg_dump", "pg_restore": "pg_restore"}
    erro = _erro_restore(
        ERRO_ROLE_DBA,
        "Command was: GRANT SELECT ON TABLE core.tb_sistema TO dba;",
        "pg_restore: warning: errors ignored on restore: 1",
    )

    ignoradas = copiar_dados(ferramentas, ORIGEM, DESTINO, iniciar=FabricaDeProcessos((0, 1), erro))

    assert ignoradas == ("dba",)


def test_outro_erro_do_restore_continua_sendo_falha() -> None:
    ferramentas = {"pg_dump": "pg_dump", "pg_restore": "pg_restore"}
    erro = _erro_restore(
        ERRO_ROLE_DBA,
        'pg_restore: error: could not execute query: ERROR:  relation "x" already exists',
    )

    with pytest.raises(ErroEspelho, match="pg_restore falhou"):
        copiar_dados(ferramentas, ORIGEM, DESTINO, iniciar=FabricaDeProcessos((0, 1), erro))


# --- Ferramentas ---------------------------------------------------------------------------


def test_localizar_ferramentas_prefere_a_pasta_informada(tmp_path: Path) -> None:
    for nome in ("pg_dump.exe", "pg_restore.exe"):
        (tmp_path / nome).write_text("", encoding="utf-8")

    achadas = localizar_ferramentas(tmp_path, procurar=lambda _: "/usr/bin/outro")

    assert achadas["pg_dump"].endswith("pg_dump.exe")
    assert Path(achadas["pg_restore"]).parent == tmp_path


def test_localizar_ferramentas_usa_a_instalacao_de_maior_versao(tmp_path: Path) -> None:
    for versao in ("15", "17", "16"):
        pasta = tmp_path / versao / "bin"
        pasta.mkdir(parents=True)
        for nome in ("pg_dump.exe", "pg_restore.exe"):
            (pasta / nome).write_text("", encoding="utf-8")

    achadas = localizar_ferramentas(
        None, procurar=lambda _: None, pastas_instalacao=[str(tmp_path)]
    )

    assert f"{Path('17') / 'bin'}" in achadas["pg_dump"]


def test_ferramenta_ausente_explica_o_que_fazer() -> None:
    with pytest.raises(ErroEspelho, match="--pg-bin"):
        localizar_ferramentas(None, procurar=lambda _: None, pastas_instalacao=[])


# --- Roles ---------------------------------------------------------------------------------


def test_le_so_roles_de_aplicacao_com_scram() -> None:
    conexao = ConexaoFalsa(roles=[("luft_control_hml_app", VERIFICADOR)])

    roles = ler_roles_aplicacao(conexao)

    assert roles == [RoleAplicacao("luft_control_hml_app", VERIFICADOR)]
    consulta = conexao.comandos[0][0]
    assert "NOT rolsuper" in consulta and "rolcanlogin" in consulta


def test_role_com_senha_md5_interrompe_o_espelho() -> None:
    conexao = ConexaoFalsa(roles=[("luft_antiga_app", "md5abcdef")])

    with pytest.raises(ErroEspelho, match="SCRAM"):
        ler_roles_aplicacao(conexao)


def test_role_nova_e_criada_e_existente_mantem_a_senha_local() -> None:
    pytest.importorskip("psycopg")
    nova = ConexaoFalsa()
    existente = ConexaoFalsa()
    existente.role_existe = True
    role = RoleAplicacao("luft_web_owner", VERIFICADOR)

    assert aplicar_roles(nova, [role]) == []
    assert aplicar_roles(existente, [role]) == ["luft_web_owner"]

    assert "CREATE ROLE" in nova.comandos[-1][0]
    assert VERIFICADOR in nova.comandos[-1][0]
    assert not any("ROLE" in c[0] and "PASSWORD" in c[0] for c in existente.comandos)


def test_sobrescrever_senhas_faz_alter_role() -> None:
    pytest.importorskip("psycopg")
    existente = ConexaoFalsa()
    existente.role_existe = True

    aplicar_roles(
        existente, [RoleAplicacao("luft_web_owner", VERIFICADOR)], sobrescrever_senhas=True
    )

    assert "ALTER ROLE" in existente.comandos[-1][0]


# --- Banco local ---------------------------------------------------------------------------


def test_banco_existente_exige_recriar() -> None:
    pytest.importorskip("psycopg")
    conexao = ConexaoFalsa()
    conexao.banco_existe = True

    with pytest.raises(ErroEspelho, match="--recriar"):
        recriar_banco(conexao, "luft_web", apagar_existente=False)
    assert not any("DROP" in c[0] for c in conexao.comandos)


def test_recriar_derruba_conexoes_apaga_e_cria() -> None:
    pytest.importorskip("psycopg")
    conexao = ConexaoFalsa()
    conexao.banco_existe = True

    assert recriar_banco(conexao, "luft_web", apagar_existente=True) is True

    textos = [c[0] for c in conexao.comandos]
    assert any("pg_terminate_backend" in t for t in textos)
    assert textos.index(next(t for t in textos if "DROP DATABASE" in t)) < textos.index(
        next(t for t in textos if "CREATE DATABASE" in t)
    )


def test_espelhar_orquestra_roles_banco_e_dados() -> None:
    pytest.importorskip("psycopg")
    origem = ConexaoFalsa(roles=[("luft_control_hml_app", VERIFICADOR)])
    destino = ConexaoFalsa()
    banco_local = ConexaoFalsa()
    conexoes = {"luft_web": origem, "postgres": destino, "luft_web_dev": banco_local}
    fabrica = FabricaDeProcessos()
    etapas: list[str] = []

    resultado = espelhar(
        ORIGEM,
        Servidor("localhost", 5432, "luft_web_dev", "postgres", "senha-local"),
        ferramentas={"pg_dump": "pg_dump", "pg_restore": "pg_restore"},
        recriar=False,
        conectar=lambda _servidor, banco: conexoes[banco],
        iniciar=fabrica,
        ao_etapa=etapas.append,
    )

    assert resultado.roles == ("luft_control_hml_app",)
    assert resultado.recriado is False
    assert len(fabrica.processos) == 2
    assert any("CREATE DATABASE" in c[0] for c in destino.comandos)
    assert len(etapas) == 5
    assert any("SELECT rolname FROM pg_roles" in c[0] for c in banco_local.comandos)


def test_espelhar_recusa_destino_remoto_antes_de_conectar() -> None:
    def nunca(*_: object) -> None:
        raise AssertionError("nao deveria conectar")

    with pytest.raises(ErroEspelho):
        espelhar(
            ORIGEM,
            Servidor("172.19.85.111", 5432, "luft_web", "postgres", "x"),
            ferramentas={},
            recriar=False,
            conectar=nunca,
        )


# --- .env ----------------------------------------------------------------------------------


def test_configurar_env_acrescenta_e_depois_atualiza(tmp_path: Path) -> None:
    arquivo = tmp_path / ".env"
    arquivo.write_text("LUFT_SISTEMA_ID=3\nPORT=9000\n", encoding="utf-8")

    assert configurar_env(arquivo, DESTINO) is True
    assert configurar_env(arquivo, DESTINO) is False
    outro = Servidor("127.0.0.1", 5433, "luft_web", "postgres", "x")
    assert configurar_env(arquivo, outro) is True

    texto = arquivo.read_text(encoding="utf-8")
    assert texto.count("LUFT_BANCO_LOCAL_HOST=") == 1
    assert "LUFT_BANCO_LOCAL_HOST=127.0.0.1" in texto
    assert "LUFT_BANCO_LOCAL_PORTA=5433" in texto
    assert "LUFT_SISTEMA_ID=3" in texto


# --- Configuracao: LUFT_BANCO_LOCAL_* ------------------------------------------------------

BASE = {
    "LUFT_SISTEMA_ID": "1",
    "LUFT_AMBIENTE": "homologacao",
    "LUFT_VAULT_ENDERECO": "http://vault:8200",
    "LUFT_LDAP_SERVIDOR": "ad.luft.interno",
    "LUFT_LDAP_DOMINIO": "LUFTFARMA",
}
CREDENCIAL = CredencialBanco(
    tipo=TipoBanco.POSTGRESQL,
    host="172.19.85.111",
    porta=5432,
    nome_banco="luft_web",
    usuario="luft_control_hml_app",
    senha=Segredo("segredo"),
    esquema="control",
)


def test_sem_banco_local_a_credencial_nao_muda() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(BASE)

    assert configuracao.banco_local is None
    assert configuracao.aplicar_banco_local(CREDENCIAL) is CREDENCIAL


def test_nome_local_padrao_troca_o_sufixo_do_ambiente() -> None:
    from luftbase.infraestrutura.espelho_banco import nome_local_padrao

    assert nome_local_padrao("luft_web_hml") == "luft_web_dev"
    assert nome_local_padrao("luft_web") == "luft_web_dev"
    assert nome_local_padrao("luft_web_dev") == "luft_web_dev"


def test_banco_local_pode_trocar_o_nome_do_banco() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {**BASE, "LUFT_BANCO_LOCAL_HOST": "localhost", "LUFT_BANCO_LOCAL_NOME": "luft_web_dev"}
    )

    assert configuracao.aplicar_banco_local(CREDENCIAL).nome_banco == "luft_web_dev"


def test_banco_local_troca_so_host_e_porta() -> None:
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {**BASE, "LUFT_BANCO_LOCAL_HOST": "localhost", "LUFT_BANCO_LOCAL_PORTA": "5433"}
    )

    credencial = configuracao.aplicar_banco_local(CREDENCIAL)

    assert (credencial.host, credencial.porta) == ("localhost", 5433)
    assert credencial.usuario == CREDENCIAL.usuario
    assert credencial.senha is CREDENCIAL.senha
    assert credencial.esquema == "control"
    assert credencial.nome_banco == "luft_web"


def test_banco_local_recusa_host_remoto() -> None:
    with pytest.raises(ErroConfiguracao, match="LUFT_BANCO_LOCAL_HOST"):
        ConfiguracaoLuftBase.de_mapeamento({**BASE, "LUFT_BANCO_LOCAL_HOST": "172.19.85.111"})


def test_banco_local_recusa_producao() -> None:
    with pytest.raises(ErroConfiguracao, match="producao"):
        ConfiguracaoLuftBase.de_mapeamento(
            {**BASE, "LUFT_AMBIENTE": "producao", "LUFT_BANCO_LOCAL_HOST": "localhost"}
        )


# --- CLI -----------------------------------------------------------------------------------


def _sessao_de_origem() -> SessaoOperador:
    destino = DestinoProvisionamento(
        ambiente="homologacao",
        namespace="luft",
        vault_url="http://vault:8200",
        host="172.19.85.111",
        porta=5432,
        banco="luft_web",
        sistema_referencia=0,
    )

    class ProvisionadorMudo:
        def encerrar(self) -> None:
            return None

    return SessaoOperador(
        ProvisionadorMudo(),  # type: ignore[arg-type]
        destino,
        "",
        "admin",
        Segredo("senha-da-origem"),
    )


def test_cli_recusa_destino_remoto_sem_pedir_credenciais() -> None:
    resultado = CliRunner().invoke(
        cli, ["banco", "espelhar", "--destino-host", "172.19.85.111", "--sim"]
    )

    assert resultado.exit_code != 0
    assert "propria maquina" in resultado.output


def test_cli_recusa_producao_como_origem() -> None:
    resultado = CliRunner().invoke(cli, ["banco", "espelhar", "--origem", "producao"])

    assert resultado.exit_code != 0


def test_cli_espelha_e_configura_o_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULO_BANCO, "_conectar_postgresql", lambda *_: None)
    chamadas: dict[str, Any] = {}

    def espelho_falso(origem: Servidor, destino: Servidor, **opcoes: Any) -> Any:
        chamadas["origem"], chamadas["destino"], chamadas["opcoes"] = origem, destino, opcoes
        opcoes["ao_etapa"]("feito")
        from luftbase.infraestrutura.espelho_banco import ResultadoEspelho

        return ResultadoEspelho(destino.banco, ("luft_control_hml_app",), False)

    monkeypatch.setattr(
        "luftbase.cli.operador.abrir_sessao_operador", lambda **_: _sessao_de_origem()
    )
    monkeypatch.setattr("luftbase.infraestrutura.espelho_banco.espelhar", espelho_falso)
    monkeypatch.setattr(
        "luftbase.infraestrutura.espelho_banco.localizar_ferramentas",
        lambda _pasta=None: {"pg_dump": "pg_dump", "pg_restore": "pg_restore"},
    )
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "senha-local")
    env = tmp_path / ".env"
    env.write_text("LUFT_SISTEMA_ID=3\n", encoding="utf-8")

    resultado = CliRunner().invoke(
        cli, ["banco", "espelhar", "--sim", "--sem-vault", "--configurar-env", str(env)]
    )

    assert resultado.exit_code == 0, resultado.output
    assert chamadas["origem"].host == "172.19.85.111"
    assert chamadas["destino"].host == "localhost"
    assert chamadas["destino"].banco == "luft_web_dev"
    assert chamadas["opcoes"]["recriar"] is False
    assert "senha-local" not in resultado.output and "senha-da-origem" not in resultado.output
    assert "LUFT_BANCO_LOCAL_HOST=localhost" in env.read_text(encoding="utf-8")
    assert "somente leitura" in resultado.output


def test_via_wsl_prefixa_comando_e_repassa_senha_so_por_ambiente() -> None:
    from luftbase.infraestrutura.espelho_banco import PREFIXO_WSL

    fabrica = FabricaDeProcessos((0, 0), b"")
    copiar_dados(
        {"pg_dump": "pg_dump", "pg_restore": "pg_restore"},
        ORIGEM,
        DESTINO,
        iniciar=fabrica,
        via_wsl=True,
    )

    assert len(fabrica.processos) == 2
    for processo in fabrica.processos:
        assert tuple(processo.comando[:2]) == PREFIXO_WSL
        assert "PGPASSWORD" in processo.opcoes["env"]["WSLENV"]
        assert ORIGEM.senha not in " ".join(processo.comando)
        assert DESTINO.senha not in " ".join(processo.comando)


def test_ferramentas_no_wsl_ausentes_orientam_a_instalar() -> None:
    from types import SimpleNamespace

    from luftbase.infraestrutura.espelho_banco import ferramentas_no_wsl

    with pytest.raises(ErroEspelho, match="postgresql-client"):
        ferramentas_no_wsl(lambda *_a, **_k: SimpleNamespace(returncode=1))
    assert set(ferramentas_no_wsl(lambda *_a, **_k: SimpleNamespace(returncode=0))) == {
        "pg_dump",
        "pg_restore",
    }


def test_parametro_novo_do_pg_dump_e_tolerado_com_aviso() -> None:
    erro = _erro_restore(
        'pg_restore: error: could not execute query: ERROR:  unrecognized configuration parameter "transaction_timeout"',
        "Command was: SET transaction_timeout = 0;",
        "pg_restore: warning: errors ignored on restore: 1",
    )
    avisos: list[str] = []

    ignoradas = copiar_dados(
        {"pg_dump": "pg_dump", "pg_restore": "pg_restore"},
        ORIGEM,
        DESTINO,
        iniciar=FabricaDeProcessos((0, 1), erro),
        avisos=avisos,
    )

    assert ignoradas == ()
    assert "transaction_timeout" in avisos[0]


def test_somente_estrutura_usa_schema_only_no_dump() -> None:
    from luftbase.infraestrutura.espelho_banco import comando_dump

    assert "--schema-only" in comando_dump("pg_dump", ORIGEM, somente_estrutura=True)
    assert "--schema-only" not in comando_dump("pg_dump", ORIGEM)


class CursorRolesDev:
    """Cursor que responde a lista de roles `_dev_app` e quais schemas existem."""

    def __init__(self, roles: list[str], schemas: set[str], comandos: list[str]) -> None:
        self.roles, self.schemas, self.comandos = roles, schemas, comandos
        self._schema: str | None = None

    def __enter__(self) -> CursorRolesDev:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, consulta: Any, parametros: Any = None) -> None:
        texto = consulta if isinstance(consulta, str) else consulta.as_string(None)
        self.comandos.append(texto)
        self._schema = parametros[0] if parametros and "pg_namespace" in texto else None

    def fetchall(self) -> list[tuple[str]]:
        return [(r,) for r in self.roles]

    def fetchone(self) -> tuple[int] | None:
        return (1,) if self._schema in self.schemas else None


class ConexaoRolesDev:
    def __init__(self, roles: list[str], schemas: set[str]) -> None:
        self.comandos: list[str] = []
        self._cursor = CursorRolesDev(roles, schemas, self.comandos)

    def cursor(self) -> CursorRolesDev:
        return self._cursor


def test_roles_dev_locais_ganham_acesso_ao_schema_restaurado() -> None:
    pytest.importorskip("psycopg")
    from luftbase.infraestrutura.espelho_banco import conceder_acesso_roles_dev

    conexao = ConexaoRolesDev(["luft_faturas_dev_app", "luft_orfao_dev_app"], {"faturas"})

    atendidas, sem_schema = conceder_acesso_roles_dev(conexao)

    assert atendidas == ["luft_faturas_dev_app"]
    assert sem_schema == ["luft_orfao_dev_app"]
    grants = [c for c in conexao.comandos if c.startswith(("GRANT", "ALTER DEFAULT"))]
    assert 'GRANT ALL ON ALL TABLES IN SCHEMA "faturas" TO "luft_faturas_dev_app"' in grants
    assert 'GRANT USAGE ON SCHEMA core TO "luft_faturas_dev_app"' in grants
    assert not any("orfao" in g for g in grants)


def test_cli_espelha_tambem_o_vault_de_desenvolvimento(monkeypatch: pytest.MonkeyPatch) -> None:
    from luftbase.infraestrutura import cadastro_sistema, espelho_vault
    from luftbase.infraestrutura.espelho_vault import ResultadoVault, SistemaLocal

    class Conexao:
        def __enter__(self) -> Conexao:
            return self

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(MODULO_BANCO, "_conectar_postgresql", lambda *_: Conexao())
    sessao = _sessao_de_origem()
    sessao.provisionador.cliente_vault = object()  # type: ignore[misc]
    monkeypatch.setattr("luftbase.cli.operador.abrir_sessao_operador", lambda **_: sessao)
    monkeypatch.setattr(
        "luftbase.infraestrutura.espelho_banco.espelhar",
        lambda origem, destino, **_: __import__(
            "luftbase.infraestrutura.espelho_banco", fromlist=["ResultadoEspelho"]
        ).ResultadoEspelho(destino.banco, (), False),
    )
    monkeypatch.setattr(
        "luftbase.infraestrutura.espelho_banco.localizar_ferramentas",
        lambda _pasta=None: {"pg_dump": "pg_dump", "pg_restore": "pg_restore"},
    )
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "senha-local")
    dev = DestinoProvisionamento(
        "desenvolvimento",
        "luft",
        "http://v",
        "172.19.85.111",
        5432,
        "luft_web",
        0,
        alias_conexao="luft-web",
    )
    monkeypatch.setattr(cadastro_sistema, "descobrir_destino_core", lambda *_a, **_k: dev)
    monkeypatch.setattr(
        espelho_vault,
        "ler_sistemas_locais",
        lambda _c: [SistemaLocal(0, "Luft-Workspace", "workspace")],
    )
    recebido: dict[str, Any] = {}

    def vault_falso(provisionador: Any, sistemas: Any, alias: str, **opcoes: Any) -> ResultadoVault:
        recebido.update(ambiente=provisionador.ambiente, alias=alias, sistemas=list(sistemas))
        return ResultadoVault([0], [], [], [])

    monkeypatch.setattr(espelho_vault, "espelhar_vault", vault_falso)

    resultado = CliRunner().invoke(cli, ["banco", "espelhar", "--sim"])

    assert resultado.exit_code == 0, resultado.output
    assert recebido["ambiente"] == "desenvolvimento" and recebido["alias"] == "luft-web"
    assert "vault_espelhado=criados:1" in resultado.output
    # A conexao do Vault aponta para luft_web, e o espelho se chama luft_web_dev: o aviso e obrigatorio.
    assert "aviso=a conexao 'luft-web'" in resultado.output
    assert "senha-local" not in resultado.output
