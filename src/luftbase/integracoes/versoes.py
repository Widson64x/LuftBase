"""Versoes dos componentes instalados e comparacao do LuftBase com o GitHub."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import metadata

REPOSITORIO_PADRAO = "Widson64x/LuftBase"
_PADRAO_VERSAO = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_ORDEM_PRE = {"a": 0, "b": 1, "rc": 2}

# Pacotes que a plataforma mostra no painel (nome da distribuicao, rotulo, papel).
COMPONENTES: tuple[tuple[str, str, str], ...] = (
    ("Flask", "Flask", "Framework web"),
    ("SQLAlchemy", "SQLAlchemy", "Acesso a dados"),
    ("alembic", "Alembic", "Migracoes do core"),
    ("psycopg", "Psycopg", "Driver PostgreSQL"),
    ("pyodbc", "pyodbc", "Driver SQL Server"),
    ("oracledb", "python-oracledb", "Driver Oracle"),
    ("hvac", "hvac", "Cliente do Vault"),
    ("redis", "redis-py", "Cliente Redis"),
    ("ldap3", "ldap3", "Login corporativo"),
    ("cryptography", "cryptography", "Criptografia"),
    ("waitress", "Waitress", "Servidor WSGI"),
)


def interpretar_versao(texto: str) -> tuple[int, int, int, int, int] | None:
    """Ordena `0.1.0a56`/`v0.1.0` (final > rc > b > a). Devolve None para formato desconhecido."""

    achado = _PADRAO_VERSAO.fullmatch(texto.strip())
    if achado is None:
        return None
    maior, menor, correcao, pre, numero = achado.groups()
    if pre is None:
        return int(maior), int(menor), int(correcao), 9, 0
    return int(maior), int(menor), int(correcao), _ORDEM_PRE[pre], int(numero)


def versao_instalada(distribuicao: str) -> str | None:
    """Versao de um pacote instalado, ou None quando nao esta instalado."""

    try:
        return metadata.version(distribuicao)
    except metadata.PackageNotFoundError:
        return None


def listar_componentes() -> list[dict[str, str | bool]]:
    """Componentes de terceiros e o Python, com a versao instalada."""

    itens: list[dict[str, str | bool]] = [
        {
            "nome": "Python",
            "papel": "Interpretador",
            "versao": ".".join(str(parte) for parte in sys.version_info[:3]),
            "instalado": True,
        }
    ]
    for distribuicao, rotulo, papel in COMPONENTES:
        versao = versao_instalada(distribuicao)
        itens.append(
            {
                "nome": rotulo,
                "papel": papel,
                "versao": versao or "nao instalado",
                "instalado": versao is not None,
            }
        )
    return itens


@dataclass(frozen=True, slots=True)
class ResultadoVersao:
    """Resultado da comparacao entre a versao instalada e a ultima tag do GitHub."""

    instalada: str
    ultima: str | None
    situacao: str  # atualizada | desatualizada | a_frente | indisponivel
    repositorio: str
    verificada_em: str
    detalhe: str = ""

    @property
    def url_tags(self) -> str:
        return f"https://github.com/{self.repositorio}/tags"

    def como_dict(self) -> dict[str, str | None]:
        return {
            "instalada": self.instalada,
            "ultima": self.ultima,
            "situacao": self.situacao,
            "repositorio": self.repositorio,
            "url": self.url_tags,
            "verificada_em": self.verificada_em,
            "detalhe": self.detalhe,
        }


def comparar_versoes(instalada: str, ultima: str | None) -> str:
    """Classifica a versao instalada frente a ultima publicada."""

    if ultima is None:
        return "indisponivel"
    atual = interpretar_versao(instalada)
    remota = interpretar_versao(ultima)
    if atual is None or remota is None:
        return "indisponivel"
    if atual == remota:
        return "atualizada"
    return "desatualizada" if atual < remota else "a_frente"


def _baixar_tags(repositorio: str, token: str | None, timeout: float) -> list[str]:
    requisicao = urllib.request.Request(
        f"https://api.github.com/repos/{repositorio}/tags?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "luftbase-painel",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
        carga = json.loads(resposta.read().decode("utf-8"))
    return [str(item["name"]) for item in carga if isinstance(item, dict) and "name" in item]


class VerificadorVersao:
    """Consulta as tags do GitHub com cache (15 min; falha 2 min), sem derrubar o painel."""

    def __init__(
        self,
        *,
        repositorio: str | None = None,
        token: str | None = None,
        buscar_tags: Callable[[str, str | None, float], list[str]] = _baixar_tags,
        relogio: Callable[[], float] = time.monotonic,
        timeout: float = 4.0,
    ) -> None:
        self._repositorio = repositorio or os.environ.get(
            "LUFT_BASE_REPOSITORIO", REPOSITORIO_PADRAO
        )
        self._token = token or os.environ.get("LUFT_GITHUB_TOKEN") or None
        self._buscar = buscar_tags
        self._relogio = relogio
        self._timeout = timeout
        self._trava = threading.Lock()
        self._cache: tuple[float, float, ResultadoVersao] | None = None

    def verificar(self, instalada: str, *, forcar: bool = False) -> ResultadoVersao:
        with self._trava:
            agora = self._relogio()
            if self._cache and not forcar:
                criado, validade, resultado = self._cache
                if agora - criado < validade and resultado.instalada == instalada:
                    return resultado
            resultado = self._consultar(instalada)
            validade = 900.0 if resultado.situacao != "indisponivel" else 120.0
            self._cache = (agora, validade, resultado)
            return resultado

    def _consultar(self, instalada: str) -> ResultadoVersao:
        carimbo = datetime.now(UTC).isoformat(timespec="seconds")
        try:
            tags = self._buscar(self._repositorio, self._token, self._timeout)
        except urllib.error.HTTPError as erro:
            motivo = (
                "repositorio privado: informe LUFT_GITHUB_TOKEN"
                if erro.code in (401, 403, 404)
                else f"GitHub respondeu HTTP {erro.code}"
            )
            return ResultadoVersao(
                instalada, None, "indisponivel", self._repositorio, carimbo, motivo
            )
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            return ResultadoVersao(
                instalada,
                None,
                "indisponivel",
                self._repositorio,
                carimbo,
                "sem acesso ao GitHub a partir deste servidor",
            )
        validas = [(interpretar_versao(tag), tag) for tag in tags]
        validas = [(chave, tag) for chave, tag in validas if chave is not None]
        if not validas:
            return ResultadoVersao(
                instalada, None, "indisponivel", self._repositorio, carimbo, "nenhuma tag de versao"
            )
        ultima = max(validas, key=lambda par: par[0])[1].lstrip("v")
        return ResultadoVersao(
            instalada, ultima, comparar_versoes(instalada, ultima), self._repositorio, carimbo
        )


__all__ = [
    "REPOSITORIO_PADRAO",
    "ResultadoVersao",
    "VerificadorVersao",
    "comparar_versoes",
    "interpretar_versao",
    "listar_componentes",
    "versao_instalada",
]
