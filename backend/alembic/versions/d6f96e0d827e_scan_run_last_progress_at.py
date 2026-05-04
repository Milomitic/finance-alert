"""scan_run_last_progress_at

Revision ID: d6f96e0d827e
Revises: 7e2e42691dff
Create Date: 2026-05-04 13:45:40.742930

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6f96e0d827e'
down_revision: Union[str, Sequence[str], None] = '7e2e42691dff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add last_progress_at heartbeat column to scan_runs.

    The column is set every time the worker reports progress (every N stocks
    via on_progress callback). The UI uses `now() - last_progress_at` to detect
    stuck/orphan scans — if no heartbeat for >2 min, the row is shown as stale
    and the user can stop it manually.
    """
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.drop_column("last_progress_at")
