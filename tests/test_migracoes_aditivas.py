"""Regra de rollback: migracao nova e sempre aditiva.

O rollback do LuftBase e voltar a tag no `requirements.txt` do app. Isso so e seguro se o codigo da
versao anterior ainda roda sobre o schema da versao nova, o que exige migracoes que nao removem nem
endurecem nada. As revisoes ate `LIMITE_LEGADO` sao anteriores a regra e ficam de fora.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from luftbase.migracoes import obter_diretorio_migracoes

LIMITE_LEGADO = "20260923_0013"

_PROIBIDO = re.compile(
    r"\b(op\.(drop_table|drop_column|drop_constraint|drop_index|rename_table|alter_column)"
    r"|batch_alter_table|DROP\s+(TABLE|COLUMN)|RENAME\s+(TO|COLUMN))\b",
    re.IGNORECASE,
)


def _revisoes_novas() -> list[Path]:
    versoes = obter_diretorio_migracoes() / "versoes"
    return sorted(
        arquivo
        for arquivo in versoes.glob("2*.py")
        if arquivo.stem.split("_", 2)[0] + "_" + arquivo.stem.split("_", 2)[1] > LIMITE_LEGADO
    )


@pytest.mark.parametrize("arquivo", _revisoes_novas() or [None], ids=lambda a: a.name if a else "-")
def test_migracao_nova_nao_remove_nem_altera_schema_existente(arquivo: Path | None) -> None:
    if arquivo is None:
        pytest.skip("nenhuma migracao posterior ao limite legado")
    codigo = arquivo.read_text(encoding="utf-8")
    # O downgrade pode remover o que o upgrade criou; so o upgrade precisa ser aditivo.
    upgrade = codigo.split("def downgrade", 1)[0]

    achados = _PROIBIDO.findall(upgrade)

    assert not achados, f"{arquivo.name} nao e aditiva: {sorted({a[0] for a in achados})}"


def test_a_regra_pega_uma_migracao_destrutiva() -> None:
    assert _PROIBIDO.search("def upgrade():\n    op.drop_column('tb_x', 'y')")
    assert _PROIBIDO.search("def upgrade():\n    op.alter_column('tb_x', 'y', nullable=False)")
    assert not _PROIBIDO.search("def upgrade():\n    op.add_column('tb_x', sa.Column('y'))")
