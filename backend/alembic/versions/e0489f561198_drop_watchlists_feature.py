"""Drop the watchlists feature.

The watchlist UI (user-curated stock lists) and the Tier 2 per-watchlist
rule override mechanism were retired in May 2026. The /watchlists nav
slot was replaced by a Sectors overview hub. See CLAUDE.md for rationale.

Schema deltas:
  - DROP TABLE watchlist_items
  - DROP TABLE watchlists
  - ALTER rules: drop the `watchlist_id` column (and its FK on
    watchlists.id). SQLite needs `batch_alter_table` for column drops.

The downgrade re-creates the tables and the column but leaves them
empty — there is no way to recover the curated lists from the DB
without an external backup, so a true downgrade would only restore
the schema, not the data.

Revision ID: e0489f561198
Revises: 6ed5a4d41b17
Create Date: 2026-05-12 14:56:42.440170
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e0489f561198"
down_revision: Union[str, Sequence[str], None] = "6ed5a4d41b17"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop rules.watchlist_id first — its FK on watchlists.id would
    #    otherwise block the table drop on a strict-FK database. SQLite
    #    needs batch mode for column removal.
    with op.batch_alter_table("rules") as batch_op:
        # Drop the index too if it exists (Alembic auto-named it when the
        # FK was created; the name comes from the original migration). On
        # SQLite the batch rewrite handles this transparently.
        batch_op.drop_column("watchlist_id")

    # 2. Drop the watchlist tables.
    op.drop_table("watchlist_items")
    op.drop_table("watchlists")


def downgrade() -> None:
    # Re-create the tables. Data is gone — only schema is restored.
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "watchlist_items",
        sa.Column(
            "watchlist_id",
            sa.Integer(),
            sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "stock_id",
            sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Re-add the column on rules. Nullable=True since this was the
    # original schema (NULL = Tier 1 global).
    with op.batch_alter_table("rules") as batch_op:
        batch_op.add_column(
            sa.Column(
                "watchlist_id",
                sa.Integer(),
                sa.ForeignKey("watchlists.id", ondelete="CASCADE"),
                nullable=True,
            )
        )
