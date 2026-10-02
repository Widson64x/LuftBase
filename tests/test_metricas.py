"""Testes das metricas locais de baixa cardinalidade."""

from luftbase.observabilidade.metricas import RegistroMetricas


def test_agrega_por_metodo_e_classe_sem_rotas_ou_usuarios() -> None:
    metricas = RegistroMetricas()

    metricas.registrar_requisicao("GET", 200, 12)
    metricas.registrar_requisicao("GET", 404, 3)
    metricas.registrar_requisicao("TRACE", 503, 7)
    metricas.registrar_falha_auditoria()
    resultado = metricas.snapshot()

    assert resultado["requisicoes_total"] == 3
    assert resultado["requisicoes"] == {"GET:2xx": 1, "GET:4xx": 1, "OUTRO:5xx": 1}
    assert resultado["duracao_total_ms"] == 22
    assert resultado["falhas_auditoria_total"] == 1
