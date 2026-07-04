"""signal_outcomes source

Revision ID: 9fc31644b13b
Revises: 2a137ffef964
Create Date: 2026-07-04 02:01:36.136661

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fc31644b13b'
down_revision: Union[str, Sequence[str], None] = '2a137ffef964'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Provenance flag on the outcomes warehouse: 'live' rows are written by
    mature_outcomes on alerts the engine actually fired; 'replay' rows come
    from the historical 10y replay backfill (closes the 63d-detector blind
    spot without waiting ~2 months of live maturation). Consumers filter or
    segment on it — live-vs-replay hit rates must never be silently mixed."""
    op.add_column(
        "signal_outcomes",
        sa.Column(
            "source", sa.String(8),
            nullable=False, server_default=sa.text("'live'"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("signal_outcomes") as batch:
        batch.drop_column("source")
