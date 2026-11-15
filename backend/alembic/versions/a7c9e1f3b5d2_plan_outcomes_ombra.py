"""plan_outcomes_ombra: le uscite alternative del piano, in prova silenziosa

Revision ID: a7c9e1f3b5d2
Revises: f4b6d8a0c2e5
Create Date: 2026-11-15

Tabella nuova e solo additiva (FA-141). Il ritorno la toglie per intero: le
righe si rigenerano dalle barre e da `plan_outcomes` alla passata successiva.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c9e1f3b5d2"
down_revision: str | None = "f4b6d8a0c2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plan_outcomes_ombra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("detector", sa.String(64), nullable=False),
        sa.Column("variante", sa.String(16), nullable=False),
        sa.Column("esito", sa.String(16), nullable=False),
        sa.Column("r_multiple", sa.Float(), nullable=False),
        sa.Column("bars_to_outcome", sa.Integer(), nullable=False),
        sa.Column("method_version", sa.String(16), nullable=False),
        sa.Column("matured_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ux_plan_outcomes_ombra_alert_variante", "plan_outcomes_ombra",
                    ["alert_id", "variante"], unique=True)
    op.create_index("ix_plan_outcomes_ombra_detector", "plan_outcomes_ombra", ["detector"])


def downgrade() -> None:
    op.drop_index("ix_plan_outcomes_ombra_detector", table_name="plan_outcomes_ombra")
    op.drop_index("ux_plan_outcomes_ombra_alert_variante", table_name="plan_outcomes_ombra")
    op.drop_table("plan_outcomes_ombra")
