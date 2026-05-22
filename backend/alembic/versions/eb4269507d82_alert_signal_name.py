"""alert signal_name

Revision ID: eb4269507d82
Revises: 429ed41825c6
Create Date: 2026-05-23 01:33:53.078528

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb4269507d82'
down_revision: Union[str, Sequence[str], None] = '429ed41825c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alerts") as b:
        b.add_column(sa.Column("signal_name", sa.String(length=64), nullable=True))
        b.create_index("ix_alerts_signal_name", ["signal_name"])


def downgrade() -> None:
    with op.batch_alter_table("alerts") as b:
        b.drop_index("ix_alerts_signal_name")
        b.drop_column("signal_name")
