"""separate macro value kind from upstream source scale

Revision ID: c6b2f93a1d47
Revises: 50c3faa68285
Create Date: 2026-09-10

FRED stores PAYEMS in thousands, GDPC1 in billions and RSAFS in millions.
The old `unit='level'` described the shape of the value but discarded that
scale, letting the frontend compact an already-scaled number a second time.
"""
import sqlalchemy as sa

from alembic import op

revision = "c6b2f93a1d47"
down_revision = "50c3faa68285"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "macro_series",
        sa.Column("source_scale", sa.String(length=16), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE macro_series
            SET source_scale = CASE fred_series_id
                WHEN 'PAYEMS' THEN 'thousands'
                WHEN 'GDPC1' THEN 'billions'
                WHEN 'RSAFS' THEN 'millions'
                ELSE 'ones'
            END
            WHERE unit = 'level'
            """
        )
    )


def downgrade() -> None:
    op.drop_column("macro_series", "source_scale")
