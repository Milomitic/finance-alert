"""preferiti: la stella sui titoli, una lista sola (FA-112)

Revision ID: c7e2f4a9b1d6
Revises: b4c1e9d7a2f3
Create Date: 2026-09-28

Tabella nuova e vuota. Il ritorno la toglie e con lei la lista, che non si
ricava da nient'altro — detto qui invece che scoperto in un ripristino.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c7e2f4a9b1d6"
down_revision: str | None = "b4c1e9d7a2f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "preferiti",
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column(
            "aggiunto_il", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stock_id"),
    )


def downgrade() -> None:
    op.drop_table("preferiti")
