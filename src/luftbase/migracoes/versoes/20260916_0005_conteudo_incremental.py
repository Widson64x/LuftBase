"""Otimiza cursores de notificacoes e publicacoes.

Revisao: 20260916_0005
Anterior: 20260916_0004
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260916_0005"
down_revision: str | None = "20260916_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Adiciona indices alinhados aos cursores e filtros de audiencia."""

    op.create_index(
        "ix_core_notificacao_sistema_cursor",
        "tb_notificacao",
        ["id_sistema", "id_notificacao"],
        schema="core",
    )
    op.create_index(
        "ix_core_notificacao_usuario_cursor",
        "tb_notificacao",
        ["id_usuario_destino", "id_notificacao"],
        schema="core",
    )
    op.create_index(
        "ix_core_notificacao_grupo_cursor",
        "tb_notificacao",
        ["id_grupo_destino", "id_notificacao"],
        schema="core",
    )
    op.create_index(
        "ix_core_publicacao_sistema_status_cursor",
        "tb_publicacao",
        ["id_sistema", "status_publicacao", "id_publicacao"],
        schema="core",
    )


def downgrade() -> None:
    """Remove somente os indices de consulta incremental."""

    op.drop_index(
        "ix_core_publicacao_sistema_status_cursor",
        table_name="tb_publicacao",
        schema="core",
    )
    op.drop_index(
        "ix_core_notificacao_grupo_cursor",
        table_name="tb_notificacao",
        schema="core",
    )
    op.drop_index(
        "ix_core_notificacao_usuario_cursor",
        table_name="tb_notificacao",
        schema="core",
    )
    op.drop_index(
        "ix_core_notificacao_sistema_cursor",
        table_name="tb_notificacao",
        schema="core",
    )
