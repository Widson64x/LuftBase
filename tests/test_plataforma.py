"""Testes da extensao principal Flask."""

import pytest
from flask import Flask

from luftbase import PlataformaLuft, obter_luftbase
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.fabrica import (
    FabricaInfraestruturaMemoria,
    RecursosInfraestrutura,
)
from luftbase.nucleo import ErroInicializacao


class BancosFalsos:
    """Catalogo sem rede para observar ciclo de vida e health check."""

    def __init__(self, bancos_base: object) -> None:
        self.remocoes = 0
        self.diretorio = bancos_base.diretorio  # type: ignore[attr-defined]
        self.core = bancos_base.core  # type: ignore[attr-defined]
        self.aplicacao = bancos_base.aplicacao  # type: ignore[attr-defined]

    def remover_sessoes_contextuais(self) -> None:
        self.remocoes += 1

    def verificar_saude(self) -> tuple[ResultadoSaude, ...]:
        return (
            ResultadoSaude("diretorio_sqlserver", True, 1.0, "ok"),
            ResultadoSaude("core_postgresql", True, 1.0, "ok"),
            ResultadoSaude("aplicacao_postgresql", True, 1.0, "ok"),
        )


class DiretorioFalso:
    """Fronteira minima aceita pelo repositorio, sem conexao real."""

    somente_leitura = True


class ArmazenamentoFalso:
    """Armazenamento de sessao em memoria usado pela plataforma de teste."""

    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        del ttl_segundos
        self.dados[chave] = valor

    def remover(self, chave: str) -> None:
        self.dados.pop(chave, None)

    def verificar_saude(self) -> bool:
        return True


class FabricaFalsa:
    """Substitui Vault e bancos durante testes da extensao Flask."""

    def __init__(self) -> None:
        self.bancos = None
        self.armazenamento = ArmazenamentoFalso()
        self.chamadas = 0

    def criar(self, configuracao, caminhos):  # type: ignore[no-untyped-def]
        self.chamadas += 1
        base = FabricaInfraestruturaMemoria().criar(configuracao, caminhos)
        self.bancos = BancosFalsos(base.bancos)
        return RecursosInfraestrutura(
            bancos=self.bancos,  # type: ignore[arg-type]
            armazenamento_sessoes=self.armazenamento,  # type: ignore[arg-type]
            chave_assinatura_sessao=Segredo("s" * 64),
            identificador_vault=base.identificador_vault,
        )


def _criar_app() -> Flask:
    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    return app


def test_inicializa_e_expoe_estado_no_contexto_flask() -> None:
    app = _criar_app()
    fabrica = FabricaFalsa()
    plataforma = PlataformaLuft(fabrica)  # type: ignore[arg-type]

    estado = plataforma.inicializar(app)

    assert app.extensions["luftbase"] is estado
    assert estado.caminhos_vault.postgresql.endswith("/bancos/postgresql/sistemas/0")
    with app.app_context():
        assert obter_luftbase() is estado
    assert fabrica.chamadas == 1
    assert fabrica.bancos.remocoes == 1


def test_impede_inicializacao_duplicada() -> None:
    app = _criar_app()
    fabrica = FabricaFalsa()
    plataforma = PlataformaLuft(fabrica)  # type: ignore[arg-type]
    plataforma.inicializar(app)

    with pytest.raises(ErroInicializacao, match="ja foi inicializado"):
        plataforma.inicializar(app)
    assert fabrica.chamadas == 1


def test_expoe_health_check_sanitizado() -> None:
    app = _criar_app()
    fabrica = FabricaFalsa()
    PlataformaLuft(fabrica).inicializar(app)  # type: ignore[arg-type]

    resposta = app.test_client().get("/_luftbase/saude")

    assert resposta.status_code == 200
    assert resposta.json["status"] == "ok"
    assert resposta.json["dependencias"][0] == {
        "codigo": "ok",
        "dependencia": "diretorio_sqlserver",
        "disponivel": True,
        "latencia_ms": 1.0,
    }
    assert resposta.json["dependencias"][-1]["dependencia"] == "sessoes_redis"
    assert resposta.json["dependencias"][-1]["disponivel"] is True


def test_instala_politica_de_sessao_e_autenticacao() -> None:
    app = _criar_app()
    app.config.update(
        LUFT_SESSAO_COOKIE_NOME="sessao_corporativa",
        LUFT_SESSAO_TTL_MINUTOS=90,
    )

    estado = PlataformaLuft(FabricaFalsa()).inicializar(app)  # type: ignore[arg-type]

    assert app.config["SESSION_COOKIE_NAME"] == "sessao_corporativa"
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.permanent_session_lifetime.total_seconds() == 5400
    assert estado.autenticacao is not None
    assert estado.autorizacao is not None
    assert estado.notificacoes is not None
    assert estado.publicacoes is not None
    assert estado.temas.registro.obter("luft") is not None
    assert estado.auditoria is not None
    assert estado.metricas is not None
    assert estado.gerenciador_login is app.login_manager  # type: ignore[attr-defined]


def test_expoe_correlacao_prontidao_e_metricas_sanitizadas() -> None:
    app = _criar_app()
    PlataformaLuft(FabricaFalsa()).inicializar(app)  # type: ignore[arg-type]

    @app.get("/teste")
    def teste() -> str:
        return "ok"

    cliente = app.test_client()
    resposta = cliente.get("/teste", headers={"X-Correlation-ID": "teste-correlacao-123"})
    prontidao = cliente.get("/_luftbase/prontidao")
    metricas = cliente.get("/_luftbase/metricas")

    assert resposta.headers["X-Correlation-ID"] == "teste-correlacao-123"
    assert prontidao.status_code == 200
    assert metricas.status_code == 200
    assert metricas.json["requisicoes_total"] == 2
    assert "usuario" not in str(metricas.json).lower()
