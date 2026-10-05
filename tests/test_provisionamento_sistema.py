"""Provisionamento de sistema pela tela: nomes, credenciais, Vault e erros por campo."""

from __future__ import annotations

from typing import Any

import pytest

from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.provisionamento_sistema import (
    CredenciaisOperador,
    DestinoProvisionamento,
    ErroProvisionamento,
    PlanoSistema,
    ProvisionadorSistema,
    derivar_plano,
)
from luftbase.web.configuracoes import _ler_credenciais_operador

DESTINO = DestinoProvisionamento(
    ambiente="desenvolvimento",
    namespace="luft",
    vault_url="http://vault:8200",
    host="172.19.85.111",
    porta=5432,
    banco="luft_web",
    sistema_referencia=0,
)
CREDENCIAIS = CredenciaisOperador("admin", Segredo("token-operador"), Segredo("senha-admin"))


class InvalidPath(Exception):
    pass


class Kv2Falso:
    def __init__(self, segredos: dict[str, dict[str, object]]) -> None:
        self.segredos = segredos
        self.gravados: list[tuple[str, int, dict[str, object]]] = []
        self.removidos: list[str] = []

    def read_secret_version(self, path: str, mount_point: str, **_: object) -> dict[str, Any]:
        if path not in self.segredos:
            raise InvalidPath(path)
        return {"data": {"data": self.segredos[path]}}

    def read_secret_metadata(self, path: str, mount_point: str) -> dict[str, Any]:
        from hvac import exceptions

        if path not in self.segredos:
            raise exceptions.InvalidPath(path)
        return {"data": {}}

    def create_or_update_secret(
        self, path: str, mount_point: str, secret: dict[str, object], cas: int | None = None
    ) -> None:
        self.gravados.append((path, cas, secret))  # type: ignore[arg-type]

    def delete_metadata_and_all_versions(self, path: str, mount_point: str) -> None:
        self.removidos.append(path)


class VaultFalso:
    def __init__(self, kv2: Kv2Falso, autenticado: bool = True) -> None:
        self._autenticado = autenticado
        self.secrets = type("S", (), {"kv": type("K", (), {"v2": kv2})()})()

    def is_authenticated(self) -> bool:
        return self._autenticado


def _provisionador(kv2: Kv2Falso, autenticado: bool = True) -> ProvisionadorSistema:
    return ProvisionadorSistema(
        DESTINO, CREDENCIAIS, criar_cliente_vault=lambda *_: VaultFalso(kv2, autenticado)
    )


def test_nomes_seguem_a_convencao_do_bootstrap() -> None:
    plano = derivar_plano(1, "Luft-ConnectAir", "connectair")

    assert plano == PlanoSistema(1, "luft-connectair", "connectair", "luft_connectair_app")


def test_nome_iniciado_por_digito_gera_identificador_valido() -> None:
    assert derivar_plano(9, "360 Vendas", "vendas").identificador == "sistema-360-vendas"


def test_credenciais_nao_aparecem_em_repr() -> None:
    assert "token-operador" not in repr(CREDENCIAIS)
    assert "senha-admin" not in repr(CREDENCIAIS)


def test_token_recusado_aponta_o_campo_do_token() -> None:
    with pytest.raises(ErroProvisionamento) as erro:
        _provisionador(Kv2Falso({}), autenticado=False).verificar()

    assert erro.value.campo == "TokenOperadorVault"


def test_alias_vem_do_segredo_do_workspace() -> None:
    kv2 = Kv2Falso({"luft/desenvolvimento/bancos/postgresql/sistemas/0": {"conexao": "luft-web"}})

    assert _provisionador(kv2).alias_conexao() == "luft-web"


def test_segredo_novo_usa_cas_zero_e_convencao_do_bootstrap() -> None:
    kv2 = Kv2Falso({})
    provisionador = _provisionador(kv2)
    plano = derivar_plano(1, "Luft-ConnectAir", "connectair")

    caminho = provisionador.gravar_segredo(plano, "luft-web", Segredo("senha-da-role"))

    assert caminho == "luft/desenvolvimento/bancos/postgresql/sistemas/1"
    assert kv2.gravados == [
        (
            caminho,
            0,
            {
                "sistema_id": 1,
                "identificador": "luft-connectair",
                "conexao": "luft-web",
                "esquema": "connectair",
                "usuario": "luft_connectair_app",
                "senha": "senha-da-role",
            },
        )
    ]


def test_segredo_existente_e_detectado() -> None:
    kv2 = Kv2Falso({"luft/desenvolvimento/bancos/postgresql/sistemas/1": {"x": 1}})
    provisionador = _provisionador(kv2)

    assert provisionador.segredo_existe(1) is True
    assert provisionador.segredo_existe(2) is False


