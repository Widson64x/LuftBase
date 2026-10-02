"""Clonagem de ambiente PostgreSQL/Vault: roles dedicadas, sem tocar na origem."""

from __future__ import annotations

import sys
from typing import Any

import pytest
from click.testing import CliRunner

from luftbase.cli import cli
from luftbase.infraestrutura.cofre import clonagem
from luftbase.nucleo.excecoes import ErroConfiguracao

CONEXAO = {
    "tipo_banco": "postgresql",
    "host": "172.19.85.111",
    "porta": "5432",
    "nome_banco": "luft_web",
    "sslmode": "prefer",
}
SISTEMAS = {
    "0": {
        "conexao": "luft-web",
        "esquema": "workspace",
        "identificador": "luft-workspace",
        "usuario": "luft_workspace_app",
        "senha": "SENHA-DE-PRODUCAO-0",
        "sistema_id": "0",
    },
    "1": {
        "conexao": "luft-web",
        "esquema": "connectair",
        "identificador": "luft-connectair",
        "usuario": "luft_connectair_app",
        "senha": "SENHA-DE-PRODUCAO-1",
        "sistema_id": "1",
    },
}


def _plano(**alteracoes: Any) -> clonagem.PlanoClonagem:
    argumentos: dict[str, Any] = {
        "ambiente_origem": "producao",
        "ambiente_destino": "homologacao",
        "banco_destino": "luft_web_hml",
    }
    argumentos.update(alteracoes)
    return clonagem.montar_plano({"luft-web": CONEXAO}, SISTEMAS, **argumentos)


def test_deriva_roles_dedicadas_sem_reaproveitar_a_origem() -> None:
    assert clonagem.derivar_usuario_destino("luft_workspace_app", "hml") == "luft_workspace_hml_app"
    assert clonagem.derivar_usuario_destino("etl_leitor", "hml") == "etl_leitor_hml"
    assert clonagem.sufixo_do_ambiente("producao") == "prd"


def test_plano_aponta_conexao_para_o_banco_destino_e_nao_carrega_senha() -> None:
    plano = _plano()

    assert plano.campos_conexao["nome_banco"] == "luft_web_hml"
    assert plano.campos_conexao["host"] == "172.19.85.111"
    assert plano.caminho_conexao_destino == ("luft/homologacao/bancos/postgresql/conexoes/luft-web")
    assert plano.roles_destino == ("luft_connectair_hml_app", "luft_workspace_hml_app")
    assert [s.caminho_destino for s in plano.sistemas] == [
        "luft/homologacao/bancos/postgresql/sistemas/0",
        "luft/homologacao/bancos/postgresql/sistemas/1",
    ]
    assert "senha" not in plano.sistemas[0].campos
    assert "SENHA-DE-PRODUCAO" not in repr(plano)
    assert plano.sistemas[0].usuario_origem == "luft_workspace_app"


def test_plano_permite_trocar_o_servidor() -> None:
    assert _plano(host_destino="10.0.0.9").campos_conexao["host"] == "10.0.0.9"


@pytest.mark.parametrize(
    ("alteracoes", "mensagem"),
    [
        ({"ambiente_destino": "producao"}, "diferentes"),
        ({"banco_destino": "luft_web"}, "mesmo da origem"),
        ({"banco_destino": "banco; DROP"}, "invalido"),
        ({"alias": "outra"}, "nao existe"),
    ],
)
def test_plano_rejeita_entradas_perigosas(alteracoes: dict[str, str], mensagem: str) -> None:
    with pytest.raises(ErroConfiguracao, match=mensagem):
        _plano(**alteracoes)


def test_plano_exige_alias_quando_ha_varias_conexoes() -> None:
    with pytest.raises(ErroConfiguracao, match="--conexao"):
        clonagem.montar_plano(
            {"a": CONEXAO, "b": CONEXAO},
            SISTEMAS,
            ambiente_origem="producao",
            ambiente_destino="homologacao",
            banco_destino="luft_web_hml",
        )


def test_senhas_sao_aleatorias_e_independentes_por_role() -> None:
    plano = _plano()

    primeira, segunda = clonagem.gerar_senhas(plano), clonagem.gerar_senhas(plano)

    assert set(primeira) == set(plano.roles_destino)
    assert len(set(primeira.values())) == 2
    assert primeira != segunda
    assert all("PRODUCAO" not in s for s in primeira.values())


class Kv2Falso:
    def __init__(self, existentes: dict[str, dict[str, str]] | None = None) -> None:
        self.dados = dict(existentes or {})
        self.escritas: list[tuple[str, dict[str, str], dict[str, Any]]] = []

    def list_secrets(self, path: str, mount_point: str) -> dict[str, Any]:
        prefixo = path + "/"
        chaves = sorted(c[len(prefixo) :] for c in self.dados if c.startswith(prefixo))
        return {"data": {"keys": chaves}}

    def read_secret_version(self, path: str, mount_point: str, **_: Any) -> dict[str, Any]:
        return {"data": {"data": self.dados[path]}}

    def read_secret_metadata(self, path: str, mount_point: str) -> dict[str, Any]:
        if path not in self.dados:
            from hvac import exceptions

            raise exceptions.InvalidPath()
        return {}

    def create_or_update_secret(
        self, path: str, mount_point: str, secret: dict[str, str], **opcoes: Any
    ) -> None:
        self.escritas.append((path, secret, opcoes))
        self.dados[path] = secret


