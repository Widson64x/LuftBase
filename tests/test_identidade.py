"""Testes do retrato e do servico canonico de autenticacao."""

import pytest

from luftbase.identidade import ServicoAutenticacao, UsuarioAutenticado


def _usuario() -> UsuarioAutenticado:
    return UsuarioAutenticado(
        id_usuario=2759,
        login="valdeir.junior",
        nome_completo="Valdeir Junior",
        email="valdeir.junior@luft.com.br",
        id_grupo=7,
        nome_grupo="TI",
        permissoes=frozenset({"RELATORIOS.BUDGET.VISUALIZAR"}),
    )


def test_usuario_autenticado_atende_contrato_do_flask_login() -> None:
    usuario = _usuario()

    assert usuario.get_id() == "2759"
    assert usuario.is_authenticated is True
    assert usuario.is_active is True
    assert usuario.is_anonymous is False
    assert usuario.possui_permissao("RELATORIOS.BUDGET.VISUALIZAR") is True
    assert usuario.possui_permissao("ADMIN.MASTER") is False


def test_retrato_pode_ser_serializado_e_restaurado() -> None:
    usuario = _usuario()

    restaurado = UsuarioAutenticado.de_dict(usuario.como_dict())

    assert restaurado == usuario


@pytest.mark.parametrize(
    "alteracao",
    [
        {"id_usuario": True},
        {"login": ""},
        {"permissoes": "ADMIN"},
    ],
)
def test_retrato_rejeita_payload_invalido(alteracao: dict[str, object]) -> None:
    dados = _usuario().como_dict()
    dados.update(alteracao)

    with pytest.raises(ValueError):
        UsuarioAutenticado.de_dict(dados)


class AutenticadorFalso:
    def __init__(self, valido: bool) -> None:
        self.valido = valido
        self.chamadas = 0

    def autenticar(self, login: str, senha: str) -> bool:
        self.chamadas += 1
        return self.valido and login == "valdeir.junior" and senha == "senha"


class RepositorioFalso:
    def __init__(self, usuario: UsuarioAutenticado | None) -> None:
        self.usuario = usuario
        self.chamadas = 0

    def obter_por_login(self, identificador: str) -> UsuarioAutenticado | None:
        self.chamadas += 1
        return self.usuario if identificador == "valdeir.junior" else None


def test_servico_valida_ldap_antes_de_consultar_diretorio() -> None:
    autenticador = AutenticadorFalso(True)
    repositorio = RepositorioFalso(_usuario())
    servico = ServicoAutenticacao(autenticador, repositorio)

    assert servico.autenticar(" valdeir.junior ", "senha") == _usuario()
    assert autenticador.chamadas == 1
    assert repositorio.chamadas == 1


def test_servico_nao_consulta_diretorio_quando_ldap_rejeita() -> None:
    repositorio = RepositorioFalso(_usuario())
    servico = ServicoAutenticacao(AutenticadorFalso(False), repositorio)

    assert servico.autenticar("valdeir.junior", "senha") is None
    assert repositorio.chamadas == 0


def test_login_com_novo_codigo_aposenta_cadastro_antigo_sem_apagar() -> None:
    """Diretorio re-numerado: o login unico nao pode travar o cadastro nem apagar historico."""

    from sqlalchemy import (
        CheckConstraint,
        DefaultClause,
        ForeignKeyConstraint,
        MetaData,
        Table,
        create_engine,
        select,
        text,
    )
    from sqlalchemy.orm import Session

    from luftbase.identidade.repositorio_core import RepositorioUsuariosPostgreSQL
    from luftbase.persistencia.core.usuario import Usuario
    from typing import cast

    engine = create_engine(
        "sqlite+pysqlite:///:memory:", execution_options={"schema_translate_map": {"core": None}}
    )
    meta = MetaData()
    tabela = cast(Table, Usuario.__table__).to_metadata(meta)
    # Copia sem CHECK/FK do PostgreSQL, que o SQLite nao interpreta; o foco e o login unico.
    for restricao in [
        c for c in tabela.constraints if isinstance(c, CheckConstraint | ForeignKeyConstraint)
    ]:
        tabela.constraints.discard(restricao)
    for coluna in tabela.columns:
        coluna.foreign_keys.clear()
        padrao = getattr(coluna.server_default, "arg", None)
        if padrao is not None and "TIME ZONE" in str(padrao):
            coluna.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
    tabela.indexes.clear()
    meta.create_all(engine)
    with Session(engine) as sessao:
        sessao.execute(
            tabela.insert().values(
                codigo_usuario=2280,
                login_usuario="widson.araujo",
                nome_usuario="Widson",
                ativo=True,
            )
        )
        sessao.flush()

        RepositorioUsuariosPostgreSQL._liberar_login_de_outro_codigo(sessao, 2351, "Widson.Araujo")
        sessao.execute(
            tabela.insert().values(
                codigo_usuario=2351,
                login_usuario="widson.araujo",
                nome_usuario="Widson",
                ativo=True,
            )
        )
        linhas = {
            r.codigo_usuario: (r.login_usuario, bool(r.ativo))
            for r in sessao.execute(
                select(tabela.c.codigo_usuario, tabela.c.login_usuario, tabela.c.ativo)
            )
        }

    assert linhas[2351] == ("widson.araujo", True)
    assert linhas[2280] == ("widson.araujo~2280", False)