def test_formulario_exige_as_tres_credenciais() -> None:
    credenciais, erros = _ler_credenciais_operador({"UsuarioBanco": " "})

    assert credenciais is None
    assert set(erros) == {"TokenOperadorVault", "UsuarioBanco", "SenhaBanco"}


def test_formulario_completo_gera_credenciais_mascaradas() -> None:
    credenciais, erros = _ler_credenciais_operador(
        {"TokenOperadorVault": "t", "UsuarioBanco": "admin", "SenhaBanco": "s"}
    )

    assert erros == {}
    assert credenciais is not None
    assert credenciais.usuario_banco == "admin"
    assert credenciais.token_vault.revelar() == "t"


def test_parametro_da_aplicacao_valida_titulo_endpoint_e_icone() -> None:
    from luftbase import ParametroAplicacao
    from luftbase.nucleo import ErroConfiguracao

    assert ParametroAplicacao("Prioridade", "x", "Pagina.abrir").icone == "ph-bold ph-sliders"
    for invalido in (
        {"titulo": " ", "endpoint": "a.b"},
        {"titulo": "T", "endpoint": ""},
        {"titulo": "T", "endpoint": "a.b", "icone": "fa fa-home"},
    ):
        with pytest.raises(ErroConfiguracao):
            ParametroAplicacao(descricao="x", **invalido)  # type: ignore[arg-type]


