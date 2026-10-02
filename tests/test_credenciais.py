"""Testes da validacao de credenciais vindas do Vault."""

from collections.abc import Mapping

import pytest

from luftbase.infraestrutura.cofre.credenciais import Segredo, TipoBanco
from luftbase.infraestrutura.cofre.servico import CarregadorCredenciais
from luftbase.nucleo.excecoes import ErroConfiguracao, ErroCredencial


class ProvedorFalso:
    """Provedor deterministico, sem rede, usado pelos testes."""

    def __init__(self, dados: Mapping[str, object]) -> None:
        self.dados = dados
        self.caminhos_lidos: list[str] = []

    def validar_acesso(self) -> None:
        return None

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        self.caminhos_lidos.append(caminho)
        return self.dados


def _postgres(**alteracoes: object) -> dict[str, object]:
    dados: dict[str, object] = {
        "host": "postgres.interno",
        "nome_banco": "luft_web",
        "esquema": "luft_workspace",
        "porta": "5432",
        "senha": "nao-exibir",
        "tipo_banco": "postgresql",
        "usuario": "svc_luft_workspace",
    }
    dados.update(alteracoes)
    return dados


def _redis(**alteracoes: object) -> dict[str, object]:
    dados: dict[str, object] = {
        "host": "redis.interno",
        "porta": "6379",
        "banco": "0",
        "usuario": "svc_sessoes",
        "senha": "senha-redis",
        "tls": "true",
        "chave_assinatura_sessao": "x" * 64,
    }
    dados.update(alteracoes)
    return dados


def test_carrega_postgresql_com_esquema() -> None:
    provedor = ProvedorFalso(_postgres())

    credencial = CarregadorCredenciais(provedor).carregar_banco(
        "luft/desenvolvimento/postgresql/luft-workspace",
        TipoBanco.POSTGRESQL,
        exigir_esquema=True,
    )

    assert credencial.esquema == "luft_workspace"
    assert credencial.porta == 5432
    assert credencial.senha.revelar() == "nao-exibir"
    assert "nao-exibir" not in repr(credencial)
    assert provedor.caminhos_lidos == ["luft/desenvolvimento/postgresql/luft-workspace"]


def test_segredo_nunca_exibe_valor() -> None:
    segredo = Segredo("valor-supersecreto")

    assert str(segredo) == "********"
    assert "valor-supersecreto" not in repr(segredo)


@pytest.mark.parametrize("campo", ["host", "nome_banco", "porta", "senha", "usuario"])
def test_rejeita_campos_obrigatorios_ausentes(campo: str) -> None:
    provedor = ProvedorFalso(_postgres(**{campo: ""}))

    with pytest.raises(ErroCredencial, match=campo):
        CarregadorCredenciais(provedor).carregar_banco(
            "caminho",
            TipoBanco.POSTGRESQL,
            exigir_esquema=True,
        )


@pytest.mark.parametrize("porta", ["zero", "0", "65536"])
def test_rejeita_porta_invalida(porta: str) -> None:
    with pytest.raises(ErroCredencial, match="porta"):
        CarregadorCredenciais(ProvedorFalso(_postgres(porta=porta))).carregar_banco(
            "caminho",
            TipoBanco.POSTGRESQL,
            exigir_esquema=True,
        )


@pytest.mark.parametrize("usuario", ["admin", "POSTGRES", "sa"])
def test_rejeita_usuario_administrativo_em_runtime(usuario: str) -> None:
    with pytest.raises(ErroCredencial, match="administrativa"):
        CarregadorCredenciais(ProvedorFalso(_postgres(usuario=usuario))).carregar_banco(
            "caminho",
            TipoBanco.POSTGRESQL,
            exigir_esquema=True,
        )


def test_rejeita_tipo_diferente_do_esperado() -> None:
    with pytest.raises(ErroCredencial, match="tipo de banco esperado"):
        CarregadorCredenciais(ProvedorFalso(_postgres(tipo_banco="sqlserver"))).carregar_banco(
            "caminho", TipoBanco.POSTGRESQL, exigir_esquema=True
        )


def test_rejeita_esquema_reservado() -> None:
    with pytest.raises(ErroConfiguracao, match="reservado"):
        CarregadorCredenciais(ProvedorFalso(_postgres(esquema="core"))).carregar_banco(
            "caminho",
            TipoBanco.POSTGRESQL,
            exigir_esquema=True,
        )


def test_aceita_alias_mssql() -> None:
    dados = _postgres(tipo_banco="mssql", esquema="")

    credencial = CarregadorCredenciais(ProvedorFalso(dados)).carregar_banco(
        "caminho",
        TipoBanco.SQLSERVER,
    )

    assert credencial.tipo is TipoBanco.SQLSERVER


def test_carrega_redis_e_mascara_segredos() -> None:
    credencial = CarregadorCredenciais(ProvedorFalso(_redis())).carregar_redis(
        "luft/desenvolvimento/redis/sessoes"
    )

    assert credencial.porta == 6379
    assert credencial.banco == 0
    assert credencial.tls is True
    assert credencial.usuario == "svc_sessoes"
    assert credencial.senha.revelar() == "senha-redis"
    assert "senha-redis" not in repr(credencial)
    assert "x" * 64 not in repr(credencial)


