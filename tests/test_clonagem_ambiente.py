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


PRIVILEGIOS_ORIGEM: dict[str, dict[str, list[tuple[Any, ...]]]] = {
    "luft_workspace_app": {
        "schema": [("workspace", "USAGE", False)],
        "relacao": [
            ("workspace", "tb_a", "r", "SELECT", False),
            ("workspace", "seq_a", "S", "USAGE", False),
        ],
        "funcao": [("workspace", "fn_x", "integer", "f", "EXECUTE", False)],
        "padrao": [
            ("dba_teste", "workspace", "r", "SELECT", False),
            ("outro_dono", "workspace", "r", "INSERT", False),
        ],
    },
    "luft_connectair_app": {
        "schema": [("connectair", "USAGE", True)],
        "relacao": [("connectair", "tb_b", "r", "SELECT", False)],
        "funcao": [],
        "padrao": [],
    },
}


class CursorFalso:
    """Responde por consulta, como o catalogo faria. `resultados` forca uma fila simples."""

    def __init__(
        self,
        resultados: list[list[tuple[Any, ...]]] | None = None,
        *,
        existentes: tuple[str, ...] = (),
        pode_criar: bool = True,
        efetivo: bool = True,
    ) -> None:
        self.comandos: list[str] = []
        self._fila = list(resultados) if resultados is not None else None
        self._existentes = existentes
        self._pode_criar = pode_criar
        self._efetivo = efetivo
        self._atual: list[tuple[Any, ...]] = []

    def __enter__(self) -> CursorFalso:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, consulta: Any, parametros: Any = None) -> None:
        texto = consulta.as_string(None) if hasattr(consulta, "as_string") else str(consulta)
        texto = " ".join(texto.split())
        self.comandos.append(texto)
        self._atual = [] if self._fila is not None else self._responder(texto, parametros)

    def _responder(self, texto: str, parametros: Any) -> list[tuple[Any, ...]]:
        if "pg_auth_members" in texto:
            return [("luft_workspace_app", "luft_workspace_rw")]
        if "FROM pg_catalog.pg_roles WHERE rolname = ANY" in texto:
            return [(nome,) for nome in self._existentes]
        if texto == "SELECT current_user":
            return [("dba_teste",)]
        if "rolsuper OR rolcreaterole" in texto:
            return [(self._pode_criar,)]
        if "has_database_privilege" in texto:
            return [(True,)]
        if "aclexplode" in texto and parametros:
            role = str(parametros[0])
            origem = role.replace("_hml_app", "_app")
            if role != origem and not self._efetivo:
                return []
            dados = PRIVILEGIOS_ORIGEM.get(origem)
            if dados is None:
                return []
            for chave, marca in (
                ("schema", "n.nspacl"),
                ("relacao", "c.relacl"),
                ("funcao", "p.proacl"),
                ("padrao", "pg_default_acl"),
            ):
                if marca in texto:
                    return list(dados[chave])
        return []

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._fila is not None:
            return self._fila.pop(0) if self._fila else []
        return list(self._atual)

    def fetchone(self) -> tuple[Any, ...] | None:
        lista = self.fetchall()
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

    def __enter__(self) -> ConexaoFalsa:
        return self

    def __exit__(self, *_: object) -> None:
        return None


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
    def __init__(
        self, existentes: tuple[str, ...], pode_criar: bool = True, efetivo: bool = True
    ) -> None:
        self.cursor_falso = CursorFalso(
            existentes=existentes, pode_criar=pode_criar, efetivo=efetivo
        )

    def connect(self, **opcoes: Any) -> ConexaoFalsa:
        self.opcoes = opcoes
        return ConexaoFalsa(self.cursor_falso)


def _preparar(  # type: ignore[no-untyped-def]
    monkeypatch,
    kv2: Kv2Falso,
    existentes: list[str] | None = None,
    *,
    pode_criar: bool = True,
    efetivo: bool = True,
) -> PsycopgFalso:
    import psycopg

    modulo = sys.modules["luftbase.cli.vault"]
    monkeypatch.setattr(modulo, "_solicitar_segredo", lambda rotulo: "segredo")
    monkeypatch.setattr(modulo, "_criar_cliente_hvac_operador", lambda *a: ClienteFalso(kv2))
    falso = PsycopgFalso(tuple(existentes or ()), pode_criar, efetivo)
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
    "--postgres-admin",
    "dba_teste",
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
    assert "Sem privilegios sobre os dados, o risco e baixo" in resultado.output
    assert "TODAS as roles que usam esse banco" in resultado.output
    # O comando nunca deve sugerir um GRANT pronto que deixe roles de fora.
    assert "GRANT CONNECT ON DATABASE luft_web TO" not in resultado.output
    assert 'CREATE ROLE "luft_workspace_hml_app"' in " ".join(falso.cursor_falso.comandos)


