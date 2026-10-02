"""Raiz temporaria dos logs do processo em memoria e arquivo local.

Armazena os ultimos eventos enquanto o servico estiver em execucao.
Quando o servico for desligado ou reiniciado, estes dados somem da RAM.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from luftbase.observabilidade.sanitizacao import serializar_dados_seguro


@dataclass(frozen=True, slots=True)
class RegistroLogTemp:
    """Entrada individual de log volátil em memoria."""

    data_hora: datetime
    nivel: str
    id_correlacao: str | None
    codigo_usuario: int | None
    login_usuario: str | None
    codigo_grupo: int | None
    nome_grupo: str | None
    acao: str | None
    recurso: str | None
    mensagem: str
    detalhes: dict[str, Any] | None = None

    def como_dict(self) -> dict[str, Any]:
        dados = asdict(self)
        dados["data_hora"] = self.data_hora.isoformat()
        return dados


class BufferLogsTemporarios:
    """Buffer circular thread-safe baseado em deque com capacidade fixa."""

    def __init__(
        self,
        capacidade_maxima: int = 1000,
        *,
        diretorio_arquivos: str | Path | None = None,
    ) -> None:
        self._capacidade = max(capacidade_maxima, 50)
        self._deque: deque[RegistroLogTemp] = deque(maxlen=self._capacidade)
        self._trava = threading.Lock()
        self._caminho_arquivo = (
            Path(diretorio_arquivos) / f"luftbase-{os.getpid()}.temp.log"
            if diretorio_arquivos is not None
            else None
        )
        self._preparar_arquivo()

    def adicionar(
        self,
        nivel: str,
        mensagem: str,
        *,
        id_correlacao: str | None = None,
        codigo_usuario: int | None = None,
        login_usuario: str | None = None,
        codigo_grupo: int | None = None,
        nome_grupo: str | None = None,
        acao: str | None = None,
        recurso: str | None = None,
        detalhes: dict[str, Any] | None = None,
        data_hora: datetime | None = None,
    ) -> RegistroLogTemp:
        """Insere uma nova entrada no buffer circular."""

        registro = RegistroLogTemp(
            data_hora=data_hora or datetime.now(),
            nivel=nivel.upper(),
            id_correlacao=id_correlacao,
            codigo_usuario=codigo_usuario,
            login_usuario=login_usuario,
            codigo_grupo=codigo_grupo,
            nome_grupo=nome_grupo,
            acao=acao,
            recurso=recurso,
            mensagem=mensagem,
            detalhes=detalhes,
        )
        with self._trava:
            self._deque.append(registro)
            self._gravar_arquivo(registro)
        return registro

    def listar(
        self,
        *,
        limite: int = 100,
        nivel: str | None = None,
        termo: str | None = None,
        codigo_usuario: int | None = None,
        codigo_grupo: int | None = None,
    ) -> list[RegistroLogTemp]:
        """Consulta as entradas mais recentes filtradas."""

        with self._trava:
            itens = list(reversed(self._deque))

        if nivel:
            nivel_busca = nivel.strip().upper()
            itens = [item for item in itens if item.nivel == nivel_busca]

        if codigo_usuario is not None:
            itens = [item for item in itens if item.codigo_usuario == codigo_usuario]
        if codigo_grupo is not None:
            itens = [item for item in itens if item.codigo_grupo == codigo_grupo]

        if termo:
            termo_busca = termo.strip().lower()
            itens = [
                item
                for item in itens
                if termo_busca in item.mensagem.lower()
                or (item.login_usuario and termo_busca in item.login_usuario.lower())
                or (item.nome_grupo and termo_busca in item.nome_grupo.lower())
                or (item.acao and termo_busca in item.acao.lower())
                or (item.recurso and termo_busca in item.recurso.lower())
                or (item.id_correlacao and termo_busca in item.id_correlacao.lower())
            ]

        return itens[: max(limite, 1)]

    def limpar(self) -> None:
        """Limpa o buffer em memoria."""

        with self._trava:
            self._deque.clear()

    def contagem(self) -> int:
        """Total de logs em memoria."""

        with self._trava:
            return len(self._deque)

    @property
    def caminho_arquivo(self) -> Path | None:
        """Arquivo raiz do processo, quando a persistencia temporaria foi configurada."""

        return self._caminho_arquivo

    def _preparar_arquivo(self) -> None:
        if self._caminho_arquivo is None:
            return
        try:
            self._caminho_arquivo.parent.mkdir(parents=True, exist_ok=True)
            limite = time.time() - (2 * 24 * 60 * 60)
            for arquivo in self._caminho_arquivo.parent.glob("luftbase-*.temp.log"):
                if arquivo != self._caminho_arquivo and arquivo.stat().st_mtime < limite:
                    arquivo.unlink(missing_ok=True)
        except OSError:
            self._caminho_arquivo = None

    def _gravar_arquivo(self, registro: RegistroLogTemp) -> None:
        if self._caminho_arquivo is None:
            return
        try:
            linha = serializar_dados_seguro(registro.como_dict())
            with self._caminho_arquivo.open("a", encoding="utf-8") as arquivo:
                arquivo.write(linha + "\n")
        except OSError:
            # Falha local de diagnostico nunca interrompe a operacao de negocio.
            return
