"""signal_candidates: il registro dei match che i cancelli scartano

Revision ID: d4e8a1c7f2b9
Revises: c3a91f26d8b4
Create Date: 2026-09-24

Fino a oggi lo scan emetteva un alert solo se il match passava Forza minima,
allineamento al trend e follow-through, e di cio' che non passava non restava
traccia: l'effetto di un cancello non era misurabile dal vivo per
costruzione. Questa tabella registra gli scartati, e la maturazione ne scrive
l'esito con la stessa aritmetica degli alert. Motivazione per esteso in
`app/models/signal_candidate.py`.

⚠️ Il ritorno CANCELLA il registro. Non c'e' un altro posto dove quei match
esistono: chi ripercorre all'indietro questa migrazione perde le osservazioni
raccolte da quando e' nata, e le ritrova solo rifacendo lo studio sulla storia.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d4e8a1c7f2b9"
down_revision: str | None = "c3a91f26d8b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detector", sa.String(64), nullable=False),
        sa.Column("tone", sa.String(8), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("bar_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False),
        sa.Column("passa_forza", sa.Boolean(), nullable=False),
        sa.Column("passa_trend", sa.Boolean(), nullable=False),
        sa.Column("passa_follow", sa.Boolean(), nullable=False),
        sa.Column("factors", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=True),
        sa.Column("fwd_return", sa.Float(), nullable=True),
        sa.Column("mkt_neutral_excess", sa.Float(), nullable=True),
        sa.Column("mkt_neutral_hit", sa.Integer(), nullable=True),
        sa.Column("matured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("method_version", sa.String(16), nullable=True),
    )
    op.create_index("ix_signal_candidates_unico", "signal_candidates",
                    ["stock_id", "detector", "tone", "signal_date"], unique=True)
    op.create_index("ix_signal_candidates_attesa", "signal_candidates", ["matured_at"])


def downgrade() -> None:
    op.drop_index("ix_signal_candidates_attesa", table_name="signal_candidates")
    op.drop_index("ix_signal_candidates_unico", table_name="signal_candidates")
    op.drop_table("signal_candidates")