def test_cli_confirmacao_errada_nao_grava(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    _preparar(monkeypatch, kv2)

    resultado = CliRunner().invoke(cli, [*_ARGS, "--executar"], input="sim\n")

    assert resultado.exit_code != 0
    assert not [e for e in kv2.escritas if e[0].startswith("luft/homologacao")]


def test_cli_pergunta_o_usuario_administrativo_quando_nao_informado(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    falso = _preparar(monkeypatch, _vault_producao())
    sem_usuario = [a for a in _ARGS if a not in ("--postgres-admin", "dba_teste")]

    resultado = CliRunner().invoke(cli, sem_usuario, input="dba_maria\n")

    assert resultado.exit_code == 0, resultado.output
    assert "Usuario administrativo do PostgreSQL" in resultado.output
    assert falso.opcoes["user"] == "dba_maria"


def test_cli_usa_o_usuario_informado_sem_perguntar(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    falso = _preparar(monkeypatch, _vault_producao())

    resultado = CliRunner().invoke(cli, _ARGS)

    assert resultado.exit_code == 0, resultado.output
    assert "Usuario administrativo do PostgreSQL" not in resultado.output
    assert falso.opcoes["user"] == "dba_teste"


# ---- Privilegios diretos ------------------------------------------------------


def _privilegios_destino() -> dict[str, list[Any]]:
    from luftbase.infraestrutura.cofre import privilegios

    cursor = CursorFalso()
    return {
        "luft_workspace_hml_app": list(
            privilegios.consultar_privilegios(cursor, "luft_workspace_app")
        ),
        "luft_connectair_hml_app": list(
            privilegios.consultar_privilegios(cursor, "luft_connectair_app")
        ),
    }


def test_le_privilegios_diretos_de_schema_tabela_sequence_funcao_e_padrao() -> None:
    from luftbase.infraestrutura.cofre import privilegios

    lidos = privilegios.consultar_privilegios(CursorFalso(), "luft_workspace_app")

    assert {p.categoria for p in lidos} == {"SCHEMA", "TABLE", "SEQUENCE", "FUNCTION", "DEFAULT"}
    assert privilegios.resumo_por_categoria(lidos) == {
        "DEFAULT": 2,
        "FUNCTION": 1,
        "SCHEMA": 1,
        "SEQUENCE": 1,
        "TABLE": 1,
    }


def test_padroes_de_outro_dono_nao_sao_aplicaveis() -> None:
    from luftbase.infraestrutura.cofre import privilegios

    lidos = privilegios.consultar_privilegios(CursorFalso(), "luft_workspace_app")
    aplicaveis, ignorados = privilegios.separar_padroes(lidos, "dba_teste")

    assert [p.objeto[0] for p in ignorados] == ["outro_dono"]
    assert all(p.categoria != "DEFAULT" or p.objeto[0] == "dba_teste" for p in aplicaveis)


def test_comando_grant_para_cada_categoria() -> None:
    from luftbase.infraestrutura.cofre.privilegios import Privilegio, comando_grant

    def texto(item: Privilegio) -> str:
        return " ".join(comando_grant(item, "nova").as_string(None).split())

    assert texto(Privilegio("SCHEMA", ("s",), "USAGE", True)) == (
        'GRANT USAGE ON SCHEMA "s" TO "nova" WITH GRANT OPTION'
    )
    assert texto(Privilegio("TABLE", ("s", "t"), "SELECT")) == (
        'GRANT SELECT ON TABLE "s"."t" TO "nova"'
    )
    assert texto(Privilegio("SEQUENCE", ("s", "q"), "USAGE")) == (
        'GRANT USAGE ON SEQUENCE "s"."q" TO "nova"'
    )
    assert texto(Privilegio("FUNCTION", ("s", "f", "integer, text"), "EXECUTE")) == (
        'GRANT EXECUTE ON FUNCTION "s"."f"(integer, text) TO "nova"'
    )
    assert texto(Privilegio("PROCEDURE", ("s", "p", ""), "EXECUTE")) == (
        'GRANT EXECUTE ON PROCEDURE "s"."p"() TO "nova"'
    )
    assert texto(Privilegio("DEFAULT", ("dono", "s", "r"), "SELECT")) == (
        'ALTER DEFAULT PRIVILEGES FOR ROLE "dono" IN SCHEMA "s" GRANT SELECT ON TABLES TO "nova"'
    )
    assert texto(Privilegio("DEFAULT", ("dono", "", "S"), "USAGE")) == (
        'ALTER DEFAULT PRIVILEGES FOR ROLE "dono" GRANT USAGE ON SEQUENCES TO "nova"'
    )


def test_comando_grant_rejeita_privilegio_suspeito() -> None:
    from luftbase.infraestrutura.cofre.privilegios import Privilegio, comando_grant

    with pytest.raises(ErroConfiguracao, match="inesperado"):
        comando_grant(Privilegio("TABLE", ("s", "t"), "SELECT; DROP TABLE x"), "nova")


def test_criar_roles_replica_privilegios_diretos_na_role_nova_e_nunca_na_origem() -> None:
    plano = _plano()
    cursor = CursorFalso()

    nao_concedidos = clonagem.criar_roles(
        ConexaoFalsa(cursor), plano, clonagem.gerar_senhas(plano), _privilegios_destino()
    )

    comandos = cursor.comandos
    assert nao_concedidos == {}
    assert 'GRANT USAGE ON SCHEMA "workspace" TO "luft_workspace_hml_app"' in comandos
    assert 'GRANT SELECT ON TABLE "workspace"."tb_a" TO "luft_workspace_hml_app"' in comandos
    assert 'GRANT USAGE ON SEQUENCE "workspace"."seq_a" TO "luft_workspace_hml_app"' in comandos
    assert (
        'GRANT EXECUTE ON FUNCTION "workspace"."fn_x"(integer) TO "luft_workspace_hml_app"'
        in comandos
    )
    assert (
        'ALTER DEFAULT PRIVILEGES FOR ROLE "dba_teste" IN SCHEMA "workspace" '
        'GRANT SELECT ON TABLES TO "luft_workspace_hml_app"'
    ) in comandos
    assert 'GRANT USAGE ON SCHEMA "connectair" TO "luft_connectair_hml_app" WITH GRANT OPTION' in (
        comandos
    )
    # O padrao de outro dono nao pode ser aplicado por quem nao e esse dono.
    assert not any("outro_dono" in c and c.startswith("ALTER DEFAULT") for c in comandos)
    # Nada e concedido a (ou revogado de) roles da origem.
    assert not any(
        c.startswith("GRANT") and c.endswith('TO "luft_workspace_app"') for c in comandos
    )
    assert not any("REVOKE" in c for c in comandos)


def test_criar_roles_informa_privilegios_que_nao_foram_concedidos() -> None:
    plano = _plano()
    cursor = CursorFalso(efetivo=False)

    nao_concedidos = clonagem.criar_roles(
        ConexaoFalsa(cursor), plano, clonagem.gerar_senhas(plano), _privilegios_destino()
    )

    assert set(nao_concedidos) == {"luft_workspace_hml_app", "luft_connectair_hml_app"}
    assert len(nao_concedidos["luft_workspace_hml_app"]) == 5


def test_cli_mostra_privilegios_diretos_e_avisa_sobre_padroes_de_outro_dono(  # type: ignore[no-untyped-def]
    monkeypatch,
) -> None:
    _preparar(monkeypatch, _vault_producao())

    resultado = CliRunner().invoke(cli, _ARGS)

    assert resultado.exit_code == 0, resultado.output
    assert "privilegios diretos a copiar: 2 DEFAULT, 1 FUNCTION, 1 SCHEMA" in resultado.output
    assert "pertencem a outro dono e nao serao copiados" in resultado.output
    assert "administrador=dba_teste pode_criar_roles=sim" in resultado.output


def test_cli_recusa_executar_sem_permissao_para_criar_roles(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    kv2 = _vault_producao()
    falso = _preparar(monkeypatch, kv2, pode_criar=False)

    simulacao = CliRunner().invoke(cli, _ARGS)
    execucao = CliRunner().invoke(cli, [*_ARGS, "--executar"], input="x\n")

    assert simulacao.exit_code == 0, simulacao.output
    assert "pode_criar_roles=nao" in simulacao.output
    assert execucao.exit_code != 0
    assert "CREATEROLE" in execucao.output
    assert not [e for e in kv2.escritas if e[0].startswith("luft/homologacao")]
    assert not any(c.startswith("CREATE ROLE") for c in falso.cursor_falso.comandos)


def test_cli_avisa_quando_a_role_nova_nao_recebe_todos_os_privilegios(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _preparar(monkeypatch, _vault_producao(), efetivo=False)

    resultado = CliRunner().invoke(
        cli, [*_ARGS, "--executar"], input="CLONAR-PRODUCAO-HOMOLOGACAO\n"
    )

    assert resultado.exit_code == 0, resultado.output
    assert "nao recebeu 5 privilegio(s)" in resultado.output
    assert "Repita esses GRANTs com o dono dos objetos" in resultado.output
