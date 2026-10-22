"""Cache de vida curta (segundos) para consultas analiticas repetidas, sem dependencias externas.

A tela de Auditoria pode ser atualizada sozinha e aberta por varias pessoas ao mesmo tempo: sem isto, cada
atualizacao refaz os mesmos agregados sobre a trilha de acessos. Os resultados ficam por poucos segundos
(o painel e "quase em tempo real", nao em tempo real) e o botao Atualizar sempre ignora o cache.

O cache e por aplicacao Flask (ver `web.auditoria._cache`), nunca global: nada vaza entre instancias.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class CacheCurto:
    """Guarda ate `maximo` resultados por `ttl_segundos`; os mais antigos saem primeiro."""

    def __init__(self, ttl_segundos: float = 15.0, maximo: int = 64) -> None:
        self._ttl = float(ttl_segundos)
        self._maximo = max(int(maximo), 1)
        self._itens: OrderedDict[Hashable, tuple[float, Any]] = OrderedDict()
        self._trava = threading.Lock()
        self.acertos = 0
        self.falhas = 0

    def obter(self, chave: Hashable, calcular: Callable[[], Any], *, forcar: bool = False) -> Any:
        """Devolve o valor guardado (se ainda valido) ou calcula, guarda e devolve.

        `forcar=True` recalcula e substitui o que estava guardado. O calculo roda fora da trava: duas
        requisicoes simultaneas podem calcular o mesmo valor, o que e inofensivo (so leitura).
        """

        agora = time.monotonic()
        if not forcar:
            with self._trava:
                existente = self._itens.get(chave)
                if existente is not None and existente[0] > agora:
                    self._itens.move_to_end(chave)
                    self.acertos += 1
                    return existente[1]
        valor = calcular()
        with self._trava:
            self.falhas += 1
            self._itens[chave] = (time.monotonic() + self._ttl, valor)
            self._itens.move_to_end(chave)
            while len(self._itens) > self._maximo:
                self._itens.popitem(last=False)
        return valor

    def limpar(self) -> None:
        with self._trava:
            self._itens.clear()

    def __len__(self) -> int:
        with self._trava:
            return len(self._itens)
