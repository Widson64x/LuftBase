"""Metricas locais de baixa cardinalidade pertencentes a uma aplicacao."""

from __future__ import annotations

from collections import Counter
from threading import Lock
from time import monotonic


class RegistroMetricas:
    """Agrega contadores sem rotas, usuarios ou outros rotulos sensiveis."""

    def __init__(self) -> None:
        self._inicio = monotonic()
        self._requisicoes: Counter[str] = Counter()
        self._duracao_total_ms = 0
        self._falhas_auditoria = 0
        self._lock = Lock()

    def registrar_requisicao(self, metodo: str, status_http: int, duracao_ms: int) -> None:
        """Agrupa por metodo conhecido e classe do status para limitar cardinalidade."""

        metodo_normalizado = (
            metodo if metodo in {"GET", "POST", "PUT", "PATCH", "DELETE"} else "OUTRO"
        )
        classe = f"{max(min(status_http // 100, 5), 1)}xx"
        with self._lock:
            self._requisicoes[f"{metodo_normalizado}:{classe}"] += 1
            self._duracao_total_ms += max(duracao_ms, 0)

    def registrar_falha_auditoria(self) -> None:
        """Conta falhas sem incorporar a mensagem da excecao."""

        with self._lock:
            self._falhas_auditoria += 1

    def snapshot(self) -> dict[str, object]:
        """Produz uma copia consistente e sanitizada dos acumuladores."""

        with self._lock:
            requisicoes = dict(sorted(self._requisicoes.items()))
            total = sum(self._requisicoes.values())
            duracao_total = self._duracao_total_ms
            falhas = self._falhas_auditoria
        return {
            "uptime_segundos": round(monotonic() - self._inicio, 3),
            "requisicoes_total": total,
            "requisicoes": requisicoes,
            "duracao_total_ms": duracao_total,
            "falhas_auditoria_total": falhas,
        }
