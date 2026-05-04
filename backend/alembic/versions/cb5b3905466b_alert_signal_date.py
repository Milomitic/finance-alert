"""alert_signal_date

Revision ID: cb5b3905466b
Revises: d6f96e0d827e
Create Date: 2026-05-04 15:08:27.400024

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cb5b3905466b'
down_revision: Union[str, Sequence[str], None] = 'd6f96e0d827e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add signal_date column to alerts.

    The market-data bar date on which the rule's condition matched. May differ
    from `triggered_at`: the scan runs daily/on-demand, so the bar with
    RSI=85 may have closed yesterday or last Friday while the alert row is
    created when the scan runs today. Nullable because legacy rows from
    before this column predate signal-date capture — they show "—" in UI.
    """
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("signal_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.drop_column("signal_date")
