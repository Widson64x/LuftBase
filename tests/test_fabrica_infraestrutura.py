"""Testes da composicao de infraestrutura sem Vault ou bancos reais."""

from collections.abc import Mapping

from luftbase.configuracao.caminhos_vault import resolver_caminhos_vault
from luftbase.configuracao.modelos import ConfiguracaoLuftBase
from luftbase.infraestrutura import fabrica as modulo_fabrica
from luftbase.infraestrutura.cofre.credenciais import (
    CredencialBanco,
    CredencialRedis,
    Segredo,
)
from luftbase.infraestrutura.cofre.criptografia import DesprotetorFernet
from luftbase.infraestrutura.fabrica import FabricaInfraestruturaPadrao


class ProvedorFalso:
    """Nao usado diretamente; documenta o limite substituido no teste."""

    def validar_acesso(self) -> None:
        return None

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        return {}


class ClienteVaultFalso:
    """Registra o token e devolve payloads conforme o caminho solicitado."""

    token_recebido = ""
    caminhos: list[str] = []

    def __init__(self, endereco: str, token: Segredo) -> None:
        assert endereco == "http://vault:8200"
        type(self).token_recebido = token.revelar()

    def validar_acesso(self) -> None:
        return None

    def ler_segredo(self, caminho: str) -> Mapping[str, object]:
        type(self).caminhos.append(caminho)
        if caminho.endswith("integracoes/email"):
            return {
                "host": "smtp.gmail.com",
                "porta": "587",
                "seguranca": "starttls",
                "usuario": "conta@luft.com",
                "senha": "senha-smtp",
            }
        if caminho.endswith("redis/sessoes"):
            return {
                "host": "redis",
                "porta": "6379",
                "banco": "0",
                "senha": "senha-redis",
                "tls": "true",
                "chave_assinatura_sessao": "x" * 64,
            }
        comum = {
            "host": "db",
            "nome_banco": "banco",
            "porta": "1433" if "sqlserver" in caminho else "5432",
            "senha": "senha",
            "usuario": "svc_app",
        }
        if "sqlserver" in caminho:
            return {**comum, "tipo_banco": "sqlserver"}
        if "/bancos/postgresql/sistemas/" in caminho:
            return {
                "conexao": "luft-web",
                "senha": "senha",
                "usuario": "svc_app",
                "esquema": "luft_workspace",
                "identificador": "luft-workspace",
                "sistema_id": 0,
            }
        return {**comum, "tipo_banco": "postgresql", "esquema": "luft_workspace"}


class FabricaBancosFalsa:
    """Captura as credenciais que seriam usadas na criacao das engines."""

    def __init__(self) -> None:
        self.credenciais: tuple[CredencialBanco, CredencialBanco] | None = None
        self.catalogo = object()

    def criar(self, diretorio: CredencialBanco, postgresql: CredencialBanco):
        self.credenciais = (diretorio, postgresql)
        return self.catalogo


class FabricaRedisFalsa:
    """Captura a credencial sem criar sockets Redis."""

    def __init__(self) -> None:
        self.credencial: CredencialRedis | None = None
        self.armazenamento = object()

    def criar(self, credencial: CredencialRedis):  # type: ignore[no-untyped-def]
        self.credencial = credencial
        return self.armazenamento


def test_fabrica_nao_conecta_ao_ser_construida() -> None:
    fabrica = FabricaInfraestruturaPadrao()

    assert fabrica is not None


def test_configuracao_com_token_compativel_pode_ser_validada() -> None:
    protetor = DesprotetorFernet("chave")
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": protetor.proteger("token-real-simulado"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
    )

    configuracao.validar_para_inicializacao()

    assert caminhos.postgresql == "luft/desenvolvimento/bancos/postgresql/sistemas/0"


