"""alerts composite indexes

Revision ID: 91d8c40e0e08
Revises: 9405b58cdb90
Create Date: 2026-07-08 22:30:43.982030

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '91d8c40e0e08'
down_revision: Union[str, Sequence[str], None] = '9405b58cdb90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Two composite indexes for the alerts hot paths (Segnali audit, SEG-2):
    (archived_at, triggered_at) serves the default list view's filter+sort as
    an ordered index scan (no temp B-tree); (stock_id, signal_name,
    signal_date) serves the dedup prior-alert lookup on every scan."""
    op.create_index(
        "ix_alerts_archived_triggered", "alerts", ["archived_at", "triggered_at"]
    )
    op.create_index(
        "ix_alerts_dedup_lookup", "alerts", ["stock_id", "signal_name", "signal_date"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_alerts_dedup_lookup", table_name="alerts")
    op.drop_index("ix_alerts_archived_triggered", table_name="alerts")
