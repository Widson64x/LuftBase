"""Logs fisicos em arquivo (.log, rotacao diaria): o da plataforma (`luftbase.log`) e o da aplicacao.

O `luftbase.log` e um diario de MENSAGENS do que o LuftBase fez (login, e-mails enviados, permissoes,
publicacoes, falhas...), nao um registro de rotas: as rotas ficam na trilha de acessos HTTP do banco.
Tudo que os modulos do LuftBase registram com `logging` (logger `luftbase.*`) entra aqui, com o usuario
e o id de correlacao da requisicao quando existem. Excecoes aparecem resumidas (tipos e onde nasceram),
nunca com a mensagem bruta, e segredos em texto livre sao mascarados.

O log da aplicacao (`application.log`) e escrito pela propria aplicacao; aqui so e LIDO, em seus dois formatos.
"""

from __future__ import annotations

import contextlib
import copy
import logging
import os
import re
import shutil
import time
from collections.abc import Mapping
from dataclasses import dataclass
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING, Any

from luftbase.nucleo.tempo import FormatadorDeLog, de_timestamp
from luftbase.observabilidade.sanitizacao import mascarar_texto, resumir_excecao

if TYPE_CHECKING:
    from luftbase.observabilidade.modelos import EventoDominio

_PADRAO_LUFTBASE = re.compile(
    r"^\[(?P<data>[^]]+)] \[(?P<nivel>[^]]+)] \[(?P<correlacao>[^]]+)] "
    r"\[(?P<login>[^]]+)] \[(?P<acao>[^]]+)] - (?P<mensagem>.*)$"
)
# Formato do log das aplicacoes: "2026-10-21 15:49:37 | INFO     | Luft-Workspace.App | mensagem".
_PADRAO_APLICACAO = re.compile(
    r"^(?P<data>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)(?:[,.]\d+)? \| (?P<nivel>[A-Za-z]+)\s*\| "
    r"(?P<origem>.*?)\s*\| (?P<mensagem>.*)$"
)
_MAXIMO_LEITURA_BYTES = 2 * 1024 * 1024
_MAXIMO_MENSAGEM = 12_000
NOME_LOG_LUFTBASE = "luftbase.log"
NOME_LOG_APLICACAO = "application.log"

# Marca o handler que captura o logger `luftbase`, para trocar (e nao duplicar) ao recriar a plataforma.
_MARCA_CAPTURA = "_luftbase_captura_fisica"

_ROTULOS_ORIGEM: tuple[tuple[str, str], ...] = (
    ("luftbase.integracoes.email", "EMAIL"),
    ("luftbase.email", "EMAIL"),
    ("luftbase.autorizacao", "ACESSO"),
    ("luftbase.identidade", "IDENTIDADE"),
    ("luftbase.conteudo", "COMUNICADOS"),
    ("luftbase.observabilidade.alertas", "ALERTAS"),
    ("luftbase.observabilidade.avaliador", "ALERTAS"),
    ("luftbase.observabilidade.retencao", "RETENCAO"),
    ("luftbase.infraestrutura", "INFRAESTRUTURA"),
    ("luftbase.servidor", "SERVIDOR"),
    ("luftbase.plataforma", "PLATAFORMA"),
    ("luftbase.web", "WEB"),
    ("luftbase.cli", "CLI"),
)


def rotulo_de_origem(nome_logger: str) -> str:
    """Nome curto da area do LuftBase que escreveu a mensagem (ex.: `EMAIL`, `ACESSO`)."""

    for prefixo, rotulo in _ROTULOS_ORIGEM:
        if nome_logger == prefixo or nome_logger.startswith(prefixo + "."):
            return rotulo
    partes = nome_logger.split(".")
    return partes[1].upper() if len(partes) > 1 and partes[0] == "luftbase" else "LUFTBASE"


@dataclass(frozen=True, slots=True)
class RegistroLogFisico:
    """Entrada normalizada de um arquivo fisico local (uma mensagem, mesmo que ocupe varias linhas)."""

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


def _contexto_da_requisicao() -> tuple[str | None, str | None]:
    """(id de correlacao, login) da requisicao em andamento; (None, None) fora dela."""

    try:
        from flask import g, has_request_context
        from flask_login import current_user

        if not has_request_context():
            return None, None
        correlacao = getattr(g, "luftbase_id_correlacao", None)
        login = getattr(current_user._get_current_object(), "login", None)
        return (str(correlacao) if correlacao else None), (str(login) if login else None)
    except Exception:
        return None, None