class ClienteFalso:
    def __init__(self, kv2: Kv2Falso) -> None:
        self.secrets = type("S", (), {"kv": type("K", (), {"v2": kv2})()})()


def _vault_producao() -> Kv2Falso:
    base = "luft/producao/bancos/postgresql"
    dados = {f"{base}/conexoes/luft-web": dict(CONEXAO)}
    dados.update({f"{base}/sistemas/{i}": dict(s) for i, s in SISTEMAS.items()})
    return Kv2Falso(dados)


def test_le_conexoes_e_sistemas_da_origem() -> None:
    conexoes, sistemas = clonagem.ler_segredos_postgresql(
        ClienteFalso(_vault_producao()), "secret", "producao"
    )

    assert set(conexoes) == {"luft-web"}
    assert set(sistemas) == {"0", "1"}


def test_grava_destino_com_cas_zero_e_senha_nova_sem_copiar_a_da_origem() -> None:
    kv2 = Kv2Falso()
    plano = _plano()
    senhas = clonagem.gerar_senhas(plano)

    clonagem.gravar_segredos_destino(ClienteFalso(kv2), "secret", plano, senhas)

    assert all(opcoes == {"cas": 0} for _, _, opcoes in kv2.escritas)
    por_caminho = {caminho: segredo for caminho, segredo, _ in kv2.escritas}
    sistema0 = por_caminho["luft/homologacao/bancos/postgresql/sistemas/0"]
    assert sistema0["usuario"] == "luft_workspace_hml_app"
    assert sistema0["senha"] == senhas["luft_workspace_hml_app"]
    assert sistema0["senha"] != SISTEMAS["0"]["senha"]
    assert sistema0["esquema"] == "workspace"
    assert por_caminho["luft/homologacao/bancos/postgresql/conexoes/luft-web"]["nome_banco"] == (
        "luft_web_hml"
    )


def test_substituir_grava_nova_versao_sem_cas() -> None:
    kv2 = Kv2Falso()
    plano = _plano()

    clonagem.gravar_segredos_destino(
        ClienteFalso(kv2), "secret", plano, clonagem.gerar_senhas(plano), substituir=True
    )

    assert all(opcoes == {} for _, _, opcoes in kv2.escritas)


class CursorFalso:
    def __init__(self, resultados: list[list[tuple[Any, ...]]] | None = None) -> None:
        self.comandos: list[str] = []
        self._resultados = list(resultados or [])

    def __enter__(self) -> CursorFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, consulta: Any, parametros: Any = None) -> None:
        texto = consulta.as_string(None) if hasattr(consulta, "as_string") else str(consulta)
        self.comandos.append(" ".join(texto.split()))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._resultados.pop(0) if self._resultados else []

    def fetchone(self) -> tuple[Any, ...] | None:
        lista = self._resultados.pop(0) if self._resultados else []
        return lista[0] if lista else None


class PgConnFalso:
    def encrypt_password(self, senha: bytes, usuario: bytes, algoritmo: bytes) -> bytes:
        return b"SCRAM-SHA-256$verificador"


class ConexaoFalsa:
    def __init__(self, cursor: CursorFalso) -> None:
        self.cursor_falso = cursor
        self.pgconn = PgConnFalso()

    def transaction(self) -> CursorFalso:
        return self.cursor_falso

    def cursor(self) -> CursorFalso:
        return self.cursor_falso


def test_cria_somente_roles_de_destino_com_grupos_e_connect() -> None:
    plano = _plano().com_grupos(
        {
            "luft_workspace_app": ("luft_workspace_rw", "luft_core_ro"),
            "luft_connectair_app": ("luft_connectair_rw",),
        }
    )
    cursor = CursorFalso()

    clonagem.criar_roles(ConexaoFalsa(cursor), plano, clonagem.gerar_senhas(plano))

    comandos = cursor.comandos
    assert any(
        c.startswith('CREATE ROLE "luft_workspace_hml_app" LOGIN PASSWORD') for c in comandos
    )
    assert 'GRANT "luft_workspace_rw" TO "luft_workspace_hml_app"' in comandos
    assert 'GRANT "luft_core_ro" TO "luft_workspace_hml_app"' in comandos
    assert 'GRANT CONNECT ON DATABASE "luft_web_hml" TO "luft_connectair_hml_app"' in comandos
    # Nenhum comando pode citar uma role da origem como alvo de alteracao.
    assert not any("ALTER ROLE" in c or "DROP ROLE" in c for c in comandos)
    assert not any('TO "luft_workspace_app"' in c for c in comandos)
    assert "SENHA-DE-PRODUCAO" not in " ".join(comandos)


