"""macro_series_add_source

Revision ID: 5971d1723def
Revises: 3f1c8a9d2e44
Create Date: 2026-05-14 01:13:21.929990

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5971d1723def'
down_revision: Union[str, Sequence[str], None] = '3f1c8a9d2e44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add `source` to macro_series — the publishing organization
    (e.g. "U.S. Bureau of Labor Statistics") shown in the new macro
    detail page header. Currency stays derived from `region` in the
    schema layer (US→USD, EZ/DE/FR/...→EUR, ...) — keeping it out of
    the DB avoids a duplicate source of truth.
    """
    with op.batch_alter_table("macro_series") as batch_op:
        batch_op.add_column(sa.Column("source", sa.String(255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("macro_series") as batch_op:
        batch_op.drop_column("source")