@pytest.mark.parametrize(
    ("alteracoes", "mensagem"),
    [
        ({"banco": "-1"}, "banco"),
        ({"tls": "talvez"}, "tls"),
        ({"chave_assinatura_sessao": "curta"}, "32 caracteres"),
        ({"tipo_banco": "postgresql"}, "tipo Redis"),
    ],
)
def test_rejeita_credencial_redis_invalida(
    alteracoes: dict[str, object],
    mensagem: str,
) -> None:
    with pytest.raises(ErroCredencial, match=mensagem):
        CarregadorCredenciais(ProvedorFalso(_redis(**alteracoes))).carregar_redis("caminho")


class ProvedorMultiSegredos:
    """Provedor para testar leitura de multiplos segredos interligados."""

    def __init__(self, segredos: Mapping[str, Mapping[str, object]]) -> None:
        self.segredos = segredos
        self.caminhos_lidos: list[str] = []

    def validar_acesso(self) -> None:
        return None

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        self.caminhos_lidos.append(caminho)
        if caminho in self.segredos:
            return self.segredos[caminho]
        raise ErroCredencial(f"Segredo nao encontrado: {caminho}")


def test_carrega_banco_composto_com_sucesso() -> None:
    segredos = {
        "luft/desenvolvimento/bancos/postgresql/aplicacoes/luft-workspace": {
            "conexao": "luft-web",
            "esquema": "workspace",
            "usuario": "luft_workspace_app",
            "senha": "senha-segura",
        },
        "luft/desenvolvimento/bancos/postgresql/conexoes/luft-web": {
            "tipo_banco": "postgresql",
            "host": "172.19.85.111",
            "porta": "5432",
            "nome_banco": "luft_web",
            "sslmode": "prefer",
        },
    }
    provedor = ProvedorMultiSegredos(segredos)
    carregador = CarregadorCredenciais(provedor)

    credencial = carregador.carregar_banco_composto(
        "luft/desenvolvimento/bancos/postgresql/aplicacoes/luft-workspace",
        "luft/desenvolvimento/bancos/postgresql/conexoes",
    )

    assert credencial.tipo is TipoBanco.POSTGRESQL
    assert credencial.host == "172.19.85.111"
    assert credencial.porta == 5432
    assert credencial.nome_banco == "luft_web"
    assert credencial.usuario == "luft_workspace_app"
    assert credencial.esquema == "workspace"
    assert credencial.senha.revelar() == "senha-segura"
    assert provedor.caminhos_lidos == [
        "luft/desenvolvimento/bancos/postgresql/aplicacoes/luft-workspace",
        "luft/desenvolvimento/bancos/postgresql/conexoes/luft-web",
    ]


def test_carrega_aplicacao_postgresql_e_confere_identidade() -> None:
    segredos = {
        "sistemas/0": {
            "conexao": "luft-web",
            "esquema": "workspace",
            "usuario": "luft_workspace_app",
            "senha": "senha-segura",
            "identificador": "luft-workspace",
            "sistema_id": 0,
        },
        "conexoes/luft-web": {
            "tipo_banco": "postgresql",
            "host": "db",
            "porta": "5432",
            "nome_banco": "luft_web",
            "sslmode": "require",
        },
    }

    aplicacao = CarregadorCredenciais(
        ProvedorMultiSegredos(segredos)
    ).carregar_aplicacao_postgresql(
        "sistemas/0",
        "conexoes",
        sistema_id_esperado=0,
    )

    assert aplicacao.identificador == "luft-workspace"
    assert aplicacao.sistema_id == 0
    assert aplicacao.banco.esquema == "workspace"
    assert aplicacao.banco.sslmode == "require"


def test_rejeita_segredo_de_outro_sistema() -> None:
    segredos = {
        "sistemas/0": {
            "conexao": "luft-web",
            "esquema": "workspace",
            "usuario": "luft_workspace_app",
            "senha": "senha-segura",
            "identificador": "luft-workspace",
            "sistema_id": 2,
        },
        "conexoes/luft-web": {
            "tipo_banco": "postgresql",
            "host": "db",
            "porta": "5432",
            "nome_banco": "luft_web",
        },
    }

    with pytest.raises(ErroCredencial, match="bootstrap solicitou"):
        CarregadorCredenciais(ProvedorMultiSegredos(segredos)).carregar_aplicacao_postgresql(
            "sistemas/0",
            "conexoes",
            sistema_id_esperado=0,
        )


def test_carrega_banco_composto_rejeita_usuario_administrativo() -> None:
    segredos = {
        "app": {
            "conexao": "luft-web",
            "esquema": "workspace",
            "usuario": "admin",
            "senha": "senha",
        },
        "conexoes/luft-web": {
            "tipo_banco": "postgresql",
            "host": "db",
            "porta": "5432",
            "nome_banco": "luft_web",
        },
    }
    carregador = CarregadorCredenciais(ProvedorMultiSegredos(segredos))
    with pytest.raises(ErroCredencial, match="administrativa"):
        carregador.carregar_banco_composto("app", "conexoes")


def test_carrega_banco_composto_rejeita_tipo_conexao_invalido() -> None:
    segredos = {
        "app": {
            "conexao": "luft-web",
            "esquema": "workspace",
            "usuario": "luft_app",
            "senha": "senha",
        },
        "conexoes/luft-web": {
            "tipo_banco": "oracle",
            "host": "db",
            "porta": "1521",
            "nome_banco": "luft_web",
        },
    }
    carregador = CarregadorCredenciais(ProvedorMultiSegredos(segredos))
    with pytest.raises(ErroCredencial, match="postgresql"):
        carregador.carregar_banco_composto("app", "conexoes")
