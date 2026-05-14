"""scan_runs_add_phase_history

Revision ID: efea1d6d8451
Revises: 5971d1723def
Create Date: 2026-05-14 02:17:34.287399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'efea1d6d8451'
down_revision: Union[str, Sequence[str], None] = '5971d1723def'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add `phase_history` JSON column to scan_runs.

    Powers the per-phase timing breakdown shown in the new ScanLogPanel.
    Stored as a JSON-encoded list of {phase, started_at, ended_at} entries
    populated by a SQLAlchemy event listener (on `ScanRun.phase` set).
    Default '[]' so old rows render as "no phase data" instead of crashing.
    """
    with op.batch_alter_table("scan_runs") as batch_op:
        batch_op.add_column(
            sa.Column("phase_history", sa.Text(), nullable=False, server_default="[]")
        )


def downgrade() -> None:
    with op.batch_alter_table("scan_runs") as batch_op:
        batch_op.drop_column("phase_history")
