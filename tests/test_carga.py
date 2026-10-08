"""A ferramenta de carga (`tools/carga.py`) mede e reprova como esperado."""

from __future__ import annotations

import importlib.util
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_CAMINHO = Path(__file__).resolve().parents[1] / "tools" / "carga.py"
_spec = importlib.util.spec_from_file_location("luft_carga", _CAMINHO)
assert _spec and _spec.loader
carga = importlib.util.module_from_spec(_spec)
sys.modules["luft_carga"] = carga  # o @dataclass precisa achar o modulo
_spec.loader.exec_module(carga)


class _Servidor(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        codigo = 500 if self.path == "/quebra" else 200
        self.send_response(codigo)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def base():  # type: ignore[no-untyped-def]
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _Servidor)
    fio = threading.Thread(target=servidor.serve_forever, daemon=True)
    fio.start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()
    servidor.server_close()


def test_percentil() -> None:
    assert carga.percentil([], 95) == 0.0
    assert carga.percentil(list(map(float, range(1, 101))), 95) == pytest.approx(95, abs=1)


def test_aprova_servidor_saudavel(base: str, capsys: pytest.CaptureFixture[str]) -> None:
    codigo = carga.main(["--base", base, "--rota", "/ok", "--usuarios", "5", "--duracao", "1"])

    assert codigo == 0
    assert "APROVADO" in capsys.readouterr().out


def test_reprova_quando_ha_erro_5xx(base: str, capsys: pytest.CaptureFixture[str]) -> None:
    codigo = carga.main(
        ["--base", base, "--rota", "/quebra", "--usuarios", "3", "--duracao", "1"]
    )

    assert codigo == 1
    assert "REPROVADO" in capsys.readouterr().out
