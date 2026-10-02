"""Validacao do cadastro de sistemas no painel de configuracoes."""

from __future__ import annotations

from luftbase.web.configuracoes import prefixo_chave_sistema, validar_payload_novo_sistema


def test_payload_minimo_valido_gera_chave_base() -> None:
    valores, erros = validar_payload_novo_sistema({"Nome": "Luft-ConnectAir"})

    assert erros == {}
    assert valores["nome_sistema"] == "Luft-ConnectAir"
    assert valores["chave_permissao_base"] == "LUFT_CONNECTAIR.SISTEMA.ACESSAR"
    assert valores["icone"] == "ph-bold ph-app-window"
    assert valores["id_sistema"] is None
    assert valores["schema_aplicacao"] is None


def test_nome_obrigatorio_e_reportado_no_campo() -> None:
    _, erros = validar_payload_novo_sistema({"Nome": "   "})

    assert set(erros) == {"Nome"}
    assert "obrigatório" in erros["Nome"]


def test_todos_os_erros_sao_reportados_de_uma_vez() -> None:
    _, erros = validar_payload_novo_sistema(
        {
            "Nome": "",
            "IdSistema": "0",
            "OrdemExibicao": "abc",
            "Cor": "azul",
            "Link": "app.empresa.com",
            "UrlSaude": "/api/ health",
            "SchemaAplicacao": "Connect-Air",
            "Icone": "fa fa-home",
            "Categoria": "OUTRA",
        }
    )

    assert set(erros) == {
        "Nome",
        "IdSistema",
        "OrdemExibicao",
        "Cor",
        "Link",
        "UrlSaude",
        "SchemaAplicacao",
        "Icone",
        "Categoria",
    }


def test_schema_maiusculo_sugere_versao_minuscula() -> None:
    _, erros = validar_payload_novo_sistema({"Nome": "X", "SchemaAplicacao": "ConnectAir"})

    assert "connectair" in erros["SchemaAplicacao"]


def test_schema_reservado_e_recusado() -> None:
    for schema in ("core", "public", "pg_temp"):
        _, erros = validar_payload_novo_sistema({"Nome": "X", "SchemaAplicacao": schema})
        assert "reservado" in erros["SchemaAplicacao"]


def test_limites_de_tamanho_das_colunas() -> None:
    _, erros = validar_payload_novo_sistema(
        {"Nome": "N" * 101, "Descricao": "d" * 501, "Responsavel": "r" * 151}
    )

    assert set(erros) == {"Nome", "Descricao", "Responsavel"}


def test_rotas_e_urls_aceitas() -> None:
    _, erros = validar_payload_novo_sistema(
        {"Nome": "X", "Link": "/Luft-Integrador/", "UrlSaude": "https://app.luft.com/health"}
    )

    assert erros == {}


def test_prefixo_de_nome_iniciado_por_digito_respeita_constraint() -> None:
    assert prefixo_chave_sistema("3PL Portal") == "SISTEMA_3PL_PORTAL"
    assert prefixo_chave_sistema("---") == ""

    valores, erros = validar_payload_novo_sistema({"Nome": "3PL Portal"})
    assert erros == {}
    assert valores["chave_permissao_base"] == "SISTEMA_3PL_PORTAL.SISTEMA.ACESSAR"


def test_nome_sem_letras_nem_numeros_e_recusado() -> None:
    _, erros = validar_payload_novo_sistema({"Nome": "---"})

    assert "letra ou número" in erros["Nome"]
