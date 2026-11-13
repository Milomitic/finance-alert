"""esiti_orizzonti: ogni alert misurato a 1, 5, 21 e 63 sedute, con un controllo

Revision ID: f4b6d8a0c2e5
Revises: e3a5c7e9b1d4
Create Date: 2026-11-14

Tabella nuova e solo additiva (FA-138, FA-139): `signal_outcomes` non cambia.
Il ritorno la toglie per intero; i dati si rigenerano dalle barre con
`app.scripts.backfill_esiti_orizzonti`, quindi non si perde niente che non si
possa ricostruire.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b6d8a0c2e5"
down_revision: str | None = "e3a5c7e9b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "esiti_orizzonti",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("detector", sa.String(64), nullable=False),
        sa.Column("tono", sa.String(8), nullable=False),
        sa.Column("ancora", sa.Date(), nullable=False),
        sa.Column("orizzonte", sa.Integer(), nullable=False),
        sa.Column("ingresso", sa.Float(), nullable=False),
        sa.Column("uscita", sa.Float(), nullable=False),
        sa.Column("rendimento", sa.Float(), nullable=False),
        sa.Column("mediana_universo", sa.Float(), nullable=True),
        sa.Column("eccesso_mediana", sa.Float(), nullable=True),
        sa.Column("colpo_mediana", sa.Integer(), nullable=True),
        sa.Column("controllo", sa.Float(), nullable=True),
        sa.Column("controlli_n", sa.Integer(), nullable=True),
        sa.Column("eccesso_controllo", sa.Float(), nullable=True),
        sa.Column("colpo_controllo", sa.Integer(), nullable=True),
        sa.Column("metodo", sa.String(16), nullable=False),
        sa.Column("maturato_il", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ux_esiti_orizzonti_alert_h", "esiti_orizzonti", ["alert_id", "orizzonte"], unique=True)
    op.create_index("ix_esiti_orizzonti_detector", "esiti_orizzonti", ["detector"])
    op.create_index("ix_esiti_orizzonti_ancora", "esiti_orizzonti", ["ancora"])


def downgrade() -> None:
    op.drop_index("ix_esiti_orizzonti_ancora", table_name="esiti_orizzonti")
    op.drop_index("ix_esiti_orizzonti_detector", table_name="esiti_orizzonti")
    op.drop_index("ux_esiti_orizzonti_alert_h", table_name="esiti_orizzonti")
    op.drop_table("esiti_orizzonti")
