"""scan_runs composite index on status + last_progress_at

The orphan-cleanup job (introduced by `62ef600`) runs every minute and
queries `WHERE status='running' AND last_progress_at < cutoff`. Without
this index, SQLite full-scans the scan_runs table — fine when it has
~100 rows, but it grows ~10/day so this becomes expensive within weeks.

Revision ID: 429ed41825c6
Revises: efea1d6d8451
Create Date: 2026-05-15 15:26:44.149882

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '429ed41825c6'
down_revision: Union[str, Sequence[str], None] = 'efea1d6d8451'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_scan_runs_status_last_progress",
        "scan_runs",
        ["status", "last_progress_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scan_runs_status_last_progress", "scan_runs")
