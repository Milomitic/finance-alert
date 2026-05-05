"""drop_bollinger_squeeze_rules

Revision ID: 47c2035665bd
Revises: a62229a35412
Create Date: 2026-05-05 18:03:14.455884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '47c2035665bd'
down_revision: Union[str, Sequence[str], None] = 'a62229a35412'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop existing Rule rows of kind 'bollinger_squeeze'.

    The category was retired in favor of more actionable desk/trader
    signals (ADX trend strength, gap up/down, mean reversion). Existing
    Alert history of this kind cascades-delete via the Alert.rule_id
    FK (`ondelete="CASCADE"`).
    """
    op.execute("DELETE FROM rules WHERE kind = 'bollinger_squeeze'")


def downgrade() -> None:
    """No-op: rules are user-managed; we don't recreate them on rollback.
    Re-adding the kind to the catalog is enough for users to recreate
    a rule via the editor if needed."""
    pass
