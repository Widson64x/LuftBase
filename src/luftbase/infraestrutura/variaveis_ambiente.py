"""Variaveis do `.env` que a tela de Ambiente pode mostrar e alterar: so as NAO sensiveis.

Lista fechada (allowlist): a tela nunca le nem devolve qualquer outra chave do arquivo. Tokens,
enderecos do Vault, identidade do sistema, cookies e LDAP nao estao aqui e portanto nunca saem do
servidor nem podem ser alterados pela web. Cada chave tem seu validador, entao um valor invalido
(ou com quebra de linha) e recusado antes de tocar no arquivo.

A gravacao preserva comentarios, ordem e quebra de linha do arquivo, faz copia de seguranca
(`.env.bak`) e troca o arquivo de forma atomica. A aplicacao so le o `.env` ao iniciar: depois de
salvar, o servico precisa ser reiniciado.
"""

from __future__ import annotations

import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_AMBIENTES_NEGOCIO = ("producao", "homologacao", "desenvolvimento")


class ErroVariavel(ValueError):
    """Valor recusado ou chave fora da lista permitida."""


def _inteiro(minimo: int, maximo: int) -> Callable[[str], str]:
    def validar(valor: str) -> str:
        texto = valor.strip()
        if not re.fullmatch(r"\d{1,6}", texto) or not minimo <= int(texto) <= maximo:
            raise ErroVariavel(f"Informe um numero inteiro entre {minimo} e {maximo}.")
        return str(int(texto))

    return validar


def _opcoes(*permitidas: str) -> Callable[[str], str]:
    def validar(valor: str) -> str:
        texto = valor.strip().lower()
        if texto not in permitidas:
            raise ErroVariavel(f"Use um destes valores: {', '.join(permitidas)}.")
        return texto

    return validar


def _data_hora_opcional(valor: str) -> str:
    texto = valor.strip()
    if not texto:
        return ""
    try:
        datetime.fromisoformat(texto)
    except ValueError as erro:
        raise ErroVariavel("Use data e hora no formato 2026-10-06T17:00 (ou deixe vazio).") from erro
    return texto


@dataclass(frozen=True, slots=True)
class VariavelPermitida:
    chave: str
    descricao: str
    validar: Callable[[str], str]


PERMITIDAS: tuple[VariavelPermitida, ...] = (
    VariavelPermitida(
        "LUFT_AUDITORIA_DADOS_DESDE",
        "Auditoria: ignora nas análises o que veio antes desta data e hora (ex.: 2026-10-06T17:00). Vazio = sem corte.",
        _data_hora_opcional,
    ),
    VariavelPermitida(
        "LUFT_SESSAO_TTL_MINUTOS",
        "Minutos sem atividade até a sessão expirar (1 a 10080).",
        _inteiro(1, 10_080),
    ),
    VariavelPermitida(
        "LUFT_LDAP_TIMEOUT_SEGUNDOS",
        "Tempo máximo de espera do login corporativo, em segundos (1 a 60).",
        _inteiro(1, 60),
    ),
    VariavelPermitida(
        "LUFT_AUTORIZACAO_TTL_SEGUNDOS",
        "Cache das decisões de permissão, em segundos (5 a 3600).",
        _inteiro(5, 3_600),
    ),
    VariavelPermitida(
        "LUFT_AUTORIZACAO_REVISAO_TTL_SEGUNDOS",
        "Intervalo para perceber mudanças de permissão, em segundos (1 a 60).",
        _inteiro(1, 60),
    ),
    VariavelPermitida(
        "LUFT_AUTORIZACAO_MAX_CHAVES",
        "Máximo de permissões consultadas de uma vez (1 a 500).",
        _inteiro(1, 500),
    ),
    VariavelPermitida(
        "EMAIL_LINK_VALIDADE_DIAS",
        "Validade dos links enviados por e-mail, em dias (1 a 60).",
        _inteiro(1, 60),
    ),
    VariavelPermitida(
        "SQLSERVER_NEGOCIO_AMBIENTE",
        "De qual ambiente do Vault vem o banco de negócio (ERP/TMS), somente leitura.",
        _opcoes(*_AMBIENTES_NEGOCIO),
    ),
    VariavelPermitida(
        "NEGOCIO_AMBIENTE",
        "De qual ambiente do Vault vêm os bancos de negócio, somente leitura.",
        _opcoes(*_AMBIENTES_NEGOCIO),
    ),
)
_POR_CHAVE = {v.chave: v for v in PERMITIDAS}


