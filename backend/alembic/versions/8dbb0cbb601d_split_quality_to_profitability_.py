"""split_quality_to_profitability_sustainability

Adds two new sub-score columns to stock_scores so the V3.2 6-pillar
framework can persist them: `profitability` (was the magnitude side
of Quality — ROE/ROA/margins) and `sustainability` (was the durability
side — debt/liquidity + new lanes for FCF quality, earnings stability,
margin trend, dividend coverage).

For backward compatibility the old `quality` column is kept during
the transition. A follow-up migration can drop it once all consumers
are confirmed to read the new columns.

Revision ID: 8dbb0cbb601d
Revises: ef20eb3c229f
Create Date: 2026-05-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = '8dbb0cbb601d'
down_revision: Union[str, Sequence[str], None] = 'ef20eb3c229f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLite needs batch_alter_table for ADD COLUMN with constraints/defaults.
    with op.batch_alter_table("stock_scores", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profitability", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("sustainability", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("stock_scores", schema=None) as batch_op:
        batch_op.drop_column("sustainability")
        batch_op.drop_column("profitability")
