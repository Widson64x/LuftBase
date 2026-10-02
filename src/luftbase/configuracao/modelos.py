"""Modelos imutaveis da configuracao de inicializacao."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from dotenv import dotenv_values

from luftbase.configuracao.ambientes import Ambiente, normalizar_ambiente
from luftbase.configuracao.caminhos_vault import validar_conexao_vault
from luftbase.configuracao.identificadores import validar_identificador_tecnico
from luftbase.nucleo.excecoes import ErroConfiguracao


def _primeiro_valor(dados: Mapping[str, Any], *chaves: str) -> Any | None:
    for chave in chaves:
        valor = dados.get(chave)
        if valor is not None and str(valor).strip():
            return valor
    return None


def _inteiro_nao_negativo(valor: object, nome: str) -> int:
    try:
        resultado = int(str(valor).strip())
    except (TypeError, ValueError) as erro:
        raise ErroConfiguracao(f"{nome} deve ser um numero inteiro.") from erro
    if resultado < 0:
        raise ErroConfiguracao(f"{nome} nao pode ser negativo.")
    return resultado


def _inteiro_intervalo(valor: object, nome: str, minimo: int, maximo: int) -> int:
    resultado = _inteiro_nao_negativo(valor, nome)
    if not minimo <= resultado <= maximo:
        raise ErroConfiguracao(f"{nome} deve estar entre {minimo} e {maximo}.")
    return resultado


def _booleano(valor: object, nome: str, *, padrao: bool) -> bool:
    if valor is None or not str(valor).strip():
        return padrao
    if isinstance(valor, bool):
        return valor
    normalizado = str(valor).strip().casefold()
    if normalizado in {"true", "1"}:
        return True
    if normalizado in {"false", "0"}:
        return False
    raise ErroConfiguracao(f"{nome} deve ser true ou false.")


@dataclass(frozen=True, slots=True)
class MetadadosSistema:
    """Metadados do sistema carregados de core.tb_sistema."""

    sistema_id: int
    nome: str
    descricao: str | None = None
    ativo: bool = True
    em_manutencao: bool = False
    icone: str | None = None
    link: str | None = None


@dataclass(frozen=True, slots=True)
class ConfiguracaoAplicacao:
    """Identidade tecnica e de exibicao da aplicacao consumidora."""

    identificador: str
    nome: str
    ambiente: Ambiente
    sistema_id: int
    versao: str | None = None
    descricao: str | None = None
    ativo: bool = True
    em_manutencao: bool = False
    icone: str | None = None
    link: str | None = None


@dataclass(frozen=True, slots=True)
class ConfiguracaoCofre:
    """Configuracao de acesso ao Vault sem revelar tokens em representacoes."""

    endereco: str
    namespace: str = "luft"
    token_protegido: str | None = field(default=None, repr=False)
    token_acesso: str | None = field(default=None, repr=False)
    conexao_diretorio: str = "user.services"


@dataclass(frozen=True, slots=True)
class ConfiguracaoDiretorio:
    """Parametros nao sensiveis do diretorio usado para autenticacao LDAP."""

    servidor: str
    dominio: str
    transporte: Literal["ldaps", "starttls"] = "ldaps"
    porta: int | None = None
    timeout_segundos: int = 5

    def __post_init__(self) -> None:
        if not self.servidor.strip():
            raise ErroConfiguracao("LUFT_LDAP_SERVIDOR e obrigatorio.")
        if not self.dominio.strip():
            raise ErroConfiguracao("LUFT_LDAP_DOMINIO e obrigatorio.")
        if self.porta is not None and not 1 <= self.porta <= 65535:
            raise ErroConfiguracao("LUFT_LDAP_PORTA esta fora do intervalo valido.")
        if not 1 <= self.timeout_segundos <= 60:
            raise ErroConfiguracao("LUFT_LDAP_TIMEOUT_SEGUNDOS deve estar entre 1 e 60.")


@dataclass(frozen=True, slots=True)
class ConfiguracaoSessao:
    """Politica central de cookie e expiracao da sessao corporativa."""

    nome_cookie: str = "luft_sessao"
    dominio_cookie: str | None = None
    caminho_cookie: str = "/"
    same_site: Literal["Lax", "Strict", "None"] = "Lax"
    ttl_minutos: int = 10
    cookie_seguro: bool = False
    # Excecao explicita ao cookie Secure em producao, para ambientes servidos por HTTP
    # (ex.: homologacao sem TLS). So informa a decisao; quem decide e cookie_seguro.
    cookie_inseguro_permitido: bool = False

    def __post_init__(self) -> None:
        if not self.nome_cookie.strip() or any(
            caractere.isspace() for caractere in self.nome_cookie
        ):
            raise ErroConfiguracao("LUFT_SESSAO_COOKIE_NOME e invalido.")
        if not self.caminho_cookie.startswith("/"):
            raise ErroConfiguracao("LUFT_SESSAO_COOKIE_CAMINHO deve iniciar com '/'.")
        if not 1 <= self.ttl_minutos <= 10_080:
            raise ErroConfiguracao("LUFT_SESSAO_TTL_MINUTOS deve estar entre 1 e 10080.")
        if self.same_site == "None" and not self.cookie_seguro:
            raise ErroConfiguracao("SameSite=None exige cookie seguro.")


@dataclass(frozen=True, slots=True)
class ConfiguracaoAutorizacao:
    """Limites de cache e consulta da autorizacao sob demanda."""

    ttl_resultado_segundos: int = 300
    ttl_revisao_segundos: int = 5
    maximo_chaves_consulta: int = 100

    def __post_init__(self) -> None:
        if not 5 <= self.ttl_resultado_segundos <= 3_600:
            raise ErroConfiguracao("LUFT_AUTORIZACAO_TTL_SEGUNDOS deve estar entre 5 e 3600.")
        if not 1 <= self.ttl_revisao_segundos <= 60:
            raise ErroConfiguracao("LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS deve estar entre 1 e 60.")
        if not 1 <= self.maximo_chaves_consulta <= 500:
            raise ErroConfiguracao("LUFT_AUTORIZACAO_MAX_CHAVES deve estar entre 1 e 500.")


@dataclass(frozen=True, slots=True)
class ConfiguracaoLuftBase:
    """Configuracao raiz validada uma unica vez durante a inicializacao."""

    aplicacao: ConfiguracaoAplicacao
    cofre: ConfiguracaoCofre
    diretorio: ConfiguracaoDiretorio
    sessao: ConfiguracaoSessao
    autorizacao: ConfiguracaoAutorizacao

    def validar_para_inicializacao(self) -> None:
        """Valida os dados exigidos antes de qualquer chamada externa."""

        endereco = urlsplit(self.cofre.endereco)
        if endereco.scheme not in {"http", "https"} or not endereco.hostname:
            raise ErroConfiguracao("LUFT_VAULT_ENDERECO deve ser uma URL HTTP ou HTTPS valida.")
        if not self.cofre.token_protegido:
            raise ErroConfiguracao("LUFT_VAULT_TOKEN e obrigatorio na inicializacao.")
        if not self.cofre.token_acesso:
            raise ErroConfiguracao("LUFT_TOKEN_ACESSO e obrigatorio na inicializacao.")
        valores_sensiveis = (self.cofre.token_protegido, self.cofre.token_acesso)
        if any(valor.startswith("<") and valor.endswith(">") for valor in valores_sensiveis):
            raise ErroConfiguracao(
                "Os placeholders de token devem ser substituidos antes da inicializacao."
            )
        if self.aplicacao.ambiente is Ambiente.PRODUCAO and not self.aplicacao.versao:
            raise ErroConfiguracao("LUFT_APLICACAO_VERSAO e obrigatoria no ambiente de producao.")

    def com_metadados_sistema(
        self,
        metadados: MetadadosSistema,
        *,
        identificador: str | None = None,
    ) -> ConfiguracaoLuftBase:
        """Retorna uma nova configuracao enriquecida com os metadados de core.tb_sistema."""

        identificador_resolvido = validar_identificador_tecnico(
            identificador or self.aplicacao.identificador
        )
        if metadados.sistema_id != self.aplicacao.sistema_id:
            raise ErroConfiguracao("O cadastro retornado pertence a outro sistema.")

        nova_aplicacao = ConfiguracaoAplicacao(
            identificador=identificador_resolvido,
            nome=metadados.nome,
            ambiente=self.aplicacao.ambiente,
            sistema_id=metadados.sistema_id,
            versao=self.aplicacao.versao,
            descricao=metadados.descricao,
            ativo=metadados.ativo,
            em_manutencao=metadados.em_manutencao,
            icone=metadados.icone,
            link=metadados.link,
        )
        return ConfiguracaoLuftBase(
            aplicacao=nova_aplicacao,
            cofre=self.cofre,
            diretorio=self.diretorio,
            sessao=self.sessao,
            autorizacao=self.autorizacao,
        )

    @classmethod
    def de_ambiente(
        cls,
        sobreposicoes: Mapping[str, Any] | None = None,
        arquivo_env: str | Path | None = None,
    ) -> ConfiguracaoLuftBase:
        """Carrega `.env`, ambiente do processo e sobreposicoes, nesta ordem."""

        caminho_env = Path(arquivo_env) if arquivo_env is not None else Path.cwd() / ".env"
        dados: dict[str, Any] = {}
        if caminho_env.is_file():
            dados.update(dotenv_values(caminho_env))
        dados.update(os.environ)
        if sobreposicoes:
            dados.update(sobreposicoes)
        return cls.de_mapeamento(dados)

    @classmethod
    def de_mapeamento(cls, dados: Mapping[str, Any]) -> ConfiguracaoLuftBase:
        """Cria a configuracao usando nomes canonicos e aliases temporarios do legado."""

        sistema_id_bruto = _primeiro_valor(dados, "LUFT_SISTEMA_ID", "SISTEMA_ID")
        if sistema_id_bruto is None:
            raise ErroConfiguracao("LUFT_SISTEMA_ID e obrigatorio.")
        sistema_id = _inteiro_intervalo(
            sistema_id_bruto,
            "LUFT_SISTEMA_ID",
            0,
            2_147_483_647,
        )

        ambiente = normalizar_ambiente(
            _primeiro_valor(dados, "LUFT_AMBIENTE", "APP_ENV") or "desenvolvimento"
        )
        endereco_vault = str(
            _primeiro_valor(dados, "LUFT_VAULT_ENDERECO", "VAULT_ADDR") or ""
        ).strip()
        if not endereco_vault:
            raise ErroConfiguracao("LUFT_VAULT_ENDERECO e obrigatorio.")

        namespace = str(
            _primeiro_valor(dados, "LUFT_VAULT_NAMESPACE", "VAULT_NAMESPACE") or "luft"
        ).strip()
        conexao_diretorio = validar_conexao_vault(
            _primeiro_valor(dados, "LUFT_VAULT_CONEXAO_DIRETORIO") or "user.services"
        )

        versao_bruta = _primeiro_valor(dados, "LUFT_APLICACAO_VERSAO", "APP_VERSION")
        versao = str(versao_bruta).strip() if versao_bruta is not None else None
        token_protegido_bruto = _primeiro_valor(dados, "LUFT_VAULT_TOKEN", "VAULT_TOKEN")
        token_protegido = (
            str(token_protegido_bruto).strip() if token_protegido_bruto is not None else None
        )
        token_acesso_bruto = _primeiro_valor(dados, "LUFT_TOKEN_ACESSO", "TOKEN_ACESSO")
        token_acesso = str(token_acesso_bruto).strip() if token_acesso_bruto is not None else None

        servidor_ldap = str(_primeiro_valor(dados, "LUFT_LDAP_SERVIDOR") or "").strip()
        dominio_ldap = str(_primeiro_valor(dados, "LUFT_LDAP_DOMINIO") or "").strip()
        transporte_ldap = (
            str(_primeiro_valor(dados, "LUFT_LDAP_TRANSPORTE") or "ldaps").strip().casefold()
        )
        if transporte_ldap not in {"ldaps", "starttls"}:
            raise ErroConfiguracao("LUFT_LDAP_TRANSPORTE deve ser ldaps ou starttls.")
        porta_ldap_bruta = _primeiro_valor(dados, "LUFT_LDAP_PORTA")
        porta_ldap = (
            _inteiro_intervalo(porta_ldap_bruta, "LUFT_LDAP_PORTA", 1, 65535)
            if porta_ldap_bruta is not None
            else None
        )
        timeout_ldap = _inteiro_intervalo(
            _primeiro_valor(dados, "LUFT_LDAP_TIMEOUT_SEGUNDOS") or 5,
            "LUFT_LDAP_TIMEOUT_SEGUNDOS",
            1,
            60,
        )

        nome_cookie = str(
            _primeiro_valor(dados, "LUFT_SESSAO_COOKIE_NOME") or "luft_sessao"
        ).strip()
        dominio_cookie_bruto = _primeiro_valor(dados, "LUFT_SESSAO_COOKIE_DOMINIO")
        dominio_cookie = (
            str(dominio_cookie_bruto).strip() if dominio_cookie_bruto is not None else None
        )
        caminho_cookie = str(_primeiro_valor(dados, "LUFT_SESSAO_COOKIE_CAMINHO") or "/").strip()
        same_site_bruto = (
            str(_primeiro_valor(dados, "LUFT_SESSAO_COOKIE_SAMESITE") or "Lax").strip().casefold()
        )
        same_site_opcoes = {"lax": "Lax", "strict": "Strict", "none": "None"}
        if same_site_bruto not in same_site_opcoes:
            raise ErroConfiguracao("LUFT_SESSAO_COOKIE_SAMESITE deve ser Lax, Strict ou None.")
        cookie_seguro_configurado = _booleano(
            _primeiro_valor(dados, "LUFT_SESSAO_COOKIE_SEGURO"),
            "LUFT_SESSAO_COOKIE_SEGURO",
            padrao=False,
        )
        # Producao exige cookie Secure. Quem serve por HTTP (sem TLS) precisa declarar a
        # excecao de forma explicita; LUFT_SESSAO_COOKIE_SEGURO=true ainda prevalece.
        cookie_inseguro_permitido = _booleano(
            _primeiro_valor(dados, "LUFT_PERMITIR_COOKIE_INSEGURO"),
            "LUFT_PERMITIR_COOKIE_INSEGURO",
            padrao=False,
        )
        cookie_seguro = cookie_seguro_configurado or (
            ambiente is Ambiente.PRODUCAO and not cookie_inseguro_permitido
        )
        ttl_minutos = _inteiro_intervalo(
            _primeiro_valor(dados, "LUFT_SESSAO_TTL_MINUTOS") or 10,
            "LUFT_SESSAO_TTL_MINUTOS",
            1,
            10_080,
        )
        ttl_autorizacao = _inteiro_intervalo(
            _primeiro_valor(dados, "LUFT_AUTORIZACAO_TTL_SEGUNDOS") or 300,
            "LUFT_AUTORIZACAO_TTL_SEGUNDOS",
            5,
            3_600,
        )
        ttl_revisao = _inteiro_intervalo(
            _primeiro_valor(dados, "LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS") or 5,
            "LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS",
            1,
            60,
        )
        maximo_chaves = _inteiro_intervalo(
            _primeiro_valor(dados, "LUFT_AUTORIZACAO_MAX_CHAVES") or 100,
            "LUFT_AUTORIZACAO_MAX_CHAVES",
            1,
            500,
        )

        return cls(
            aplicacao=ConfiguracaoAplicacao(
                identificador="",
                nome="",
                ambiente=ambiente,
                sistema_id=sistema_id,
                versao=versao,
            ),
            cofre=ConfiguracaoCofre(
                endereco=endereco_vault,
                namespace=namespace,
                token_protegido=token_protegido,
                token_acesso=token_acesso,
                conexao_diretorio=conexao_diretorio,
            ),
            diretorio=ConfiguracaoDiretorio(
                servidor=servidor_ldap,
                dominio=dominio_ldap,
                transporte=cast(Literal["ldaps", "starttls"], transporte_ldap),
                porta=porta_ldap,
                timeout_segundos=timeout_ldap,
            ),
            sessao=ConfiguracaoSessao(
                nome_cookie=nome_cookie,
                dominio_cookie=dominio_cookie,
                caminho_cookie=caminho_cookie,
                same_site=cast(
                    Literal["Lax", "Strict", "None"],
                    same_site_opcoes[same_site_bruto],
                ),
                ttl_minutos=ttl_minutos,
                cookie_seguro=cookie_seguro,
                cookie_inseguro_permitido=(
                    cookie_inseguro_permitido
                    and ambiente is Ambiente.PRODUCAO
                    and not cookie_seguro
                ),
            ),
            autorizacao=ConfiguracaoAutorizacao(
                ttl_resultado_segundos=ttl_autorizacao,
                ttl_revisao_segundos=ttl_revisao,
                maximo_chaves_consulta=maximo_chaves,
            ),
        )
