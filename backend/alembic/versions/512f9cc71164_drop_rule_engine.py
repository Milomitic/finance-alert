"""drop rule engine

Revision ID: 512f9cc71164
Revises: eb4269507d82
Create Date: 2026-05-23 15:16:39.148110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '512f9cc71164'
down_revision: Union[str, Sequence[str], None] = 'eb4269507d82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Irreversible (user-approved): purge rule-based alerts, then drop structures.
    op.execute("DELETE FROM alerts WHERE rule_id IS NOT NULL")
    with op.batch_alter_table("alerts") as b:
        b.drop_index("ix_alerts_rule_id")
        b.drop_column("rule_id")
    op.drop_table("rule_states")
    op.drop_table("rules")


def downgrade() -> None:
    raise NotImplementedError("Rule engine removal is irreversible (user-approved).")