def test_fabrica_resolve_token_caminhos_e_credenciais(monkeypatch) -> None:
    ClienteVaultFalso.caminhos = []
    protetor = DesprotetorFernet("chave")
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": protetor.proteger("token-real-simulado"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
    )
    fabrica_bancos = FabricaBancosFalsa()
    fabrica_redis = FabricaRedisFalsa()
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", ClienteVaultFalso)

    recursos = FabricaInfraestruturaPadrao(
        fabrica_bancos,  # type: ignore[arg-type]
        fabrica_redis,  # type: ignore[arg-type]
    ).criar(
        configuracao,
        caminhos,
    )

    assert ClienteVaultFalso.token_recebido == "token-real-simulado"
    assert ClienteVaultFalso.caminhos == [
        caminhos.sqlserver_diretorio,
        caminhos.postgresql,
        f"{caminhos.postgresql_conexoes}/luft-web",
        caminhos.sessoes_redis,
        caminhos.email,
    ]
    assert recursos.bancos is fabrica_bancos.catalogo
    assert fabrica_bancos.credenciais is not None
    assert fabrica_bancos.credenciais[1].esquema == "luft_workspace"
    assert recursos.armazenamento_sessoes is fabrica_redis.armazenamento
    assert fabrica_redis.credencial is not None
    assert recursos.chave_assinatura_sessao.revelar() == "x" * 64
    assert recursos.credencial_email is not None
    assert recursos.credencial_email.remetente == "conta@luft.com"


def test_fabrica_padrao_fallback_memoria_quando_redis_ausente_em_desenvolvimento(
    monkeypatch,
) -> None:
    from luftbase.infraestrutura.fabrica import ArmazenamentoSessoesDevLocal
    from luftbase.nucleo.excecoes import SegredoNaoEncontrado

    class ClienteSemRedis(ClienteVaultFalso):
        def ler_segredo(self, caminho: str) -> Mapping[str, object]:
            if caminho.endswith("redis/sessoes"):
                raise SegredoNaoEncontrado("Sem redis")
            return super().ler_segredo(caminho)

    protetor = DesprotetorFernet("chave")
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": protetor.proteger("token-real-simulado"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
    )
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", ClienteSemRedis)

    recursos = FabricaInfraestruturaPadrao(
        FabricaBancosFalsa(),  # type: ignore[arg-type]
        FabricaRedisFalsa(),  # type: ignore[arg-type]
    ).criar(configuracao, caminhos)

    assert isinstance(recursos.armazenamento_sessoes, ArmazenamentoSessoesDevLocal)
    assert len(recursos.chave_assinatura_sessao.revelar()) >= 32


def test_fabrica_padrao_usa_postgresql_sem_redis_em_producao(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
    from luftbase.nucleo.excecoes import SegredoNaoEncontrado

    class ClienteSemRedis(ClienteVaultFalso):
        def ler_segredo(self, caminho: str) -> Mapping[str, object]:
            if caminho.endswith("redis/sessoes"):
                raise SegredoNaoEncontrado("Sem redis")
            return super().ler_segredo(caminho)

    protetor = DesprotetorFernet("chave")
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "producao",
            "LUFT_APLICACAO_VERSAO": "1.0.0",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": protetor.proteger("token-real-simulado"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
    )
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", ClienteSemRedis)

    fabrica_bancos = FabricaBancosFalsa()
    fabrica_bancos.catalogo = MagicMock(core=MagicMock())

    recursos = FabricaInfraestruturaPadrao(
        fabrica_bancos,  # type: ignore[arg-type]
        FabricaRedisFalsa(),  # type: ignore[arg-type]
    ).criar(configuracao, caminhos)

    assert isinstance(recursos.armazenamento_sessoes, ArmazenamentoSessoesPostgreSQL)


