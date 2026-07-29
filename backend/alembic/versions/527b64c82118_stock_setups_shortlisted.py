"""stock_setups: shortlisted flag

The per-detector cap used to DELETE the rows it dropped. That destroyed
`first_seen_at`, so a setup oscillating around the cap boundary restarted its
wait on every re-entry and quietly zeroed `lead_days` — the number the whole
feature is judged by. Rows are now flagged out of the shortlist instead.

Revision ID: 527b64c82118
Revises: 89d248a26a58
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = '527b64c82118'
down_revision: Union[str, Sequence[str], None] = '89d248a26a58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "stock_setups",
        sa.Column("shortlisted", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stock_setups", "shortlisted")
