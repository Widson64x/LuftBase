"""Integracao da mesma sessao entre duas aplicacoes Flask independentes."""

import json
from datetime import UTC, datetime, timedelta

from flask import Flask, jsonify, request
from flask_login import current_user

from luftbase import PlataformaLuft
from luftbase.identidade import (
    UsuarioAutenticado,
    encerrar_sessao_global,
    iniciar_sessao_usuario,
)
from luftbase.infraestrutura.banco.saude import ResultadoSaude
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.infraestrutura.fabrica import (
    FabricaInfraestruturaMemoria,
    RecursosInfraestrutura,
)


class ArmazenamentoCompartilhado:
    """Substitui Redis preservando a semantica de compartilhamento e revogacao."""

    def __init__(self) -> None:
        self.dados: dict[str, bytes] = {}

    def obter(self, chave: str) -> bytes | None:
        return self.dados.get(chave)

    def salvar(self, chave: str, valor: bytes, ttl_segundos: int) -> None:
        assert ttl_segundos in {3_600, 86_400}  # 60 min; "lembrar acesso" = 1 dia
        self.dados[chave] = valor

    def remover(self, chave: str) -> None:
        self.dados.pop(chave, None)

    def verificar_saude(self) -> bool:
        return True


class DiretorioNaoConsultado:
    """Comprova que o user loader nao consulta SQL Server por requisicao."""

    somente_leitura = True

    def leitura(self):  # type: ignore[no-untyped-def]
        raise AssertionError("O diretorio nao deveria ser consultado ao restaurar a sessao.")


class BancosFalsos:
    def __init__(self) -> None:
        self.diretorio = DiretorioNaoConsultado()
        self.core = object()

    def remover_sessoes_contextuais(self) -> None:
        return None

    def verificar_saude(self) -> tuple[ResultadoSaude, ...]:
        return (ResultadoSaude("diretorio_sqlserver", True, 0.1, "ok"),)


class FabricaCompartilhada:
    def __init__(self, armazenamento: ArmazenamentoCompartilhado) -> None:
        self._armazenamento = armazenamento

    def criar(self, configuracao, caminhos):  # type: ignore[no-untyped-def]
        base = FabricaInfraestruturaMemoria().criar(configuracao, caminhos)
        return RecursosInfraestrutura(
            bancos=base.bancos,
            armazenamento_sessoes=self._armazenamento,  # type: ignore[arg-type]
            chave_assinatura_sessao=Segredo("c" * 64),
            identificador_vault=base.identificador_vault,
        )


def _criar_app(nome: str, armazenamento: ArmazenamentoCompartilhado) -> Flask:
    app = Flask(nome)
    app.config.update(
        TESTING=True,
        LUFT_SISTEMA_ID=0 if nome == "luft-workspace" else 2,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    PlataformaLuft(FabricaCompartilhada(armazenamento)).inicializar(app)  # type: ignore[arg-type]

    @app.get("/entrar")
    def entrar():  # type: ignore[no-untyped-def]
        lembrar = request.args.get("lembrar") == "1"
        iniciar_sessao_usuario(
            UsuarioAutenticado(
                id_usuario=2759,
                login="valdeir.junior",
                nome_completo="Valdeir Junior",
                email=None,
                id_grupo=7,
                nome_grupo="TI",
            ),
            lembrar=lembrar,
        )
        return jsonify(ok=True)

    @app.get("/identidade")
    def identidade():  # type: ignore[no-untyped-def]
        return jsonify(
            autenticado=current_user.is_authenticated,
            id=current_user.get_id() if current_user.is_authenticated else None,
        )

    @app.get("/sair")
    def sair():  # type: ignore[no-untyped-def]
        encerrar_sessao_global()
        return jsonify(ok=True)

    return app


def test_sessao_e_compartilhada_e_logout_revoga_todas_as_aplicacoes() -> None:
    armazenamento = ArmazenamentoCompartilhado()
    cliente_a = _criar_app("luft-workspace", armazenamento).test_client()
    cliente_b = _criar_app("luft-control", armazenamento).test_client()

    cliente_a.get("/entrar")
    cookie = cliente_a.get_cookie("luft_sessao")
    assert cookie is not None
    assert len(armazenamento.dados) == 1
    cliente_b.set_cookie("luft_sessao", cookie.value)

    identidade = cliente_b.get("/identidade")

    assert identidade.json == {"autenticado": True, "id": "2759"}
    cliente_a.get("/sair")
    assert not armazenamento.dados
    assert cliente_b.get("/identidade").json == {
        "autenticado": False,
        "id": None,
    }


def _envelhecer_sessao(armazenamento: ArmazenamentoCompartilhado, horas: int) -> None:
    for chave, bruto in list(armazenamento.dados.items()):
        envelope = json.loads(bruto)
        antigo = datetime.now(UTC) - timedelta(hours=horas)
        envelope["salva_em"] = antigo.isoformat()
        armazenamento.dados[chave] = json.dumps(envelope).encode("utf-8")


def test_lembrar_acesso_sobrevive_a_inatividade_que_derruba_a_sessao_comum() -> None:
    comum = ArmazenamentoCompartilhado()
    cliente_comum = _criar_app("luft-workspace", comum).test_client()
    cliente_comum.get("/entrar")
    _envelhecer_sessao(comum, horas=5)
    assert cliente_comum.get("/identidade").json == {"autenticado": False, "id": None}

    lembrada = ArmazenamentoCompartilhado()
    cliente_lembrado = _criar_app("luft-workspace", lembrada).test_client()
    cliente_lembrado.get("/entrar?lembrar=1")
    _envelhecer_sessao(lembrada, horas=5)
    assert cliente_lembrado.get("/identidade").json == {"autenticado": True, "id": "2759"}