class _FiltroContextoAuditoria(logging.Filter):
    """Garante que os atributos de contexto existam, preenchendo-os da requisicao quando da."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "correlacao") or not hasattr(record, "login"):
            correlacao, login = _contexto_da_requisicao()
            if not hasattr(record, "correlacao"):
                record.correlacao = correlacao or "-"
            if not hasattr(record, "login"):
                record.login = login or "SISTEMA"
        if not hasattr(record, "acao_recurso"):
            record.acao_recurso = rotulo_de_origem(record.name)
        return True


class FormatadorLogFisico(FormatadorDeLog):
    """Uma linha por mensagem: segredos mascarados e excecoes resumidas (sem mensagem bruta)."""

    def format(self, record: logging.LogRecord) -> str:
        copia = copy.copy(record)
        texto = mascarar_texto(record.getMessage(), maximo=_MAXIMO_MENSAGEM)
        if record.exc_info and record.exc_info[1] is not None:
            resumo = resumir_excecao(record.exc_info[1])
            tipos = [str(item).rsplit(".", 1)[-1] for item in _lista(resumo.get("cadeia"))]
            onde = "; ".join(str(item) for item in _lista(resumo.get("origem") or resumo.get("pilha"))[-3:])
            texto += f" | erro: {tipos[0] if tipos else 'desconhecido'}"
            if len(tipos) > 1:
                texto += f" (causa: {' > '.join(tipos[1:])})"
            if onde:
                texto += f" | em: {onde}"
        copia.msg = texto
        copia.args = ()
        copia.exc_info = None
        copia.exc_text = None
        copia.stack_info = None
        return super().format(copia)


def _lista(valor: object) -> list[object]:
    return list(valor) if isinstance(valor, list | tuple) else []


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


_NOMES_EVENTOS_TECNICOS = {
    "erro_500": "Erro interno do servidor",
    "falha_auditoria_http": "Nao foi possivel gravar a auditoria da requisicao",
}


def _descrever_tecnico(evento: str, tipo_erro: str | None, dados: object | None) -> str:
    """Frase legivel para um evento tecnico (o que falhou, onde e por que tipo de erro)."""

    texto = _NOMES_EVENTOS_TECNICOS.get(evento, evento.replace("_", " ").capitalize())
    extras: list[str] = []
    if isinstance(dados, Mapping):
        rota = dados.get("rota")
        if rota:
            texto += f" em {dados.get('metodo') or ''} {rota}".replace("  ", " ")
        if tipo_erro:
            texto += f": {tipo_erro}"
        cadeia = _lista(dados.get("cadeia"))
        if len(cadeia) > 1:
            extras.append("causa: " + " > ".join(str(item).rsplit(".", 1)[-1] for item in cadeia[1:]))
        for chave, rotulo in (("origem", "origem"), ("pilha", "em")):
            valores = _lista(dados.get(chave))
            if valores:
                extras.append(f"{rotulo}: " + "; ".join(str(item) for item in valores[-3:]))
                break
        for chave, valor in dados.items():
            if chave not in {"rota", "metodo", "cadeia", "origem", "pilha"} and isinstance(
                valor, str | int | float | bool
            ):
                extras.append(f"{chave}={valor}")
    elif tipo_erro:
        texto += f": {tipo_erro}"
    return texto + (" | " + " | ".join(extras) if extras else "")


def listar_arquivos_log(diretorio: Path, nome_base: str) -> list[dict[str, object]]:
    """Arquivos de um log (o atual e os rotacionados), do mais recente ao mais antigo.

    So devolve arquivos que comecam com `nome_base` dentro de `diretorio`: nenhum caminho livre.
    """

    try:
        arquivos = [c for c in diretorio.glob(f"{nome_base}*") if c.is_file()]
        arquivos.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return [
            {
                "nome": arquivo.name,
                "tamanho_bytes": arquivo.stat().st_size,
                "modificado_em": de_timestamp(arquivo.stat().st_mtime).isoformat(timespec="seconds"),
                "atual": arquivo.name == nome_base,
            }
            for arquivo in arquivos
        ]
    except OSError:
        return []


def ler_log(
    diretorio: Path,
    nome_base: str,
    *,
    arquivo: str | None = None,
    limite: int = 200,
    nivel: str | None = None,
    termo: str | None = None,
) -> list[RegistroLogFisico]:
    """Le o final de um arquivo conhecido (mais novos primeiro), com limites de linhas e bytes."""

    conhecidos = {str(item["nome"]) for item in listar_arquivos_log(diretorio, nome_base)}
    nome = arquivo or nome_base
    if nome not in conhecidos or Path(nome).name != nome:
        return []
    limite = max(min(limite, 500), 1)
    linhas = _ler_final_arquivo(diretorio / nome, limite * 5)
    registros = list(reversed(_agrupar(nome, linhas)))
    if nivel:
        nivel_normalizado = nivel.strip().upper()
        registros = [item for item in registros if item.nivel.upper() == nivel_normalizado]
    if termo:
        termo_normalizado = termo.strip().casefold()
        registros = [
            item
            for item in registros
            if termo_normalizado
            in " ".join(
                filter(None, (item.mensagem, item.login_usuario, item.acao, item.id_correlacao))
            ).casefold()
        ]
    return registros[:limite]


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


def _interpretar_linha(nome_arquivo: str, linha: str) -> RegistroLogFisico | None:
    """Reconhece uma linha de cabecalho em um dos dois formatos; None se for continuacao."""

    correspondencia = _PADRAO_LUFTBASE.match(linha)
    if correspondencia is not None:
        grupos = correspondencia.groupdict()
        return RegistroLogFisico(
            arquivo=nome_arquivo,
            data_hora=grupos["data"],
            nivel=grupos["nivel"],
            id_correlacao=None if grupos["correlacao"] == "-" else grupos["correlacao"],
            login_usuario=None if grupos["login"] == "-" else grupos["login"],
            acao=None if grupos["acao"] == "-" else grupos["acao"],
            mensagem=grupos["mensagem"][:_MAXIMO_MENSAGEM],
        )
    correspondencia = _PADRAO_APLICACAO.match(linha)
    if correspondencia is not None:
        grupos = correspondencia.groupdict()
        return RegistroLogFisico(
            arquivo=nome_arquivo,
            data_hora=grupos["data"],
            nivel=grupos["nivel"].upper(),
            id_correlacao=None,
            login_usuario=None,
            acao=grupos["origem"] or None,
            mensagem=grupos["mensagem"][:_MAXIMO_MENSAGEM],
        )
    return None


def _agrupar(nome_arquivo: str, linhas: list[str]) -> list[RegistroLogFisico]:
    """Junta as linhas de continuacao (pilhas de erro) na mensagem anterior, em ordem cronologica."""

    registros: list[RegistroLogFisico] = []
    for linha in linhas:
        if not linha.strip():
            continue
        novo = _interpretar_linha(nome_arquivo, linha)
        if novo is not None:
            registros.append(novo)
        elif registros:
            anterior = registros[-1]
            registros[-1] = RegistroLogFisico(
                arquivo=anterior.arquivo,
                data_hora=anterior.data_hora,
                nivel=anterior.nivel,
                id_correlacao=anterior.id_correlacao,
                login_usuario=anterior.login_usuario,
                acao=anterior.acao,
                mensagem=f"{anterior.mensagem}\n{linha}"[:_MAXIMO_MENSAGEM],
            )
        else:
            registros.append(
                RegistroLogFisico(nome_arquivo, None, "RAW", None, None, None, linha[:_MAXIMO_MENSAGEM])
            )
    return registros


class LoggerFisicoAuditoria:
    """Gerencia a escrita em disco do log rotativo da plataforma."""

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
        self._handler: logging.Handler | None = None

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
            handler.setFormatter(FormatadorLogFisico(formato, datefmt="%Y-%m-%d %H:%M:%S"))
            handler.addFilter(_FiltroContextoAuditoria())

            # Substitui handlers existentes da mesma instancia
            self._logger.handlers.clear()
            self._logger.addHandler(handler)
            self._handler = handler
        except Exception as erro:
            logging.getLogger("luftbase").error(
                "Nao foi possivel configurar log fisico em %s: %s",
                self._caminho_arquivo,
                erro,
            )

    def capturar_plataforma(self, nome_logger: str = "luftbase", nivel: int = logging.INFO) -> None:
        """Faz tudo que os modulos do LuftBase registram com `logging` cair neste arquivo.

        Repetir a chamada (ex.: ao recriar a plataforma no mesmo processo) troca o handler anterior em
        vez de duplicar as linhas.
        """

        if self._handler is None:
            return
        alvo = logging.getLogger(nome_logger)
        for existente in list(alvo.handlers):
            if getattr(existente, _MARCA_CAPTURA, False):
                alvo.removeHandler(existente)
        setattr(self._handler, _MARCA_CAPTURA, True)
        alvo.addHandler(self._handler)
        if alvo.level == logging.NOTSET or alvo.level > nivel:
            alvo.setLevel(nivel)

    def registrar_evento(self, evento: EventoDominio) -> None:
        """Registra um evento de dominio como uma frase (a descricao que o servico informou)."""

        try:
            extra: dict[str, Any] = {
                "correlacao": evento.id_correlacao or "-",
                "login": evento.login_usuario or "SISTEMA",
                "acao_recurso": f"{evento.acao}/{evento.recurso}",
            }
            mensagem = evento.descricao
            if evento.id_recurso and str(evento.id_recurso) not in mensagem:
                mensagem += f" (id {evento.id_recurso})"
            if evento.traceback:
                # So o tipo da excecao (ultima linha da pilha, antes dos dois pontos): a mensagem pode ter dados.
                ultima = [linha for linha in evento.traceback.splitlines() if linha.strip()][-1]
                mensagem += f" | erro: {ultima.split(':', 1)[0].rsplit('.', 1)[-1]}"
            if evento.severidade.value.upper() in {"ALTA", "CRITICA"}:
                self._logger.error(mensagem, extra=extra)
            else:
                self._logger.info(mensagem, extra=extra)
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

        self._escrever(logging.INFO, mensagem, correlacao, login, acao or "INFO", recurso)

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

        self._escrever(logging.WARNING, mensagem, correlacao, login, acao or "AVISO", recurso)

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
        """Registra mensagem de erro (da excecao, somente o tipo: a mensagem bruta pode ter dados)."""

        texto = f"{mensagem} | erro: {type(erro).__name__}" if erro else mensagem
        self._escrever(logging.ERROR, texto, correlacao, login, acao or "ERRO", recurso)

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

        self._escrever(logging.DEBUG, mensagem, correlacao, login, acao or "DEBUG", recurso)

    def registrar_tecnico(
        self,
        nivel: str,
        evento: str,
        *,
        id_correlacao: str | None = None,
        dados: object | None = None,
        tipo_erro: str | None = None,
    ) -> None:
        """Registra diagnostico tecnico como frase legivel, sempre sem valores sensiveis."""

        extra: dict[str, Any] = {
            "correlacao": id_correlacao or "-",
            "login": "SISTEMA",
            "acao_recurso": "TECNICO/SISTEMA",
        }
        try:
            metodo = getattr(self._logger, nivel.lower(), self._logger.info)
            metodo(_descrever_tecnico(evento, tipo_erro, dados), extra=extra)
        except Exception:
            pass

    def _escrever(
        self,
        nivel: int,
        mensagem: str,
        correlacao: str | None,
        login: str | None,
        acao: str,
        recurso: str | None,
    ) -> None:
        try:
            extra: dict[str, Any] = {
                "correlacao": correlacao or "-",
                "login": login or "SISTEMA",
                "acao_recurso": f"{acao}/{recurso or 'SISTEMA'}",
            }
            self._logger.log(nivel, mensagem, extra=extra)
        except Exception:
            pass

    def listar_arquivos(self) -> list[dict[str, object]]:
        """Lista somente arquivos pertencentes a este logger, sem aceitar caminhos livres."""

        return listar_arquivos_log(self._diretorio, self._caminho_arquivo.name)

    def ler_recentes(
        self,
        *,
        arquivo: str | None = None,
        limite: int = 200,
        nivel: str | None = None,
        termo: str | None = None,
    ) -> list[RegistroLogFisico]:
        """Le o final de um arquivo conhecido com limites de linhas e bytes."""

        return ler_log(
            self._diretorio,
            self._caminho_arquivo.name,
            arquivo=arquivo,
            limite=limite,
            nivel=nivel,
            termo=termo,
        )

    @property
    def diretorio(self) -> Path:
        """Pasta onde ficam os logs fisicos."""

        return self._diretorio

    @property
    def caminho_arquivo(self) -> Path:
        """Devolve o caminho do arquivo de log em disco."""

        return self._caminho_arquivo
