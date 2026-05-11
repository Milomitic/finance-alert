"""scan_run_kind

Revision ID: 6ed5a4d41b17
Revises: 98ebae3370fc
Create Date: 2026-05-11 12:59:28.745883

Add a `kind` discriminator column to scan_runs so the same row schema
can track BOTH alert-scan runs AND score-recompute runs. The existing
ScanProgressToast machinery (heartbeat, cancel-check, stale detection,
post-completion window) is generic enough to power both — we just need
to filter rows by kind on read so the alert-scan toast doesn't pick up
score-recompute rows and vice versa.

Backfill: all existing rows are alert-scan runs (the only kind that
existed before this migration), so we set NOT NULL with a server default
of 'alerts_scan' which SQLite applies to existing rows in the same DDL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6ed5a4d41b17'
down_revision: Union[str, Sequence[str], None] = '98ebae3370fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add scan_runs.kind. Default 'alerts_scan' backfills existing rows."""
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "kind",
                sa.String(length=20),
                nullable=False,
                server_default="alerts_scan",
            )
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.drop_column("kind")