def test_painel_lista_so_parametros_permitidos_e_ignora_rota_inexistente(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from flask import Flask

    from luftbase import ParametroAplicacao
    from luftbase.web import configuracoes

    app = Flask(__name__)
    app.add_url_rule("/cias", endpoint="Parametros.cias", view_func=lambda: "ok")
    app.add_url_rule("/fretes", endpoint="Parametros.fretes", view_func=lambda: "ok")
    monkeypatch.setattr(
        configuracoes, "consultar_permissoes", lambda chaves: {"APP.CIAS.VISUALIZAR": True}
    )
    parametros = (
        ParametroAplicacao("Cias", "d", "Parametros.cias", permissao="APP.CIAS.VISUALIZAR"),
        ParametroAplicacao("Fretes", "d", "Parametros.fretes", permissao="APP.FRETES.VISUALIZAR"),
        ParametroAplicacao("Livre", "d", "Parametros.fretes"),
        ParametroAplicacao("Quebrado", "d", "Parametros.naoexiste"),
    )

    with app.test_request_context():
        visiveis = configuracoes._parametros_visiveis(parametros)

    assert [p["titulo"] for p in visiveis] == ["Cias", "Livre"]
    assert visiveis[0]["url"] == "/cias"


# ---- Role por ambiente (a role e do cluster, nao do banco) ------------------------------------


def test_role_de_producao_nao_leva_sufixo_e_a_dos_demais_ambientes_leva() -> None:
    from luftbase.infraestrutura.provisionamento_sistema import nome_da_role

    assert nome_da_role("integrador", "producao") == "luft_integrador_app"
    assert nome_da_role("integrador", "homologacao") == "luft_integrador_hml_app"
    assert nome_da_role("integrador", "desenvolvimento") == "luft_integrador_dev_app"
    assert derivar_plano(3, "Luft-Integrador", "integrador", "homologacao").role == (
        "luft_integrador_hml_app"
    )
    # Sem ambiente informado o comportamento antigo (producao) e preservado.
    assert derivar_plano(3, "Luft-Integrador", "integrador").role == "luft_integrador_app"


def test_destino_informa_o_sufixo_da_role_para_a_tela() -> None:
    from dataclasses import replace

    assert replace(DESTINO, ambiente="homologacao").como_dict()["sufixo_role"] == "hml"
    assert replace(DESTINO, ambiente="producao").como_dict()["sufixo_role"] == ""


def test_provisionar_recusa_plano_de_outro_ambiente_antes_de_tocar_no_banco() -> None:
    provisionador = _provisionador(Kv2Falso({}))
    plano_producao = derivar_plano(3, "Luft-Integrador", "integrador", "producao")

    # O destino do teste e "desenvolvimento": um plano de producao nao pode ser aplicado nele.
    with pytest.raises(ErroProvisionamento, match="ambiente"):
        provisionador.provisionar_banco(plano_producao)


def test_provisionar_recusa_role_sem_o_sufixo_do_ambiente() -> None:
    from dataclasses import replace

    plano = replace(
        derivar_plano(3, "Luft-Integrador", "integrador", "desenvolvimento"),
        role="luft_integrador_app",
    )

    with pytest.raises(ErroProvisionamento, match="nao segue o nome"):
        _provisionador(Kv2Falso({})).provisionar_banco(plano)


def test_substituir_grava_nova_versao_sem_cas() -> None:
    kv2 = Kv2Falso({})
    plano = derivar_plano(3, "Luft-Integrador", "integrador", "desenvolvimento")

    _provisionador(kv2).gravar_segredo(plano, "luft-web", Segredo("x"), substituir=True)

    assert kv2.gravados[-1][1] is None
    assert kv2.gravados[-1][2]["usuario"] == "luft_integrador_dev_app"


# ---- Comando reprovisionar-sistema ----------------------------------------------------------


class ProvisionadorFalso:
    """Substitui o provisionador real: registra o que o comando pediria ao banco e ao Vault."""

    ultimo: ProvisionadorFalso | None = None

    def __init__(self, destino: DestinoProvisionamento, credenciais: object) -> None:
        self.destino = destino
        self.chamadas: list[str] = []
        self.gravado: dict[str, object] = {}
        ProvisionadorFalso.ultimo = self

    def verificar(self) -> None:
        self.chamadas.append("verificar")

    def segredo_existe(self, sistema_id: int) -> bool:
        return True

    def provisionar_banco(self, plano: PlanoSistema) -> tuple[Segredo, bool]:
        self.chamadas.append(f"provisionar:{plano.role}")
        return Segredo("senha-gerada-no-teste"), True

    def gravar_segredo(
        self, plano: PlanoSistema, alias: str, senha: Segredo, *, substituir: bool = False
    ) -> str:
        self.gravado = {"role": plano.role, "alias": alias, "substituir": substituir}
        return f"{self.destino.raiz_sistemas}/{plano.sistema_id}"

    def encerrar(self) -> None:
        self.chamadas.append("encerrar")


def _preparar_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    modulo = sys.modules["luftbase.cli.vault"]
    kv2 = Kv2Falso(
        {
            "luft/homologacao/bancos/postgresql/sistemas/0": {"conexao": "luft-web"},
            "luft/homologacao/bancos/postgresql/conexoes/luft-web": {
                "host": "db.interno",
                "porta": "5432",
                "nome_banco": "luft_web_hml",
            },
        }
    )
    cliente = type("C", (), {"secrets": type("S", (), {"kv": type("K", (), {"v2": kv2})()})()})()
    monkeypatch.setattr(modulo, "_solicitar_segredo", lambda rotulo: "segredo")
    monkeypatch.setattr(modulo, "_criar_cliente_hvac_operador", lambda *a: cliente)
    monkeypatch.setattr(
        "luftbase.infraestrutura.provisionamento_sistema.ProvisionadorSistema",
        ProvisionadorFalso,
    )


_ARGS_REPROVISIONAR = [
    "vault",
    "postgresql",
    "reprovisionar-sistema",
    "--ambiente",
    "homologacao",
    "--sistema-id",
    "3",
    "--nome",
    "Luft-Integrador",
    "--esquema",
    "integrador",
    "--postgres-admin",
    "dba_teste",
]


def test_cli_reprovisionar_simula_por_padrao(monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    from luftbase.cli import cli

    _preparar_cli(monkeypatch)

    resultado = CliRunner().invoke(cli, _ARGS_REPROVISIONAR)

    assert resultado.exit_code == 0, resultado.output
    assert "role=luft_integrador_hml_app" in resultado.output
    assert "banco=luft_web_hml" in resultado.output
    assert "Simulacao concluida" in resultado.output
    assert ProvisionadorFalso.ultimo is not None
    assert not any(c.startswith("provisionar") for c in ProvisionadorFalso.ultimo.chamadas)


def test_cli_reprovisionar_executa_com_a_role_do_ambiente_e_nova_versao(  # type: ignore[no-untyped-def]
    monkeypatch,
) -> None:
    from click.testing import CliRunner

    from luftbase.cli import cli

    _preparar_cli(monkeypatch)

    resultado = CliRunner().invoke(
        cli, [*_ARGS_REPROVISIONAR, "--executar"], input="REPROVISIONAR-HOMOLOGACAO-3\n"
    )

    assert resultado.exit_code == 0, resultado.output
    falso = ProvisionadorFalso.ultimo
    assert falso is not None
    assert "provisionar:luft_integrador_hml_app" in falso.chamadas
    assert falso.gravado == {
        "role": "luft_integrador_hml_app",
        "alias": "luft-web",
        "substituir": True,
    }
    assert "senha-gerada-no-teste" not in resultado.output


def test_cli_reprovisionar_confirmacao_errada_nao_altera_nada(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from click.testing import CliRunner

    from luftbase.cli import cli

    _preparar_cli(monkeypatch)

    resultado = CliRunner().invoke(cli, [*_ARGS_REPROVISIONAR, "--executar"], input="sim\n")

    assert resultado.exit_code != 0
    assert ProvisionadorFalso.ultimo is not None
    assert not any(c.startswith("provisionar") for c in ProvisionadorFalso.ultimo.chamadas)
    assert ProvisionadorFalso.ultimo.gravado == {}
