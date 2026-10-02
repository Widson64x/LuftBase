"""Testes do LDAP seguro sem abrir sockets."""

import pytest

from luftbase.identidade.ldap import (
    AutenticadorLdap,
    ConfiguracaoLdap,
    TransporteLdap,
)
from luftbase.infraestrutura.cofre.credenciais import Segredo
from luftbase.nucleo.excecoes import ErroAutenticacao


class ConexaoFalsa:
    """Conexao LDAP observavel para os cenarios de autenticacao."""

    def __init__(
        self,
        *,
        abriu: bool = True,
        iniciou_tls: bool = True,
        autenticou: bool = True,
        erro: Exception | None = None,
    ) -> None:
        self.abriu = abriu
        self.iniciou_tls = iniciou_tls
        self.autenticou = autenticou
        self.erro = erro
        self.tls_chamado = False
        self.desconectou = False

    @property
    def closed(self) -> bool:
        return not self.abriu

    def open(self) -> bool:
        if self.erro:
            raise self.erro
        return self.abriu

    def start_tls(self) -> bool:
        self.tls_chamado = True
        return self.iniciou_tls

    def bind(self) -> bool:
        return self.autenticou

    def unbind(self) -> bool:
        self.desconectou = True
        return True


class FabricaFalsa:
    """Captura usuario e senha sem depender do ldap3."""

    def __init__(self, conexao: ConexaoFalsa) -> None:
        self.conexao = conexao
        self.usuario = ""
        self.senha = ""

    def criar(
        self,
        configuracao: ConfiguracaoLdap,
        usuario: str,
        senha: Segredo,
    ) -> ConexaoFalsa:
        del configuracao
        self.usuario = usuario
        self.senha = senha.revelar()
        return self.conexao


def test_ldaps_autentica_sem_starttls() -> None:
    conexao = ConexaoFalsa()
    fabrica = FabricaFalsa(conexao)
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma"),
        fabrica,
    )

    assert autenticador.autenticar("widson", "senha") is True
    assert fabrica.usuario == "luftfarma\\widson"
    assert conexao.tls_chamado is False
    assert conexao.desconectou is True


def test_starttls_e_negociado_antes_do_bind() -> None:
    conexao = ConexaoFalsa()
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma", TransporteLdap.STARTTLS),
        FabricaFalsa(conexao),
    )

    assert autenticador.autenticar("widson@luft.com.br", "senha") is True
    assert conexao.tls_chamado is True


def test_credencial_invalida_retorna_falso() -> None:
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma"),
        FabricaFalsa(ConexaoFalsa(autenticou=False)),
    )

    assert autenticador.autenticar("widson", "incorreta") is False


@pytest.mark.parametrize(("login", "senha"), [("", "senha"), ("widson", "")])
def test_credencial_vazia_retorna_falso(login: str, senha: str) -> None:
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma"),
        FabricaFalsa(ConexaoFalsa()),
    )

    assert autenticador.autenticar(login, senha) is False


def test_falha_de_rede_e_sanitizada_e_desconecta() -> None:
    conexao = ConexaoFalsa(erro=RuntimeError("servidor=ad senha=vazada"))
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma"),
        FabricaFalsa(conexao),
    )

    with pytest.raises(ErroAutenticacao) as captura:
        autenticador.autenticar("widson", "segredo")

    assert "senha" not in str(captura.value)
    assert "servidor=ad" not in str(captura.value)
    assert conexao.desconectou is True


def test_starttls_nao_pode_falhar_aberto() -> None:
    autenticador = AutenticadorLdap(
        ConfiguracaoLdap("ad.luft", "luftfarma", TransporteLdap.STARTTLS),
        FabricaFalsa(ConexaoFalsa(iniciou_tls=False)),
    )

    with pytest.raises(ErroAutenticacao, match="negociar TLS"):
        autenticador.autenticar("widson", "segredo")


def test_configuracao_define_portas_seguras() -> None:
    assert ConfiguracaoLdap("ad", "dominio").porta_efetiva == 636
    assert ConfiguracaoLdap("ad", "dominio", TransporteLdap.STARTTLS).porta_efetiva == 389
