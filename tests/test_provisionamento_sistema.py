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
        self, path: str, mount_point: str, cas: int, secret: dict[str, object]
    ) -> None:
        self.gravados.append((path, cas, secret))

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
