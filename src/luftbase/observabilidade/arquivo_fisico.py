"""Gravacao estruturada de logs fisicos em arquivo .log com rotacao diaria."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

from luftbase.nucleo.tempo import FormatadorDeLog, de_timestamp
from luftbase.observabilidade.sanitizacao import serializar_dados_seguro

if TYPE_CHECKING:
    from luftbase.observabilidade.modelos import EventoAcessoHttp, EventoDominio

_PADRAO_LINHA = re.compile(
    r"^\[(?P<data>[^]]+)] \[(?P<nivel>[^]]+)] \[(?P<correlacao>[^]]+)] "
    r"\[(?P<login>[^]]+)] \[(?P<acao>[^]]+)] - (?P<mensagem>.*)$"
)
_MAXIMO_LEITURA_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RegistroLogFisico:
    """Linha normalizada de um arquivo fisico local."""

    arquivo: str
    data_hora: str | None
    nivel: str
    id_correlacao: str | None
    login_usuario: str | None
    acao: str | None
    mensagem: str

    def como_dict(self) -> dict[str, str | None]:
        return {
            "arquivo": self.arquivo,
            "data_hora": self.data_hora,
            "nivel": self.nivel,
            "id_correlacao": self.id_correlacao,
            "login_usuario": self.login_usuario,
            "acao": self.acao,
            "mensagem": self.mensagem,
        }


class _FiltroContextoAuditoria(logging.Filter):
    """Garante que atributos de contexto sempre existam para o formatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlacao"):
            record.correlacao = "-"
        if not hasattr(record, "login"):
            record.login = "SISTEMA"
        if not hasattr(record, "acao_recurso"):
            record.acao_recurso = "GERAL"
        return True


class HandlerRotativoResiliente(TimedRotatingFileHandler):
    """TimedRotatingFileHandler resiliente ao Windows e a processos concorrentes.

    No Windows, `os.rename()` falha com `PermissionError: [WinError 32]` quando outro
    processo (ex.: o supervisor do reloader do Werkzeug/Flask ou outro worker) mantém
    um handle aberto no arquivo de log.

    Esta classe resolve esse problema:
    1. Executa tentativas com intervalo curto para casos transientes de lock.
    2. Utiliza fallback com estrategia 'copytruncate' caso a renomeacao seja bloqueada.
    3. Garante que `rolloverAt` seja SEMPRE atualizado para o proximo periodo futuro,
       evitando que falhas pontuais causem loop de excecoes a cada requisicao.
    4. Abre o arquivo com `delay=True` para nao manter handles abertos em processos
       que apenas instanciam o app sem gravar logs (como o supervisor do reloader).
    """

    def doRollover(self) -> None:
        if self.stream:
            with contextlib.suppress(Exception):
                self.stream.close()
            self.stream = None

        current_time = int(time.time())
        dst_now = time.localtime(current_time)[-1]
        t = max(self.rolloverAt - self.interval, 0)
        try:
            if self.utc:
                time_tuple = time.gmtime(t)
            else:
                time_tuple = time.localtime(t)
                dst_then = time_tuple[-1]
                if dst_now != dst_then:
                    addend = 3600 if dst_now else -3600
                    time_tuple = time.localtime(max(t + addend, 0))
        except (OSError, OverflowError, ValueError):
            time_tuple = time.localtime(current_time)
        dfn = self.rotation_filename(
            self.baseFilename + "." + time.strftime(self.suffix, time_tuple)
        )

        rotacionou = False
        # 1. Tentativa de renomeacao padrao com retries
        for tentativa in range(3):
            try:
                if os.path.exists(dfn):
                    os.remove(dfn)
                self.rotate(self.baseFilename, dfn)
                rotacionou = True
                break
            except (PermissionError, OSError):
                if tentativa < 2:
                    time.sleep(0.05)

        # 2. Fallback com copytruncate se renomeacao falhar (bloqueio por outro processo no Windows)
        if not rotacionou and os.path.exists(self.baseFilename):
            try:
                shutil.copy2(self.baseFilename, dfn)
                with open(self.baseFilename, "w", encoding=self.encoding):
                    pass
                rotacionou = True
            except (PermissionError, OSError):
                # Se mesmo o truncate falhar, continuamos operando em append
                pass

        # 3. Limpeza de backups antigos
        if self.backupCount > 0 and rotacionou:
            for s in self.getFilesToDelete():
                with contextlib.suppress(OSError):
                    os.remove(s)

        # 4. Reabrir stream se delay nao estiver ativo
        if not self.delay:
            with contextlib.suppress(Exception):
                self.stream = self._open()

        # 5. GARANTIA CRUCIAL: Sempre avancar rolloverAt para o proximo ciclo futuro
        new_rollover_at = self.computeRollover(current_time)
        while new_rollover_at <= current_time:
            new_rollover_at += self.interval
        self.rolloverAt = new_rollover_at


