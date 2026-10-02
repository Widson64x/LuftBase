"""Convencao unica para caminhos de segredos da plataforma."""

from __future__ import annotations

import re
from dataclasses import dataclass

from luftbase.configuracao.ambientes import Ambiente, normalizar_ambiente
from luftbase.nucleo.excecoes import ErroConfiguracao


@dataclass(frozen=True, slots=True)
class CaminhosVault:
    """Caminhos resolvidos para as dependencias padrao de uma aplicacao."""

    sqlserver: str
    postgresql: str
    sessoes_redis: str
    postgresql_conexoes: str = ""
    email: str = ""
    sqlserver_conexoes: str = ""
    sqlserver_diretorio: str = ""

    @property
    def sqlserver_legado(self) -> str:
        """Caminho antigo `luft/{ambiente}/sqlserver`, usado so como reserva com aviso."""

        return self.sqlserver


def _validar_namespace(valor: object) -> str:
    namespace = str(valor or "luft").strip().strip("/")
    if not namespace or "/" in namespace or "\\" in namespace:
        raise ErroConfiguracao("O namespace do Vault deve ser um unico segmento.")
    return namespace


_PADRAO_CONEXAO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def validar_conexao_vault(valor: object) -> str:
    """Valida o nome de uma conexao nomeada (um unico segmento do caminho)."""

    conexao = str(valor or "").strip()
    if not _PADRAO_CONEXAO.fullmatch(conexao):
        raise ErroConfiguracao(
            "O nome da conexao do Vault deve ser um unico segmento com letras, numeros, "
            "ponto, hifen ou sublinhado."
        )
    return conexao


def resolver_caminhos_vault(
    *,
    ambiente: Ambiente | str,
    sistema_id: int,
    namespace: str = "luft",
    conexao_diretorio: str = "user.services",
) -> CaminhosVault:
    """Monta caminhos sem depender de valores completos no arquivo `.env`."""

    ambiente_resolvido = normalizar_ambiente(ambiente)
    namespace_resolvido = _validar_namespace(namespace)
    raiz = f"{namespace_resolvido}/{ambiente_resolvido.value}"

    if isinstance(sistema_id, bool) or sistema_id < 0:
        raise ErroConfiguracao("LUFT_SISTEMA_ID deve ser um inteiro nao negativo.")
    conexao = validar_conexao_vault(conexao_diretorio)
    return CaminhosVault(
        sqlserver=f"{raiz}/sqlserver",
        sqlserver_conexoes=f"{raiz}/bancos/sqlserver/conexoes",
        sqlserver_diretorio=f"{raiz}/bancos/sqlserver/conexoes/{conexao}",
        postgresql=f"{raiz}/bancos/postgresql/sistemas/{sistema_id}",
        sessoes_redis=f"{raiz}/redis/sessoes",
        postgresql_conexoes=f"{raiz}/bancos/postgresql/conexoes",
        email=f"{raiz}/integracoes/email",
    )
