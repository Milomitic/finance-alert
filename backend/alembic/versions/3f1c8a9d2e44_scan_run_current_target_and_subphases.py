"""scan_run current_target + widen phase for sub-phases

Revision ID: 3f1c8a9d2e44
Revises: e0489f561198
Create Date: 2026-05-12 12:00:00.000000

Two coupled additions powering richer progress feedback on the persistent
scan/recompute toast:

1. `current_target` (nullable, 64 chars): the worker writes "what it's touching
   right now" — typically a ticker, optionally annotated ("AAPL · chunk 3/12").
   Surfaces in the UI under the phase label so the user sees live focus
   instead of just a percentage.

2. Widen `phase` from String(16) to String(32): sub-phase strings like
   "evaluating:loading_rules" / "fetching:incremental" exceed the old length.
   SQLite doesn't enforce VARCHAR length so existing data is unaffected; the
   bump aligns the column with the model declaration.

Both columns are NULL-safe back-compat: historical rows get NULL current_target
(the UI hides the line when missing) and keep their existing phase strings
("fetching", "evaluating", "sector_stats", "scoring"), which remain valid.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3f1c8a9d2e44"
down_revision: Union[str, Sequence[str], None] = "e0489f561198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("current_target", sa.String(length=64), nullable=True)
        )
        batch_op.alter_column(
            "phase",
            existing_type=sa.String(length=16),
            type_=sa.String(length=32),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("scan_runs", schema=None) as batch_op:
        batch_op.alter_column(
            "phase",
            existing_type=sa.String(length=32),
            type_=sa.String(length=16),
            existing_nullable=True,
        )
        batch_op.drop_column("current_target")
