"""Servicos das aplicacoes no host: status e ciclo de vida, descobertos pelo NOME do sistema.

Sem lista no `.env` e sem nomes fixos: o servico de cada aplicacao tem o nome da propria
aplicacao no catalogo (`core.tb_sistema.nome_sistema`):

- Linux (systemd): minusculo + `.service`  -> `Luft-ConnectAir` vira `luft-connectair.service`;
- Windows (servico/NSSM): o proprio nome   -> `Luft-ConnectAir`.

Seguranca: so se opera sobre servicos de sistemas cadastrados (a rota valida o id contra o
catalogo), o nome passa por uma lista de caracteres permitidos e os comandos sao executados SEM
shell, com lista de argumentos e tempo limite.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

_PADRAO_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
_TEMPO_LIMITE_SEGUNDOS = 20.0


class PlataformaHost(StrEnum):
    LINUX = "linux"
    WINDOWS = "windows"


class StatusServico(StrEnum):
    EM_EXECUCAO = "RUNNING"
    PARADO = "STOPPED"
    INICIANDO = "STARTING"
    NAO_ENCONTRADO = "NOT_FOUND"
    INDISPONIVEL = "UNAVAILABLE"


ACOES = ("iniciar", "parar", "reiniciar")


@dataclass(frozen=True, slots=True)
class ResultadoComando:
    codigo: int
    saida: str
    erro: str


Executor = Callable[[list[str]], ResultadoComando]


class ErroServicoHost(Exception):
    """Falha esperada ao operar um servico (permissao, nome invalido, tempo esgotado)."""


def plataforma_do_host() -> PlataformaHost:
    return PlataformaHost.WINDOWS if sys.platform.startswith("win") else PlataformaHost.LINUX


def nome_do_servico(nome_sistema: str, plataforma: PlataformaHost) -> str | None:
    """Nome do servico de uma aplicacao, ou None se o nome do sistema nao for seguro."""

    base = (nome_sistema or "").strip()
    if not _PADRAO_NOME.fullmatch(base):
        return None
    if plataforma is PlataformaHost.LINUX:
        return f"{base.lower()}.service"
    return base


_DIRETORIOS_PADRAO = ("/usr/bin", "/bin", "/usr/sbin", "/sbin", "/usr/local/bin")


def _binario(nome: str) -> str:
    """Caminho do executavel. Um servico systemd costuma ter PATH restrito (ex.: so a `.venv`),
    entao `systemctl` e `sudo` sao procurados tambem nos diretorios padrao do sistema."""

    achado = shutil.which(nome)
    if achado:
        return achado
    for diretorio in _DIRETORIOS_PADRAO:
        candidato = f"{diretorio}/{nome}"  # diretorios POSIX fixos
        if os.path.isfile(candidato) and os.access(candidato, os.X_OK):
            return candidato
    return nome


def executar_comando(argumentos: list[str]) -> ResultadoComando:
    """Executa sem shell e com tempo limite; binario ausente vira codigo 127."""

    argumentos = [_binario(argumentos[0]), *argumentos[1:]]
    try:
        resultado = subprocess.run(  # noqa: S603
            argumentos,
            capture_output=True,
            text=True,
            timeout=_TEMPO_LIMITE_SEGUNDOS,
            check=False,
        )
    except FileNotFoundError:
        return ResultadoComando(127, "", f"comando nao encontrado: {argumentos[0]}")
    except subprocess.TimeoutExpired:
        return ResultadoComando(124, "", "tempo limite excedido")
    return ResultadoComando(resultado.returncode, resultado.stdout or "", resultado.stderr or "")


def _status_linux(saida: str) -> StatusServico:
    valores = dict(linha.split("=", 1) for linha in saida.splitlines() if "=" in linha)
    if valores.get("LoadState") == "not-found":
        return StatusServico.NAO_ENCONTRADO
    ativo = valores.get("ActiveState", "")
    if ativo == "active":
        return StatusServico.EM_EXECUCAO
    if ativo in {"activating", "reloading"}:
        return StatusServico.INICIANDO
    if ativo in {"inactive", "failed", "deactivating"}:
        return StatusServico.PARADO
    return StatusServico.INDISPONIVEL


def _status_windows(resultado: ResultadoComando) -> StatusServico:
    texto = resultado.saida
    if "1060" in texto or "1060" in resultado.erro:
        return StatusServico.NAO_ENCONTRADO
    # O rotulo ("STATE" / "ESTADO") muda com o idioma do Windows; os nomes dos estados, nao.
    achado = re.search(
        r"^\s*\S+\s*:\s*\d+\s+(RUNNING|STOPPED|START_PENDING|STOP_PENDING|"
        r"CONTINUE_PENDING|PAUSE_PENDING|PAUSED)(?!\w)",
        texto,
        re.MULTILINE,
    )
    if achado is None:
        return StatusServico.INDISPONIVEL
    estado = achado.group(1).upper()
    if estado == "RUNNING":
        return StatusServico.EM_EXECUCAO
    if estado in {"START_PENDING", "CONTINUE_PENDING"}:
        return StatusServico.INICIANDO
    if estado in {"STOPPED", "STOP_PENDING", "PAUSED"}:
        return StatusServico.PARADO
    return StatusServico.INDISPONIVEL


def _primeira_linha(texto: str) -> str:
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]
    return linhas[0][:200] if linhas else ""


def consultar_status_detalhado(
    nome_servico: str,
    plataforma: PlataformaHost,
    executor: Executor = executar_comando,
) -> tuple[StatusServico, str]:
    """Estado atual e, quando indisponivel, o motivo. Nunca levanta."""

    if not _PADRAO_NOME.fullmatch(nome_servico.removesuffix(".service")):
        return StatusServico.INDISPONIVEL, "Nome de servico invalido."
    if plataforma is PlataformaHost.LINUX:
        resultado = executor(
            ["systemctl", "show", nome_servico, "-p", "LoadState", "-p", "ActiveState"]
        )
        if resultado.codigo != 0:
            motivo = _primeira_linha(resultado.erro or resultado.saida)
            return StatusServico.INDISPONIVEL, motivo or f"systemctl falhou ({resultado.codigo})."
        status = _status_linux(resultado.saida)
        return status, "" if status is not StatusServico.INDISPONIVEL else "Resposta inesperada."
    resultado = executor(["sc", "query", nome_servico])
    status = _status_windows(resultado)
    if status is StatusServico.INDISPONIVEL:
        return status, _primeira_linha(resultado.erro or resultado.saida) or "sc query falhou."
    return status, ""


def consultar_status(
    nome_servico: str,
    plataforma: PlataformaHost,
    executor: Executor = executar_comando,
) -> StatusServico:
    """Estado atual do servico; nunca levanta (falha vira INDISPONIVEL)."""

    return consultar_status_detalhado(nome_servico, plataforma, executor)[0]


def _aguardar_status(
    nome: str,
    plataforma: PlataformaHost,
    alvo: StatusServico,
    executor: Executor,
    espera: Callable[[float], None],
    tentativas: int = 30,
) -> bool:
    for _ in range(tentativas):
        if consultar_status(nome, plataforma, executor) is alvo:
            return True
        espera(1.0)
    return False


def _traduzir_falha(resultado: ResultadoComando, plataforma: PlataformaHost) -> str:
    texto = f"{resultado.erro} {resultado.saida}".lower()
    if plataforma is PlataformaHost.LINUX and (
        "password is required" in texto or "a terminal is required" in texto
    ):
        return (
            "O usuario do servico nao tem sudo sem senha para systemctl neste servidor. "
            "Autorize-o em /etc/sudoers.d (veja o CHANGELOG do LuftBase)."
        )
    if "access is denied" in texto or "acesso negado" in texto:
        return "O usuario do servico nao tem permissao para controlar servicos do Windows."
    if resultado.codigo == 124:
        return "O comando excedeu o tempo limite."
    detalhe = (resultado.erro or resultado.saida).strip().splitlines()
    return detalhe[0][:200] if detalhe else f"O comando falhou (codigo {resultado.codigo})."


def executar_acao(
    nome_servico: str,
    acao: str,
    plataforma: PlataformaHost,
    executor: Executor = executar_comando,
    espera: Callable[[float], None] = time.sleep,
) -> None:
    """Inicia, para ou reinicia o servico; levanta ErroServicoHost em qualquer falha."""

    if acao not in ACOES:
        raise ErroServicoHost("Acao invalida.")
    if not _PADRAO_NOME.fullmatch(nome_servico.removesuffix(".service")):
        raise ErroServicoHost("Nome de servico invalido.")

    if plataforma is PlataformaHost.LINUX:
        verbo = {"iniciar": "start", "parar": "stop", "reiniciar": "restart"}[acao]
        resultado = executor(["sudo", "-n", "systemctl", verbo, nome_servico])
        if resultado.codigo != 0:
            raise ErroServicoHost(_traduzir_falha(resultado, plataforma))
        return

    if acao in ("parar", "reiniciar"):
        resultado = executor(["sc", "stop", nome_servico])
        # 1062 = servico ja parado: nao e erro ao reiniciar.
        if resultado.codigo not in (0, 1062):
            raise ErroServicoHost(_traduzir_falha(resultado, plataforma))
        if not _aguardar_status(nome_servico, plataforma, StatusServico.PARADO, executor, espera):
            raise ErroServicoHost("O servico nao parou dentro do tempo limite.")
    if acao in ("iniciar", "reiniciar"):
        resultado = executor(["sc", "start", nome_servico])
        # 1056 = servico ja em execucao.
        if resultado.codigo not in (0, 1056):
            raise ErroServicoHost(_traduzir_falha(resultado, plataforma))


__all__ = [
    "ACOES",
    "ErroServicoHost",
    "PlataformaHost",
    "ResultadoComando",
    "StatusServico",
    "consultar_status",
    "consultar_status_detalhado",
    "executar_acao",
    "executar_comando",
    "nome_do_servico",
    "plataforma_do_host",
]
