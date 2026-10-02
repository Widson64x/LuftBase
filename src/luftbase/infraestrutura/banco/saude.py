"""Resultado seguro dos testes de disponibilidade de dependencias."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResultadoSaude:
    """Estado de uma dependencia sem host, usuario ou mensagem sensivel."""

    dependencia: str
    disponivel: bool
    latencia_ms: float
    codigo: str

    def como_dict(self) -> dict[str, str | bool | float]:
        """Produz o payload publico e sanitizado do health check."""

        return {
            "dependencia": self.dependencia,
            "disponivel": self.disponivel,
            "latencia_ms": self.latencia_ms,
            "codigo": self.codigo,
        }