def test_armazenamento_sessoes_dev_local(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from luftbase.infraestrutura.fabrica import ArmazenamentoSessoesDevLocal

    banco = tmp_path / "teste_sessoes.sqlite"
    armazenamento = ArmazenamentoSessoesDevLocal(banco)

    assert armazenamento.verificar_saude() is True
    assert armazenamento.obter("chave1") is None

    armazenamento.salvar("chave1", b"dados1", 300)
    assert armazenamento.obter("chave1") == b"dados1"

    # Sobrevive a nova conexao (como se fosse novo processo Flask apos reload)
    novo_armazenamento = ArmazenamentoSessoesDevLocal(banco)
    assert novo_armazenamento.obter("chave1") == b"dados1"

    novo_armazenamento.remover("chave1")
    assert novo_armazenamento.obter("chave1") is None


def test_fabrica_padrao_fallback_postgresql_quando_bancos_possui_core(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from luftbase.identidade.armazenamento_postgresql import ArmazenamentoSessoesPostgreSQL
    from luftbase.nucleo.excecoes import SegredoNaoEncontrado

    class ClienteSemRedis(ClienteVaultFalso):
        def ler_segredo(self, caminho: str) -> Mapping[str, object]:
            if caminho.endswith("redis/sessoes"):
                raise SegredoNaoEncontrado("Sem redis")
            return super().ler_segredo(caminho)

    protetor = DesprotetorFernet("chave")
    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": protetor.proteger("token-real-simulado"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=configuracao.aplicacao.sistema_id,
    )
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", ClienteSemRedis)

    fabrica_bancos = FabricaBancosFalsa()
    banco_core_mock = MagicMock()
    fabrica_bancos.catalogo = MagicMock(core=banco_core_mock)

    recursos = FabricaInfraestruturaPadrao(
        fabrica_bancos,  # type: ignore[arg-type]
        FabricaRedisFalsa(),  # type: ignore[arg-type]
    ).criar(configuracao, caminhos)

    assert isinstance(recursos.armazenamento_sessoes, ArmazenamentoSessoesPostgreSQL)


def test_diretorio_usa_conexao_nomeada_e_cai_no_caminho_antigo_com_aviso(
    monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    import logging

    from luftbase.nucleo.excecoes import SegredoNaoEncontrado

    class SoCaminhoAntigo(ClienteVaultFalso):
        def ler_segredo(self, caminho: str) -> Mapping[str, object]:
            if "conexoes/user.services" in caminho:
                raise SegredoNaoEncontrado(caminho)
            return super().ler_segredo(caminho)

    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": DesprotetorFernet("chave").proteger("token"),
            "LUFT_TOKEN_ACESSO": "chave",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=0,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", SoCaminhoAntigo)
    ClienteVaultFalso.caminhos = []

    with caplog.at_level(logging.WARNING, logger="luftbase"):
        FabricaInfraestruturaPadrao(FabricaBancosFalsa(), FabricaRedisFalsa()).criar(  # type: ignore[arg-type]
            configuracao, caminhos
        )

    assert (
        caminhos.sqlserver_diretorio
        == "luft/desenvolvimento/bancos/sqlserver/conexoes/user.services"
    )
    assert caminhos.sqlserver_legado in ClienteVaultFalso.caminhos
    assert "caminho antigo" in caplog.text


def test_diretorio_sem_nenhum_segredo_aponta_o_caminho_novo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import pytest

    from luftbase.nucleo.excecoes import SegredoNaoEncontrado

    class SemSqlServer(ClienteVaultFalso):
        def ler_segredo(self, caminho: str) -> Mapping[str, object]:
            if "sqlserver" in caminho:
                raise SegredoNaoEncontrado(caminho)
            return super().ler_segredo(caminho)

    configuracao = ConfiguracaoLuftBase.de_mapeamento(
        {
            "LUFT_SISTEMA_ID": "0",
            "LUFT_AMBIENTE": "desenvolvimento",
            "LUFT_VAULT_ENDERECO": "http://vault:8200",
            "LUFT_LDAP_SERVIDOR": "ad.luft",
            "LUFT_LDAP_DOMINIO": "luftfarma",
            "LUFT_VAULT_TOKEN": DesprotetorFernet("chave").proteger("token"),
            "LUFT_TOKEN_ACESSO": "chave",
            "LUFT_VAULT_CONEXAO_DIRETORIO": "diretorio.leitura",
        }
    )
    caminhos = resolver_caminhos_vault(
        ambiente=configuracao.aplicacao.ambiente,
        sistema_id=0,
        conexao_diretorio=configuracao.cofre.conexao_diretorio,
    )
    monkeypatch.setattr(modulo_fabrica, "ClienteVaultHvac", SemSqlServer)

    with pytest.raises(SegredoNaoEncontrado, match="conexoes/diretorio.leitura"):
        FabricaInfraestruturaPadrao(FabricaBancosFalsa(), FabricaRedisFalsa()).criar(  # type: ignore[arg-type]
            configuracao, caminhos
        )