def variavel_permitida(chave: str) -> VariavelPermitida:
    permitida = _POR_CHAVE.get((chave or "").strip())
    if permitida is None:
        raise ErroVariavel("Esta variável não pode ser consultada nem alterada pela web.")
    return permitida


def _padrao_ativa(chave: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*(?:export\s+)?{re.escape(chave)}\s*=(.*)$")


def _padrao_comentada(chave: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*#\s*{re.escape(chave)}\s*=")


def _valor_da_linha(resto: str) -> str:
    texto = resto.strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in "\"'":
        return texto[1:-1]
    return re.sub(r"\s+#.*$", "", texto).strip()


def _ler_linhas(caminho: Path) -> tuple[list[str], str]:
    bruto = caminho.read_bytes().decode("utf-8-sig")
    quebra = "\r\n" if "\r\n" in bruto else "\n"
    return bruto.splitlines(), quebra


def ler_variaveis(caminho: Path) -> list[dict[str, object]]:
    """Valor atual de cada variavel permitida (vazio = nao configurada, usa o padrao)."""

    linhas, _ = _ler_linhas(caminho)
    itens: list[dict[str, object]] = []
    for permitida in PERMITIDAS:
        padrao = _padrao_ativa(permitida.chave)
        valor = ""
        for linha in linhas:  # a ultima atribuicao vence, como no python-dotenv
            achado = padrao.match(linha)
            if achado:
                valor = _valor_da_linha(achado.group(1))
        itens.append(
            {
                "chave": permitida.chave,
                "valor": valor,
                "descricao": permitida.descricao,
                "permiteEdicao": True,
            }
        )
    return itens


def gravar_variavel(caminho: Path, chave: str, valor: str) -> tuple[str, str]:
    """Grava uma variavel permitida. Devolve (valor anterior, valor novo)."""

    permitida = variavel_permitida(chave)
    novo = permitida.validar(valor)
    linhas, quebra = _ler_linhas(caminho)

    padrao = _padrao_ativa(permitida.chave)
    indices = [i for i, linha in enumerate(linhas) if padrao.match(linha)]
    anterior = ""
    if indices:
        ultimo = indices[-1]
        anterior = _valor_da_linha(padrao.match(linhas[ultimo]).group(1))  # type: ignore[union-attr]
        linhas[ultimo] = f"{permitida.chave}={novo}"
    else:
        comentada = _padrao_comentada(permitida.chave)
        posicao = next((i for i, linha in enumerate(linhas) if comentada.match(linha)), None)
        if posicao is not None:
            linhas[posicao] = f"{permitida.chave}={novo}"
        else:
            linhas.append(f"{permitida.chave}={novo}")

    conteudo = (quebra.join(linhas) + quebra).encode("utf-8")
    copia = caminho.with_name(caminho.name + ".bak")
    shutil.copy2(caminho, copia)
    temporario = caminho.with_name(caminho.name + ".tmp")
    try:
        temporario.write_bytes(conteudo)
        shutil.copymode(caminho, temporario)
        os.replace(temporario, caminho)
    finally:
        if temporario.exists():
            temporario.unlink()
    return anterior, novo


__all__ = [
    "PERMITIDAS",
    "ErroVariavel",
    "VariavelPermitida",
    "gravar_variavel",
    "ler_variaveis",
    "variavel_permitida",
]
