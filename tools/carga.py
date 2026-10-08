"""Roteiro de carga simples (so biblioteca padrao): N usuarios simultaneos batendo em URLs.

Uso:
    python tools/carga.py --base https://homologacao/luft --usuarios 100 --duracao 60 \
        --rota /_luftbase/saude --rota /auditoria/api/visao-geral --cookie "luft_session=..."

Mede por rota: requisicoes, erros (status >= 500 ou falha de rede), p50, p95 e p99 em ms. O codigo de
saida e 1 quando o p95 passa de `--p95-max` ou a taxa de erro passa de `--erro-max` (uso em pipeline).
Rode **so em homologacao**, nunca em producao, e use um cookie de sessao de teste.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class Resultado:
    tempos_ms: list[float] = field(default_factory=list)
    erros: int = 0
    status: dict[int, int] = field(default_factory=lambda: defaultdict(int))


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(len(ordenados) - 1, max(0, round(p / 100 * (len(ordenados) - 1))))
    return ordenados[indice]


def _trabalhar(
    base: str,
    rotas: list[str],
    cabecalhos: dict[str, str],
    fim: float,
    resultados: dict[str, Resultado],
    trava: threading.Lock,
    pausa: float,
) -> None:
    i = 0
    while time.monotonic() < fim:
        rota = rotas[i % len(rotas)]
        i += 1
        pedido = urllib.request.Request(base.rstrip("/") + rota, headers=cabecalhos)
        inicio = time.perf_counter()
        status = 0
        try:
            with urllib.request.urlopen(pedido, timeout=30) as resposta:  # noqa: S310
                resposta.read()
                status = resposta.status
        except urllib.error.HTTPError as erro:
            status = erro.code
        except (urllib.error.URLError, TimeoutError, OSError):
            status = 0
        decorrido = (time.perf_counter() - inicio) * 1000
        with trava:
            alvo = resultados[rota]
            alvo.tempos_ms.append(decorrido)
            alvo.status[status] += 1
            if status == 0 or status >= 500:
                alvo.erros += 1
        if pausa:
            time.sleep(pausa)


def executar(
    base: str,
    rotas: list[str],
    usuarios: int,
    duracao: float,
    cookie: str | None = None,
    pausa: float = 0.0,
) -> dict[str, Resultado]:
    cabecalhos = {"User-Agent": "luftbase-carga/1", "Accept": "*/*"}
    if cookie:
        cabecalhos["Cookie"] = cookie
    resultados: dict[str, Resultado] = {rota: Resultado() for rota in rotas}
    trava = threading.Lock()
    fim = time.monotonic() + duracao
    fios = [
        threading.Thread(
            target=_trabalhar,
            args=(base, rotas, cabecalhos, fim, resultados, trava, pausa),
            daemon=True,
        )
        for _ in range(usuarios)
    ]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join()
    return resultados


def relatorio(resultados: dict[str, Resultado]) -> tuple[str, float, float]:
    linhas = [f"{'rota':45} {'req':>7} {'erros':>6} {'p50':>8} {'p95':>8} {'p99':>8}"]
    todos: list[float] = []
    total = erros = 0
    for rota, r in resultados.items():
        todos.extend(r.tempos_ms)
        total += len(r.tempos_ms)
        erros += r.erros
        linhas.append(
            f"{rota[:45]:45} {len(r.tempos_ms):>7} {r.erros:>6} "
            f"{statistics.median(r.tempos_ms) if r.tempos_ms else 0:>8.1f} "
            f"{percentil(r.tempos_ms, 95):>8.1f} {percentil(r.tempos_ms, 99):>8.1f}"
        )
    p95_geral = percentil(todos, 95)
    taxa = erros / total if total else 1.0
    linhas.append(f"TOTAL: {total} requisicoes, p95 {p95_geral:.1f} ms, erros {taxa:.2%}")
    return "\n".join(linhas), p95_geral, taxa


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="URL base, ex.: https://host/luft")
    parser.add_argument("--rota", action="append", required=True, help="rota GET (repetivel)")
    parser.add_argument("--usuarios", type=int, default=100)
    parser.add_argument("--duracao", type=float, default=60.0, help="segundos")
    parser.add_argument("--pausa", type=float, default=0.0, help="segundos entre requisicoes")
    parser.add_argument("--cookie", default=None)
    parser.add_argument("--p95-max", type=float, default=3000.0, help="ms")
    parser.add_argument("--erro-max", type=float, default=0.01, help="fracao (0.01 = 1%%)")
    args = parser.parse_args(argv)

    resultados = executar(
        args.base, args.rota, args.usuarios, args.duracao, args.cookie, args.pausa
    )
    texto, p95, taxa = relatorio(resultados)
    print(texto)
    if p95 > args.p95_max or taxa > args.erro_max:
        print(f"REPROVADO: limites p95 <= {args.p95_max} ms e erros <= {args.erro_max:.2%}")
        return 1
    print("APROVADO")
    return 0


if __name__ == "__main__":
    sys.exit(main())
