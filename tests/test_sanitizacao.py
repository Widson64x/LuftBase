"""Testes de redacao e limites dos dados observaveis."""

import json

from luftbase.observabilidade.sanitizacao import (
    sanitizar_dados,
    serializar_dados_seguro,
)


def test_redige_segredos_em_estruturas_aninhadas() -> None:
    dados = {
        "usuario": "widson",
        "senha": "nao-pode-vazar",
        "cabecalhos": {"Authorization": "Bearer segredo", "aceitar": "json"},
        "itens": [{"token": "secreto"}],
    }

    resultado = sanitizar_dados(dados)
    serializado = json.dumps(resultado)

    assert "widson" in serializado
    assert "nao-pode-vazar" not in serializado
    assert "Bearer segredo" not in serializado
    assert "secreto" not in serializado
    assert serializado.count("[REDACTED]") == 3


def test_limita_texto_e_payload_sem_produzir_json_invalido() -> None:
    texto = serializar_dados_seguro({"valor": "x" * 20_000}, maximo_caracteres=100)

    assert json.loads(texto)["truncado"] is True