def test_consulta_grupos_e_roles_existentes() -> None:
    cursor = CursorFalso(
        [[("luft_workspace_app", "luft_workspace_rw"), ("luft_workspace_app", "luft_core_ro")]]
    )
    grupos = clonagem.consultar_grupos(cursor, ["luft_workspace_app"])
    assert grupos == {"luft_workspace_app": ("luft_core_ro", "luft_workspace_rw")}

    cursor = CursorFalso([[("luft_workspace_hml_app",)]])
    assert clonagem.consultar_roles_existentes(cursor, ["luft_workspace_hml_app"]) == {
        "luft_workspace_hml_app"
    }


def test_isolamento_aponta_roles_que_ainda_conectam_na_origem() -> None:
    plano = _plano()
    cursor = CursorFalso([[(True,)], [(False,)]])

    assert clonagem.roles_que_alcancam_a_origem(cursor, plano) == ["luft_connectair_hml_app"]


# ---- CLI -----------------------------------------------------------------


class PsycopgFalso:
    def __init__(self, existentes: list[str]) -> None:
        self.existentes = existentes
        self.cursor_falso = CursorFalso()

    def connect(self, **opcoes: Any) -> ConexaoFalsa:
        self.opcoes = opcoes
        return _ConexaoCtx(self)


class _ConexaoCtx(ConexaoFalsa):
    def __init__(self, base: PsycopgFalso) -> None:
        super().__init__(base.cursor_falso)
        self.base = base
        base.cursor_falso._resultados = [
            [("luft_workspace_app", "luft_workspace_rw")],
            [(r,) for r in base.existentes],
            [(True,)],
            [(True,)],
        ]

    def __enter__(self) -> _ConexaoCtx:
        return self

    def __exit__(self, *_: object) -> None:
        return None


def _preparar(monkeypatch, kv2: Kv2Falso, existentes: list[str] | None = None) -> PsycopgFalso:  # type: ignore[no-untyped-def]
    import psycopg

    modulo = sys.modules["luftbase.cli.vault"]
    monkeypatch.setattr(modulo, "_solicitar_segredo", lambda rotulo: "segredo")
    monkeypatch.setattr(modulo, "_criar_cliente_hvac_operador", lambda *a: ClienteFalso(kv2))
    falso = PsycopgFalso(existentes or [])
    monkeypatch.setattr(psycopg, "connect", falso.connect)
    return falso


_ARGS = [
    "vault",
    "postgresql",
    "clonar-ambiente",
    "--origem",
    "producao",
    "--destino",
    "homologacao",
    "--banco-destino",
    "luft_web_hml",
]


def test_cli_simula_por_padrao_e_nao_altera_nada(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    antes = len(kv2.escritas)
    falso = _preparar(monkeypatch, kv2)

    resultado = CliRunner().invoke(cli, _ARGS)

    assert resultado.exit_code == 0, resultado.output
    assert "luft_workspace_app -> luft_workspace_hml_app" in resultado.output
    assert "Simulacao concluida" in resultado.output
    assert len(kv2.escritas) == antes
    assert not any(c.startswith("CREATE ROLE") for c in falso.cursor_falso.comandos)
    assert "SENHA-DE-PRODUCAO" not in resultado.output


def test_cli_recusa_role_de_destino_ja_existente(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _preparar(monkeypatch, _vault_producao(), existentes=["luft_workspace_hml_app"])

    resultado = CliRunner().invoke(cli, [*_ARGS, "--executar"], input="x\n")

    assert resultado.exit_code != 0
    assert "ja existem e nao serao alteradas" in resultado.output


def test_cli_recusa_segredos_existentes_sem_substituir(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    kv2.dados["luft/homologacao/bancos/postgresql/conexoes/luft-web"] = dict(CONEXAO)
    _preparar(monkeypatch, kv2)

    resultado = CliRunner().invoke(cli, [*_ARGS, "--executar"], input="x\n")

    assert resultado.exit_code != 0
    assert "--substituir-segredos" in resultado.output
    assert not [e for e in kv2.escritas if e[0].startswith("luft/homologacao")]


def test_cli_executa_com_confirmacao_e_nao_imprime_senhas(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    falso = _preparar(monkeypatch, kv2)

    resultado = CliRunner().invoke(
        cli, [*_ARGS, "--executar"], input="CLONAR-PRODUCAO-HOMOLOGACAO\n"
    )

    assert resultado.exit_code == 0, resultado.output
    gravados = {c: s for c, s, _ in kv2.escritas}
    senha = gravados["luft/homologacao/bancos/postgresql/sistemas/0"]["senha"]
    assert senha not in resultado.output
    assert senha not in " ".join(falso.cursor_falso.comandos)
    assert "Roles criadas: luft_connectair_hml_app, luft_workspace_hml_app" in resultado.output
    assert "REVOKE CONNECT ON DATABASE luft_web FROM PUBLIC" in resultado.output
    assert 'CREATE ROLE "luft_workspace_hml_app"' in " ".join(falso.cursor_falso.comandos)


def test_cli_confirmacao_errada_nao_grava(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    _preparar(monkeypatch, kv2)

    resultado = CliRunner().invoke(cli, [*_ARGS, "--executar"], input="sim\n")

    assert resultado.exit_code != 0
    assert not [e for e in kv2.escritas if e[0].startswith("luft/homologacao")]
