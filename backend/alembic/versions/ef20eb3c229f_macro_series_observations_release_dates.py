"""macro_series_observations_release_dates

Revision ID: ef20eb3c229f
Revises: 47c2035665bd
Create Date: 2026-05-06 15:40:39.692231

Adds three tables for the FRED-driven macro calendar:
  - macro_series — one row per tracked indicator (CPI, NFP, FOMC, ...)
  - macro_observations — historical time-series values
  - macro_release_dates — scheduled publication dates (past + future)

See `app/models/macro.py` for the ORM definitions.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'ef20eb3c229f'
down_revision: Union[str, Sequence[str], None] = '47c2035665bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "macro_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fred_series_id", sa.String(length=64), nullable=False),
        sa.Column("fred_release_id", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("region", sa.String(length=8), nullable=False),
        sa.Column("importance", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fred_series_id"),
    )
    op.create_index(
        "ix_macro_series_fred_series_id", "macro_series",
        ["fred_series_id"], unique=False,
    )
    op.create_index(
        "ix_macro_series_fred_release_id", "macro_series",
        ["fred_release_id"], unique=False,
    )
    op.create_index(
        "ix_macro_series_region", "macro_series", ["region"], unique=False,
    )

    op.create_table(
        "macro_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["series_id"], ["macro_series.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id", "date", name="uq_macro_obs_series_date",
        ),
    )
    op.create_index(
        "ix_macro_observations_series_id", "macro_observations",
        ["series_id"], unique=False,
    )
    op.create_index(
        "ix_macro_observations_date", "macro_observations",
        ["date"], unique=False,
    )

    op.create_table(
        "macro_release_dates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(
            ["series_id"], ["macro_series.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_id", "date", name="uq_macro_rel_series_date",
        ),
    )
    op.create_index(
        "ix_macro_release_dates_series_id", "macro_release_dates",
        ["series_id"], unique=False,
    )
    op.create_index(
        "ix_macro_release_dates_date", "macro_release_dates",
        ["date"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_macro_release_dates_date", table_name="macro_release_dates")
    op.drop_index("ix_macro_release_dates_series_id", table_name="macro_release_dates")
    op.drop_table("macro_release_dates")
    op.drop_index("ix_macro_observations_date", table_name="macro_observations")
    op.drop_index("ix_macro_observations_series_id", table_name="macro_observations")
    op.drop_table("macro_observations")
    op.drop_index("ix_macro_series_region", table_name="macro_series")
    op.drop_index("ix_macro_series_fred_release_id", table_name="macro_series")
    op.drop_index("ix_macro_series_fred_series_id", table_name="macro_series")
    op.drop_table("macro_series")
