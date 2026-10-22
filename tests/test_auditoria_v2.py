"""Auditoria & Analise v2: cache curto, opcoes separadas, janela arredondada, alertas paginados e expiracao no Ao vivo."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import pytest
from core_sqlite import motor_sqlite
from flask import Flask

from luftbase import PlataformaLuft
from luftbase.autorizacao import PermissaoLuftBase
from luftbase.configuracao import ConfiguracaoLuftBase
from luftbase.identidade import UsuarioAutenticado
from luftbase.infraestrutura.banco.sessoes import BancoSQLAlchemy
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaMemoria
from luftbase.nucleo.tempo import agora_local
from luftbase.observabilidade.alertas import consultar_alertas, contar_alertas, situacao_do_alerta
from luftbase.observabilidade.cache_curto import CacheCurto
from luftbase.observabilidade.tempo_real import consolidar_tempo_real
from luftbase.persistencia.base import BaseLuft
from luftbase.persistencia.core.alertas import Alerta
from luftbase.persistencia.core.seguranca import Sistema

# ---------------------------------------------------------------- cache curto


def test_cache_guarda_o_resultado_ate_o_prazo() -> None:
    cache = CacheCurto(ttl_segundos=0.2)
    chamadas: list[int] = []

    def calcular() -> int:
        chamadas.append(1)
        return len(chamadas)

    assert [cache.obter("k", calcular) for _ in range(3)] == [1, 1, 1]
    time.sleep(0.25)
    assert cache.obter("k", calcular) == 2  # venceu: recalcula
    assert (cache.acertos, cache.falhas) == (2, 2)


def test_cache_forcar_ignora_e_substitui_o_guardado() -> None:
    cache = CacheCurto(ttl_segundos=60)
    cache.obter("k", lambda: "velho")

    assert cache.obter("k", lambda: "novo", forcar=True) == "novo"
    assert cache.obter("k", lambda: "outro") == "novo"


def test_cache_descarta_os_mais_antigos_ao_passar_do_limite() -> None:
    cache = CacheCurto(ttl_segundos=60, maximo=2)
    for chave in ("a", "b", "c"):
        cache.obter(chave, lambda c=chave: c)

    assert len(cache) == 2
    assert cache.obter("a", lambda: "recalculado") == "recalculado"  # "a" foi o primeiro a sair


def test_cache_chaves_diferentes_nao_se_misturam() -> None:
    cache = CacheCurto()

    assert cache.obter(("resumo", 1), lambda: "um") == "um"
    assert cache.obter(("resumo", 2), lambda: "dois") == "dois"


# ---------------------------------------------------------------- alertas


T0 = agora_local()


@pytest.fixture
def banco() -> BancoSQLAlchemy:
    banco = BancoSQLAlchemy("core", motor_sqlite(BaseLuft, "core"))
    with banco.unidade_trabalho() as s:
        s.add(Sistema(id_sistema=3, nome_sistema="Luft-ConnectAir", ativo=True))
        s.add(Sistema(id_sistema=5, nome_sistema="Luft-Docs", ativo=True))
        modelo = {
            "chave": "x",
            "ocorrencias_notificadas": 0,
            "primeira_ocorrencia": T0 - timedelta(hours=3),
        }
        s.add_all(
            [
                Alerta(**modelo, regra="ERRO_5XX", id_sistema=3, login_usuario="ana", rota="/rotas/:id", status_http=500,
                       status="ABERTO", ocorrencias=7, ultima_ocorrencia=T0 - timedelta(minutes=2), detalhe="falha ao salvar"),
                Alerta(**modelo, regra="LENTIDAO", id_sistema=3, login_usuario="bia", rota="/relatorio", status="ABERTO",
                       ocorrencias=3, ultima_ocorrencia=T0 - timedelta(minutes=30), silenciado_ate=T0 + timedelta(hours=2)),
                Alerta(**modelo, regra="ERRO_5XX", id_sistema=5, login_usuario="caio", rota="/docs", status="ABERTO",
                       ocorrencias=2, ultima_ocorrencia=T0 - timedelta(minutes=10)),
                Alerta(**modelo, regra="EVENTO_CRITICO", id_sistema=5, status="RESOLVIDO", ocorrencias=1,
                       ultima_ocorrencia=T0 - timedelta(hours=2), resolvido_em=T0 - timedelta(hours=1)),
                # silencio que ja acabou: volta a contar como aberto
                Alerta(**modelo, regra="ERRO_4XX_SEQUENCIA", id_sistema=3, login_usuario="dani", status="ABERTO", ocorrencias=9,
                       ultima_ocorrencia=T0 - timedelta(minutes=50), silenciado_ate=T0 - timedelta(minutes=1)),
            ]
        )
    return banco


def _consultar(banco: BancoSQLAlchemy, **opcoes: Any) -> dict[str, Any]:
    with banco.leitura() as db:
        return consultar_alertas(db, agora=T0, **opcoes)


def test_contagens_por_situacao(banco: BancoSQLAlchemy) -> None:
    with banco.leitura() as db:
        assert contar_alertas(db, agora=T0) == {"abertos": 3, "silenciados": 1, "resolvidos": 1, "todos": 5}
        assert contar_alertas(db, id_sistema=3, agora=T0)["abertos"] == 2  # so os do sistema 3


def test_cada_situacao_traz_so_o_que_diz(banco: BancoSQLAlchemy) -> None:
    abertos = _consultar(banco, situacao="abertos")
    silenciados = _consultar(banco, situacao="silenciados")
    resolvidos = _consultar(banco, situacao="resolvidos")

    assert sorted(i["login"] for i in abertos["itens"] if i["login"]) == ["ana", "caio", "dani"]
    assert [i["login"] for i in silenciados["itens"]] == ["bia"]
    assert [i["situacao"] for i in resolvidos["itens"]] == ["RESOLVIDO"]
    assert abertos["total"] == 3 and abertos["contagens"]["todos"] == 5


def test_todos_ordena_abertos_depois_silenciados_depois_resolvidos(banco: BancoSQLAlchemy) -> None:
    situacoes = [i["situacao"] for i in _consultar(banco, situacao="todos")["itens"]]

    assert situacoes == ["ABERTO", "ABERTO", "ABERTO", "SILENCIADO", "RESOLVIDO"]


def test_dentro_de_cada_grupo_o_mais_recente_vem_primeiro(banco: BancoSQLAlchemy) -> None:
    logins = [i["login"] for i in _consultar(banco, situacao="abertos")["itens"]]

    assert logins == ["ana", "caio", "dani"]  # 2 min, 10 min, 50 min atras


def test_filtra_por_sistema_e_por_texto(banco: BancoSQLAlchemy) -> None:
    assert {i["login"] for i in _consultar(banco, situacao="todos", id_sistema=5)["itens"]} == {"caio", None}
    assert [i["login"] for i in _consultar(banco, situacao="todos", termo="SALVAR")["itens"]] == ["ana"]  # detalhe, sem caixa
    assert [i["login"] for i in _consultar(banco, situacao="todos", termo="/relatorio")["itens"]] == ["bia"]
    assert _consultar(banco, situacao="todos", termo="%")["total"] == 0  # o '%' e literal, nao curinga


def test_paginacao_devolve_o_total_e_a_janela(banco: BancoSQLAlchemy) -> None:
    pagina = _consultar(banco, situacao="todos", limite=2, deslocamento=2)

    assert pagina["total"] == 5
    assert len(pagina["itens"]) == 2


def test_situacao_invalida_e_recusada(banco: BancoSQLAlchemy) -> None:
    with pytest.raises(ValueError):
        _consultar(banco, situacao="qualquer")


def test_silencio_vencido_volta_a_ser_aberto() -> None:
    alerta = Alerta(chave="k", regra="X", status="ABERTO", ocorrencias=1, ocorrencias_notificadas=0,
                    primeira_ocorrencia=T0, ultima_ocorrencia=T0, silenciado_ate=T0 - timedelta(seconds=1))

    assert situacao_do_alerta(alerta, T0) == "ABERTO"
    alerta.silenciado_ate = T0 + timedelta(seconds=1)
    assert situacao_do_alerta(alerta, T0) == "SILENCIADO"


# ---------------------------------------------------------------- ao vivo: expiracao da sessao


def _sessao(minutos_ate_expirar: int | None, **extra: Any) -> dict[str, Any]:
    base = {
        "codigo_usuario": 1, "login": "rafael", "nome": "Rafael", "grupo": None, "foto": None, "id_sistema": 3,
        "ip_origem": "10.0.0.1", "user_agent": "Mozilla/5.0 Chrome/155", "criada_em": T0 - timedelta(hours=39),
        "ultima_atividade": T0 - timedelta(hours=38),
    }
    base.update(extra)
    if minutos_ate_expirar is not None:
        base["expira_em"] = T0 + timedelta(minutes=minutos_ate_expirar)
    return base


def test_ao_vivo_mostra_quando_a_sessao_expira() -> None:
    resultado = consolidar_tempo_real([_sessao(90)], [], agora=T0)

    assert resultado["online"][0]["expira_em_segundos"] == 90 * 60


def test_sessao_com_prazo_longo_fica_visivel() -> None:
    # o caso real: 38 h ociosa mas com validade de dias (lembrar acesso / TTL alto) agora aparece como tal
    resultado = consolidar_tempo_real([_sessao(60 * 24 * 29)], [], agora=T0)

    assert resultado["online"][0]["expira_em_segundos"] > 28 * 24 * 3600
    assert resultado["online"][0]["inativo_segundos"] >= 38 * 3600


def test_sessao_sem_prazo_conhecido_nao_quebra() -> None:
    assert consolidar_tempo_real([_sessao(None)], [], agora=T0)["online"][0]["expira_em_segundos"] is None


# ---------------------------------------------------------------- rotas


def _aplicacao(sistema_id: int = 0) -> tuple[Flask, Any]:
    app = Flask(__name__)
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": sistema_id,
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault.invalid:8200",
            "LUFT_LDAP_SERVIDOR": "ldap.invalid",
            "LUFT_LDAP_DOMINIO": "luft",
        }
    )
    estado = PlataformaLuft(FabricaInfraestruturaMemoria()).inicializar(app, configuracao)
    app.testing = True
    return app, estado


def _autenticado(app: Flask, estado: Any, *, sensiveis: bool = True):  # type: ignore[no-untyped-def]
    cliente = app.test_client()
    usuario = UsuarioAutenticado(10, "operador", "Operador", None, 6, "DBA")
    with cliente.session_transaction() as sessao:
        sessao["_user_id"] = usuario.get_id()
        sessao["_fresh"] = True
        sessao["luftbase_usuario"] = usuario.como_dict()
    liberadas = {PermissaoLuftBase.AUDITORIA_VISUALIZAR} | ({PermissaoLuftBase.AUDITORIA_DADOS_SENSIVEIS_VISUALIZAR} if sensiveis else set())
    estado.autorizacao.possui = lambda _u, chave, *_: chave in liberadas
    estado.autorizacao.consultar = lambda _u, chaves: {c: c in liberadas for c in chaves}
    return cliente


class ServicoContador:
    def __init__(self) -> None:
        self.resumos = 0
        self.opcoes = 0
        self.filtros: list[Any] = []

    def obter_resumo(self, filtro: Any) -> dict[str, Any]:
        self.resumos += 1
        self.filtros.append(filtro)
        return {"indicadores": {"requisicoes": self.resumos}, "serie": [], "rankings": {}}

    def obter_opcoes(self, filtro: Any, *, id_sistema_escopo: int | None = None) -> dict[str, Any]:
        self.opcoes += 1
        return {"sistemas": [], "usuarios": [{"id": 1, "nome": "ana"}], "grupos": []}


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    import luftbase.web.auditoria as modulo

    app, estado = _aplicacao()
    servico = ServicoContador()
    monkeypatch.setattr(modulo, "_servico", lambda: servico)
    monkeypatch.setattr(modulo, "_contagem_alertas", lambda: {"abertos": 2, "silenciados": 0, "resolvidos": 1, "todos": 3})
    return app, estado, servico


def test_resumo_repetido_no_mesmo_instante_reaproveita_o_calculo(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)

    primeira = cliente.get("/configuracoes/api/auditoria/resumo").get_json()["data"]["indicadores"]["requisicoes"]
    segunda = cliente.get("/configuracoes/api/auditoria/resumo").get_json()["data"]["indicadores"]["requisicoes"]

    assert (primeira, segunda, servico.resumos) == (1, 1, 1)


def test_atualizar_fresco_ignora_o_cache(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)

    cliente.get("/configuracoes/api/auditoria/resumo")
    novo = cliente.get("/configuracoes/api/auditoria/resumo?fresco=1").get_json()["data"]["indicadores"]["requisicoes"]

    assert (novo, servico.resumos) == (2, 2)


def test_filtros_diferentes_nao_dividem_o_mesmo_cache(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)

    cliente.get("/configuracoes/api/auditoria/resumo?usuario_id=1")
    cliente.get("/configuracoes/api/auditoria/resumo?usuario_id=2")

    assert servico.resumos == 2


def test_resumo_sem_opcoes_nao_consulta_as_listas(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)

    leve = cliente.get("/configuracoes/api/auditoria/resumo?opcoes=0").get_json()["data"]
    completo = cliente.get("/configuracoes/api/auditoria/resumo").get_json()["data"]

    assert "opcoes" not in leve
    assert completo["opcoes"]["usuarios"] == [{"id": 1, "nome": "ana"}]
    assert servico.opcoes == 1  # so a chamada completa pediu as listas


def test_rota_de_opcoes_e_cacheada(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)

    for _ in range(3):
        resposta = cliente.get("/configuracoes/api/auditoria/opcoes")
        assert resposta.get_json()["data"]["usuarios"][0]["nome"] == "ana"

    assert servico.opcoes == 1


def test_janela_e_arredondada_para_15_segundos(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, servico = ambiente
    cliente = _autenticado(app, estado)
    fim = datetime.now().replace(second=47, microsecond=123456)

    cliente.get("/configuracoes/api/auditoria/resumo", query_string={"inicio": (fim - timedelta(hours=1)).isoformat(), "fim": fim.isoformat()})

    filtro = servico.filtros[0]
    assert filtro.fim.second == 45 and filtro.fim.microsecond == 0
    assert filtro.inicio.second == 45 and filtro.inicio.microsecond == 0


def test_alertas_no_resumo_so_para_quem_ve_dados_sensiveis(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, _servico = ambiente

    com = _autenticado(app, estado, sensiveis=True).get("/configuracoes/api/auditoria/resumo").get_json()["data"]
    sem = _autenticado(app, estado, sensiveis=False).get("/configuracoes/api/auditoria/resumo?fresco=1").get_json()["data"]

    assert com["alertas"]["abertos"] == 2
    assert sem["alertas"] is None


def test_alertas_rota_valida_a_situacao_e_exige_permissao(ambiente) -> None:  # type: ignore[no-untyped-def]
    app, estado, _servico = ambiente
    cliente = _autenticado(app, estado, sensiveis=True)

    assert cliente.get("/configuracoes/api/auditoria/alertas?situacao=qualquer").status_code == 400
    sem = _autenticado(app, estado, sensiveis=False)
    assert sem.get("/configuracoes/api/auditoria/alertas").status_code == 403