class LoggerFisicoAuditoria:
    """Gerencia escrita em disco no arquivo .log rotativo."""

    def __init__(
        self,
        diretorio_logs: str | Path = "Logs",
        nome_arquivo: str = "app.log",
        nivel: int = logging.INFO,
    ) -> None:
        self._diretorio = Path(diretorio_logs)
        self._caminho_arquivo = self._diretorio / nome_arquivo
        self._logger = logging.getLogger(f"luftbase.fisico.{nome_arquivo}")
        self._logger.setLevel(nivel)
        self._logger.propagate = False

        self._configurar_handler()

    def _configurar_handler(self) -> None:
        try:
            self._diretorio.mkdir(parents=True, exist_ok=True)
            handler = HandlerRotativoResiliente(
                str(self._caminho_arquivo),
                when="midnight",
                interval=1,
                backupCount=30,
                encoding="utf-8",
                delay=True,
            )
            formato = (
                "[%(asctime)s] [%(levelname)s] [%(correlacao)s] [%(login)s] "
                "[%(acao_recurso)s] - %(message)s"
            )
            formatter = FormatadorDeLog(formato, datefmt="%Y-%m-%d %H:%M:%S")
            handler.setFormatter(formatter)
            handler.addFilter(_FiltroContextoAuditoria())

            # Substitui handlers existentes da mesma instancia
            self._logger.handlers.clear()
            self._logger.addHandler(handler)
        except Exception as erro:
            logging.getLogger("luftbase").error(
                "Nao foi possivel configurar log fisico em %s: %s",
                self._caminho_arquivo,
                erro,
            )

    def registrar_acesso(self, evento: EventoAcessoHttp) -> None:
        """Registra acesso HTTP no arquivo de log fisico."""

        try:
            extra: dict[str, Any] = {
                "correlacao": evento.id_correlacao or "-",
                "login": evento.login_usuario or "ANONIMO",
                "acao_recurso": f"HTTP_{evento.metodo}",
            }
            msg = (
                f"{evento.rota} - Status: {evento.status_http} ({evento.duracao_ms}ms) "
                f"IP: {evento.ip_origem or '-'}"
            )
            self._logger.info(msg, extra=extra)
        except Exception:
            pass

    def registrar_evento(self, evento: EventoDominio) -> None:
        """Registra evento de dominio no arquivo de log fisico."""

        try:
            extra: dict[str, Any] = {
                "correlacao": evento.id_correlacao or "-",
                "login": evento.login_usuario or "SISTEMA",
                "acao_recurso": f"{evento.acao}/{evento.recurso}",
            }
            contexto = serializar_dados_seguro(
                {
                    "descricao": evento.descricao,
                    "recurso_id": evento.id_recurso,
                    "severidade": evento.severidade.value,
                    "dados_anteriores": evento.dados_anteriores,
                    "dados_novos": evento.dados_novos,
                    "tipo_erro": "registrado" if evento.traceback else None,
                }
            )
            msg = contexto
            severidade = evento.severidade.value.upper()
            if severidade in {"ALTA", "CRITICA"}:
                self._logger.error(msg, extra=extra)
            else:
                self._logger.info(msg, extra=extra)
        except Exception:
            pass

    def info(
        self,
        mensagem: str,
        *,
        correlacao: str | None = None,
        login: str | None = None,
        acao: str | None = None,
        recurso: str | None = None,
    ) -> None:
        """Registra mensagem informativa."""

        try:
            extra: dict[str, Any] = {
                "correlacao": correlacao or "-",
                "login": login or "SISTEMA",
                "acao_recurso": f"{acao or 'INFO'}/{recurso or 'SISTEMA'}",
            }
            self._logger.info(mensagem, extra=extra)
        except Exception:
            pass

    def aviso(
        self,
        mensagem: str,
        *,
        correlacao: str | None = None,
        login: str | None = None,
        acao: str | None = None,
        recurso: str | None = None,
    ) -> None:
        """Registra mensagem de aviso."""

        try:
            extra: dict[str, Any] = {
                "correlacao": correlacao or "-",
                "login": login or "SISTEMA",
                "acao_recurso": f"{acao or 'AVISO'}/{recurso or 'SISTEMA'}",
            }
            self._logger.warning(mensagem, extra=extra)
        except Exception:
            pass

    def erro(
        self,
        mensagem: str,
        erro: BaseException | None = None,
        *,
        correlacao: str | None = None,
        login: str | None = None,
        acao: str | None = None,
        recurso: str | None = None,
    ) -> None:
        """Registra mensagem de erro."""

        try:
            extra: dict[str, Any] = {
                "correlacao": correlacao or "-",
                "login": login or "SISTEMA",
                "acao_recurso": f"{acao or 'ERRO'}/{recurso or 'SISTEMA'}",
            }
            msg = f"{mensagem} | Erro: {type(erro).__name__}: {erro}" if erro else mensagem
            self._logger.error(msg, extra=extra)
        except Exception:
            pass

    def debug(
        self,
        mensagem: str,
        *,
        correlacao: str | None = None,
        login: str | None = None,
        acao: str | None = None,
        recurso: str | None = None,
    ) -> None:
        """Registra mensagem de debug."""

        try:
            extra: dict[str, Any] = {
                "correlacao": correlacao or "-",
                "login": login or "SISTEMA",
                "acao_recurso": f"{acao or 'DEBUG'}/{recurso or 'SISTEMA'}",
            }
            self._logger.debug(mensagem, extra=extra)
        except Exception:
            pass

    def registrar_tecnico(
        self,
        nivel: str,
        evento: str,
        *,
        id_correlacao: str | None = None,
        dados: object | None = None,
        tipo_erro: str | None = None,
    ) -> None:
        """Registra diagnostico tecnico amplo, mas sempre sanitizado."""

        extra: dict[str, Any] = {
            "correlacao": id_correlacao or "-",
            "login": "SISTEMA",
            "acao_recurso": "TECNICO/SISTEMA",
        }
        mensagem = serializar_dados_seguro(
            {"evento": evento, "tipo_erro": tipo_erro, "dados": dados}
        )
        try:
            metodo = getattr(self._logger, nivel.lower(), self._logger.info)
            metodo(mensagem, extra=extra)
        except Exception:
            pass

    def listar_arquivos(self) -> list[dict[str, object]]:
        """Lista somente arquivos pertencentes a este logger, sem aceitar caminhos livres."""

        try:
            arquivos = [
                caminho
                for caminho in self._diretorio.glob(f"{self._caminho_arquivo.name}*")
                if caminho.is_file()
            ]
            arquivos.sort(key=lambda item: item.stat().st_mtime, reverse=True)
            return [
                {
                    "nome": arquivo.name,
                    "tamanho_bytes": arquivo.stat().st_size,
                    "modificado_em": de_timestamp(arquivo.stat().st_mtime).isoformat(
                        timespec="seconds"
                    ),
                    "atual": arquivo == self._caminho_arquivo,
                }
                for arquivo in arquivos
            ]
        except OSError:
            return []

    def ler_recentes(
        self,
        *,
        arquivo: str | None = None,
        limite: int = 200,
        nivel: str | None = None,
        termo: str | None = None,
    ) -> list[RegistroLogFisico]:
        """Le o final de um arquivo conhecido com limites de linhas e bytes."""

        arquivos = {item["nome"] for item in self.listar_arquivos()}
        nome = arquivo or self._caminho_arquivo.name
        if nome not in arquivos or Path(nome).name != nome:
            return []
        caminho = self._diretorio / nome
        linhas = _ler_final_arquivo(caminho, max(min(limite, 500), 1) * 5)
        registros = [_interpretar_linha(nome, linha) for linha in reversed(linhas)]
        if nivel:
            nivel_normalizado = nivel.strip().upper()
            registros = [item for item in registros if item.nivel == nivel_normalizado]
        if termo:
            termo_normalizado = termo.strip().casefold()
            registros = [
                item
                for item in registros
                if termo_normalizado
                in " ".join(
                    filter(
                        None,
                        (
                            item.mensagem,
                            item.login_usuario,
                            item.acao,
                            item.id_correlacao,
                        ),
                    )
                ).casefold()
            ]
        return registros[: max(min(limite, 500), 1)]

    @property
    def caminho_arquivo(self) -> Path:
        """Devolve o caminho do arquivo de log em disco."""

        return self._caminho_arquivo


