"""Alertas para o desenvolvedor: deteccao, antirruido, trava e e-mail."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import pytest
from core_sqlite import motor_sqlite
from sqlalchemy import select

from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.observabilidade import alertas
from luftbase.observabilidade.alertas import DESTINATARIOS_ALERTA, Limites, avaliar
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.alertas import Alerta, AlertaControle
from luftbase.persistencia.core.auditoria import Log, LogEvento
from luftbase.persistencia.core.seguranca import Sistema

# Quarta-feira, 10:00: horario comercial.
T0 = datetime(2026, 10, 7, 10, 0, 0)


@dataclass
class EmailFalso:
    configurado: bool = True
    sucesso: bool = True
    enviados: list[dict[str, Any]] = field(default_factory=list)

    def enviar(self, para: Any, assunto: str, **opcoes: Any) -> Any:
        self.enviados.append({"para": list(para), "assunto": assunto, **opcoes})
        return type("R", (), {"sucesso": self.sucesso, "erro": "smtp fora"})()


class Bancos:
    def __init__(self) -> None:
        self.core = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))


@pytest.fixture
def bancos() -> Bancos:
    b = Bancos()
    with b.core.unidade_trabalho() as s:
        s.add(Sistema(id_sistema=0, nome_sistema="Luft-Workspace", ativo=True))
        s.add(Sistema(id_sistema=2, nome_sistema="Luft-ConnectAir", ativo=True))
    return b


def _log(
    bancos: Bancos,
    quando: datetime,
    *,
    status: int = 200,
    login: str | None = "ana",
    rota: str = "/planejamento/salvar",
    sistema: int = 2,
    duracao: int = 50,
    ip: str = "10.0.0.5",
    correlacao: str = "corr-1",
    parametros: str | None = None,
) -> None:
    with bancos.core.unidade_trabalho() as s:
        s.add(
            Log(
                id_sistema=sistema,
                login_usuario=login,
                rota_acessada=rota,
                metodo_http="POST",
                ip_origem=ip,
                id_correlacao=correlacao,
                duracao_ms=duracao,
                status_http=status,
                data_hora=quando,
                parametros_requisicao=parametros,
            )
        )


def _alertas(bancos: Bancos) -> list[Alerta]:
    with bancos.core.leitura() as s:
        return list(s.execute(select(Alerta).order_by(Alerta.id_alerta)).scalars())


def _avaliar(bancos: Bancos, email: EmailFalso, agora: datetime) -> Any:
    return avaliar(bancos, email, agora=agora)  # type: ignore[arg-type]


def test_destinatario_fixo_no_codigo() -> None:
    assert DESTINATARIOS_ALERTA == ("widson.araujo@luftlogistics.com",)


def test_erro_500_abre_alerta_e_avisa_com_usuario_e_rota(bancos: Bancos) -> None:
    email = EmailFalso()
    for i in range(3):
        _log(bancos, T0 - timedelta(minutes=2, seconds=i), status=500, rota="/clientes/42/editar")

    r = _avaliar(bancos, email, T0)

    assert r.alertas_abertos == 1 and r.email_enviado and r.avisados == 1
    (a,) = _alertas(bancos)
    assert (a.regra, a.login_usuario, a.rota, a.status_http, a.ocorrencias) == (
        "ERRO_5XX",
        "ana",
        "/clientes/:id/editar",
        500,
        3,
    )
    (envio,) = email.enviados
    assert envio["para"] == ["widson.araujo@luftlogistics.com"]
    assert "ana" in envio["assunto"] and "Luft-ConnectAir" in envio["assunto"]
    linhas = dict(envio["contexto"]["itens"][0]["linhas"])
    assert linhas["Usuario"] == "ana" and linhas["Status"] == "500"
    assert linhas["Correlacao"] == "corr-1" and linhas["Ocorrencias"] == "3"


def test_nao_envia_dados_da_requisicao(bancos: Bancos) -> None:
    _log(bancos, T0 - timedelta(minutes=1), status=500, parametros='{"senha": "super-secreta"}')
    email = EmailFalso()

    _avaliar(bancos, email, T0)

    assert "super-secreta" not in str(email.enviados)


def test_mesmo_problema_soma_e_respeita_o_silencio(bancos: Bancos) -> None:
    email = EmailFalso()
    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, email, T0)

    _log(bancos, T0 + timedelta(minutes=2), status=500)
    r2 = _avaliar(bancos, email, T0 + timedelta(minutes=3))
    assert r2.alertas_atualizados == 1 and not r2.email_enviado and len(email.enviados) == 1
    assert _alertas(bancos)[0].ocorrencias == 2

    _log(bancos, T0 + timedelta(minutes=16), status=500)
    r3 = _avaliar(bancos, email, T0 + timedelta(minutes=17))
    assert r3.email_enviado and len(email.enviados) == 2
    assert _alertas(bancos)[0].ocorrencias == 3
    assert len(_alertas(bancos)) == 1  # um unico alerta para o mesmo problema


def test_nao_conta_duas_vezes_o_mesmo_erro(bancos: Bancos) -> None:
    email = EmailFalso()
    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, email, T0)
    _avaliar(bancos, email, T0 + timedelta(minutes=1))
    _avaliar(bancos, email, T0 + timedelta(minutes=2))

    assert _alertas(bancos)[0].ocorrencias == 1
    assert len(email.enviados) == 1


def test_alerta_fecha_sozinho_quando_para(bancos: Bancos) -> None:
    email = EmailFalso()
    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, email, T0)

    r = _avaliar(bancos, email, T0 + timedelta(minutes=40))

    assert r.alertas_resolvidos == 1
    a = _alertas(bancos)[0]
    assert a.status == "RESOLVIDO" and a.resolvido_em is not None


def test_rajada_de_4xx_so_alerta_a_partir_do_limite(bancos: Bancos) -> None:
    email = EmailFalso()
    for i in range(9):
        _log(bancos, T0 - timedelta(seconds=10 + i), status=403, login="bia")
    assert _avaliar(bancos, email, T0).ocorrencias == 0

    _log(bancos, T0 - timedelta(seconds=1), status=403, login="bia")
    r = _avaliar(bancos, email, T0 + timedelta(seconds=30))

    assert r.alertas_abertos == 1
    a = _alertas(bancos)[0]
    assert (a.regra, a.login_usuario, a.status_http, a.ocorrencias) == (
        "ERRO_4XX_SEQUENCIA",
        "bia",
        403,
        10,
    )


def test_4xx_de_pessoas_diferentes_nao_se_somam(bancos: Bancos) -> None:
    for i in range(6):
        _log(bancos, T0 - timedelta(seconds=10 + i), status=404, login="ana")
        _log(bancos, T0 - timedelta(seconds=10 + i), status=404, login="bia")

    assert _avaliar(bancos, EmailFalso(), T0).ocorrencias == 0


def test_rajada_sem_login_agrupa_por_ip(bancos: Bancos) -> None:
    for i in range(10):
        _log(bancos, T0 - timedelta(seconds=10 + i), status=401, login=None, ip="9.9.9.9")

    _avaliar(bancos, EmailFalso(), T0)

    assert _alertas(bancos)[0].ip_origem == "9.9.9.9"


def _evento(bancos: Bancos, severidade: str, acao: str = "PERMISSAO_BLOQUEAR") -> None:
    with bancos.core.unidade_trabalho() as s:
        s.add(
            LogEvento(
                id_sistema=0,
                login_usuario="widson",
                acao=acao,
                recurso="PERMISSAO_USUARIO",
                descricao="Alteracao sensivel",
                severidade=severidade,
                id_correlacao="c9",
                data_hora=T0 - timedelta(minutes=1),
            )
        )


def test_evento_critico_gera_alerta(bancos: Bancos) -> None:
    _evento(bancos, "CRITICA")

    _avaliar(bancos, EmailFalso(), T0)

    a = _alertas(bancos)[0]
    assert a.regra == "EVENTO_CRITICO" and a.login_usuario == "widson"
    assert a.rota == "PERMISSAO_USUARIO/PERMISSAO_BLOQUEAR"


def test_evento_de_severidade_baixa_nao_alerta(bancos: Bancos) -> None:
    _evento(bancos, "BAIXA", "LOGIN_SUCESSO")

    assert _avaliar(bancos, EmailFalso(), T0).ocorrencias == 0


def test_lentidao_por_p95(bancos: Bancos) -> None:
    for i in range(25):
        _log(bancos, T0 - timedelta(seconds=30 + i), duracao=5000)

    _avaliar(bancos, EmailFalso(), T0)

    a = [x for x in _alertas(bancos) if x.regra == "LENTIDAO"][0]
    assert a.id_sistema == 2 and "p95" in (a.detalhe or "")


def test_poucas_requisicoes_lentas_nao_alertam(bancos: Bancos) -> None:
    for i in range(5):
        _log(bancos, T0 - timedelta(seconds=30 + i), duracao=9000)

    assert _avaliar(bancos, EmailFalso(), T0).ocorrencias == 0


def _historico_de_uso(bancos: Bancos, ate: datetime, sistema: int = 2) -> None:
    with bancos.core.unidade_trabalho() as s:
        for i in range(120):
            s.add(
                Log(
                    id_sistema=sistema,
                    login_usuario="ana",
                    rota_acessada="/x",
                    metodo_http="GET",
                    id_correlacao="c",
                    duracao_ms=10,
                    status_http=200,
                    data_hora=ate - timedelta(hours=1, minutes=i),
                )
            )


def test_sistema_movimentado_que_para_em_horario_comercial_alerta(bancos: Bancos) -> None:
    _historico_de_uso(bancos, T0 - timedelta(minutes=30))

    _avaliar(bancos, EmailFalso(), T0)

    a = [x for x in _alertas(bancos) if x.regra == "SISTEMA_SEM_ACESSO"]
    assert [x.id_sistema for x in a] == [2]


def test_fora_do_horario_comercial_nao_alerta(bancos: Bancos) -> None:
    noite = datetime(2026, 10, 7, 22, 0, 0)
    sabado = datetime(2026, 10, 10, 10, 0, 0)
    _historico_de_uso(bancos, noite - timedelta(minutes=30))
    _historico_de_uso(bancos, sabado - timedelta(minutes=30))

    assert _avaliar(bancos, EmailFalso(), noite).ocorrencias == 0
    assert _avaliar(bancos, EmailFalso(), sabado + timedelta(minutes=1)).ocorrencias == 0


def test_sistema_de_pouco_uso_nao_gera_alerta_de_silencio(bancos: Bancos) -> None:
    _log(bancos, T0 - timedelta(hours=3))

    assert _avaliar(bancos, EmailFalso(), T0).ocorrencias == 0


def test_trava_impede_dois_avaliadores_ao_mesmo_tempo(bancos: Bancos) -> None:
    with bancos.core.unidade_trabalho() as s:
        s.add(AlertaControle(chave="avaliador", em_execucao_ate=T0 + timedelta(minutes=2)))

    assert _avaliar(bancos, EmailFalso(), T0).executou is False


def test_trava_expirada_nao_bloqueia_para_sempre(bancos: Bancos) -> None:
    with bancos.core.unidade_trabalho() as s:
        s.add(AlertaControle(chave="avaliador", em_execucao_ate=T0 - timedelta(minutes=1)))

    assert _avaliar(bancos, EmailFalso(), T0).executou is True


def test_falha_no_email_deixa_o_alerta_pendente_para_a_proxima(bancos: Bancos) -> None:
    _log(bancos, T0 - timedelta(minutes=1), status=500)

    r1 = _avaliar(bancos, EmailFalso(sucesso=False), T0)
    assert not r1.email_enviado and r1.erros
    assert _alertas(bancos)[0].ultima_notificacao is None

    bom = EmailFalso()
    r2 = _avaliar(bancos, bom, T0 + timedelta(minutes=1))
    assert r2.email_enviado and len(bom.enviados) == 1


def test_email_nao_configurado_nao_quebra(bancos: Bancos) -> None:
    _log(bancos, T0 - timedelta(minutes=1), status=500)

    r = _avaliar(bancos, EmailFalso(configurado=False), T0)

    assert not r.email_enviado and any("nao configurado" in e for e in r.erros)


def test_alerta_silenciado_nao_avisa(bancos: Bancos) -> None:
    email = EmailFalso()
    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, email, T0)
    id_alerta = _alertas(bancos)[0].id_alerta
    with bancos.core.unidade_trabalho() as s:
        assert alertas.silenciar(s, id_alerta, T0 + timedelta(hours=2))

    _log(bancos, T0 + timedelta(minutes=20), status=500)
    r = _avaliar(bancos, email, T0 + timedelta(minutes=21))

    assert not r.email_enviado and len(email.enviados) == 1


def test_erro_inesperado_nao_levanta(bancos: Bancos, monkeypatch: pytest.MonkeyPatch) -> None:
    def quebra(*_a: Any, **_k: Any) -> list[Any]:
        raise RuntimeError("banco caiu")

    monkeypatch.setattr(alertas, "detectar", quebra)

    r = _avaliar(bancos, EmailFalso(), T0)

    assert r.erros and "banco caiu" in r.erros[0]


def test_listar_alertas(bancos: Bancos) -> None:
    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, EmailFalso(), T0)

    with bancos.core.leitura() as s:
        itens = alertas.listar_alertas(s)

    assert itens[0]["sistema"] == "Luft-ConnectAir" and itens[0]["login"] == "ana"
    assert itens[0]["rotulo"] == "Erro 5xx"


def test_limites_padrao_sao_os_combinados() -> None:
    limites = Limites()
    assert (limites.minimo_4xx, limites.janela_4xx_min) == (10, 5)
    assert (limites.p95_lento_ms, limites.janela_lentidao_min) == (3000, 10)
    assert limites.silencio_min == 15 and limites.sem_acesso_min == 10
    assert (limites.hora_inicio, limites.hora_fim) == (7, 19)


def test_template_do_email_renderiza() -> None:
    from luftbase.configuracao import Ambiente
    from luftbase.infraestrutura.cofre.credenciais import (
        CredencialEmail,
        Segredo,
        SegurancaSmtp,
    )
    from luftbase.integracoes.email import ServicoEmail

    servico = ServicoEmail(
        CredencialEmail(
            host="smtp.exemplo",
            porta=587,
            seguranca=SegurancaSmtp.STARTTLS,
            usuario="c@luft.com",
            senha=Segredo("x"),
            remetente="portal@luft.com",
            nome_remetente="Luft",
        ),
        ambiente=Ambiente.PRODUCAO,
    )
    envio = servico.preparar(
        "widson.araujo@luftlogistics.com",
        "[LuftBase] Erro 5xx: ana em Luft-ConnectAir",
        template=alertas.TEMPLATE_EMAIL,
        contexto={
            "itens": [{"titulo": "Erro 5xx", "linhas": [("Usuario", "ana"), ("Rota", "/x/:id")]}],
            "gerado_em": "08/10/2026 10:00:00",
        },
    )

    html = envio.mensagem.get_body(("html",)).get_content()  # type: ignore[union-attr]
    assert "1 alerta(s) para verificar" in html and "ana" in html and "/x/:id" in html


def _rota_sem_decoradores(funcao: Any) -> Any:
    import inspect

    return inspect.unwrap(funcao)


def test_api_lista_e_silencia_alertas(bancos: Bancos, monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from flask import Flask

    from luftbase.web import auditoria

    _log(bancos, T0 - timedelta(minutes=1), status=500)
    _avaliar(bancos, EmailFalso(), T0)
    id_alerta = _alertas(bancos)[0].id_alerta
    monkeypatch.setattr(auditoria, "obter_luftbase", lambda: SimpleNamespace(bancos=bancos))
    monkeypatch.setattr(auditoria, "validar_csrf_requisicao", lambda: None)
    monkeypatch.setattr(auditoria, "registrar_alteracao_auditoria", lambda **_k: 1)
    app = Flask(__name__)

    with app.test_request_context("/auditoria/api/alertas"):
        corpo = _rota_sem_decoradores(auditoria.api_alertas)().get_json()
    assert corpo["data"]["alertas"][0]["login"] == "ana"

    with app.test_request_context(method="POST", json={"horas": 4}):
        resposta = _rota_sem_decoradores(auditoria.api_silenciar_alerta)(id_alerta)
    assert resposta.get_json()["message"] == "Alerta silenciado."
    assert _alertas(bancos)[0].silenciado_ate is not None

    with app.test_request_context(method="POST", json={"horas": 999}), pytest.raises(Exception) as erro:
        _rota_sem_decoradores(auditoria.api_silenciar_alerta)(id_alerta)
    assert getattr(erro.value, "code", None) == 400

    with app.test_request_context(method="POST", json={"horas": 1}), pytest.raises(Exception) as erro:
        _rota_sem_decoradores(auditoria.api_silenciar_alerta)(99999)
    assert getattr(erro.value, "code", None) == 404


def test_rotas_de_alertas_exigem_permissao_de_dados_sensiveis() -> None:
    from pathlib import Path

    from luftbase.web import auditoria

    codigo = Path(auditoria.__file__).read_text(encoding="utf-8")
    for nome in ("def api_alertas", "def api_silenciar_alerta"):
        cabecalho = codigo[codigo.rindex("@AuditoriaBp", 0, codigo.index(nome)) : codigo.index(nome)]
        assert "AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR" in cabecalho and "@login_required" in cabecalho


def test_email_renderiza_em_comando_de_cli_com_app_e_sem_requisicao() -> None:
    """`flask alertas avaliar` tem contexto de app mas nao de requisicao (regressao de 08/10)."""

    from flask import Flask

    from luftbase import PlataformaLuft
    from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria

    app = Flask(__name__)
    app.config.update(
        LUFT_SISTEMA_ID=0,
        LUFT_AMBIENTE="desenvolvimento",
        LUFT_VAULT_ENDERECO="http://vault:8200",
        LUFT_LDAP_SERVIDOR="ad.luft",
        LUFT_LDAP_DOMINIO="luftfarma",
    )
    PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app)

    from luftbase.integracoes.email.servico import renderizar_template_email

    with app.app_context():
        html = renderizar_template_email(
            alertas.TEMPLATE_EMAIL,
            {
                "itens": [{"titulo": "Erro 5xx", "linhas": [("Usuario", "ana")]}],
                "gerado_em": "08/10/2026 11:47:00",
                "luft_email": {"ambiente": "x", "gerado_em": "", "cid_logo": "", "ano": 2026},
            },
        )

    assert "1 alerta(s) para verificar" in html and "ana" in html


def test_envio_pode_abrir_transacao_propria_sem_aninhar(bancos: Bancos) -> None:
    """A auditoria do e-mail abre outra unidade de trabalho na mesma sessao (regressao de 08/10)."""

    _log(bancos, T0 - timedelta(minutes=1), status=500)

    def envio_que_audita(_para: Any, _assunto: str, _itens: Any) -> Any:
        with bancos.core.unidade_trabalho() as db:  # aninhado = "transaction is already begun"
            db.execute(__import__("sqlalchemy").text("SELECT 1"))
        return type("R", (), {"sucesso": True, "erro": None})()

    r = avaliar(bancos, EmailFalso(), agora=T0, enviar_email=envio_que_audita)  # type: ignore[arg-type]

    assert r.email_enviado and not r.erros
    a = _alertas(bancos)[0]
    assert a.ultima_notificacao is not None


def test_trava_e_solta_ao_fim_do_ciclo(bancos: Bancos) -> None:
    from sqlalchemy import select

    _log(bancos, T0 - timedelta(minutes=1), status=500)
    avaliar(bancos, EmailFalso(), agora=T0)  # type: ignore[arg-type]

    with bancos.core.leitura() as s:
        controle = s.execute(select(AlertaControle)).scalar_one()
    assert controle.em_execucao_ate is None