def _ler_final_arquivo(caminho: Path, maximo_linhas: int) -> list[str]:
    try:
        with caminho.open("rb") as arquivo:
            arquivo.seek(0, os.SEEK_END)
            tamanho = arquivo.tell()
            inicio = max(tamanho - _MAXIMO_LEITURA_BYTES, 0)
            arquivo.seek(inicio)
            conteudo = arquivo.read(_MAXIMO_LEITURA_BYTES)
        if inicio:
            primeira_quebra = conteudo.find(b"\n")
            conteudo = conteudo[primeira_quebra + 1 :] if primeira_quebra >= 0 else b""
        return conteudo.decode("utf-8", errors="replace").splitlines()[-maximo_linhas:]
    except OSError:
        return []


def _interpretar_linha(nome_arquivo: str, linha: str) -> RegistroLogFisico:
    correspondencia = _PADRAO_LINHA.match(linha)
    if correspondencia is None:
        return RegistroLogFisico(
            arquivo=nome_arquivo,
            data_hora=None,
            nivel="RAW",
            id_correlacao=None,
            login_usuario=None,
            acao=None,
            mensagem=linha[:12_000],
        )
    grupos = correspondencia.groupdict()
    return RegistroLogFisico(
        arquivo=nome_arquivo,
        data_hora=grupos["data"],
        nivel=grupos["nivel"],
        id_correlacao=None if grupos["correlacao"] == "-" else grupos["correlacao"],
        login_usuario=None if grupos["login"] == "-" else grupos["login"],
        acao=None if grupos["acao"] == "-" else grupos["acao"],
        mensagem=grupos["mensagem"][:12_000],
    )
