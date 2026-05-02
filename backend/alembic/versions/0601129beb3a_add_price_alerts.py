"""add price alerts

Revision ID: 0601129beb3a
Revises: b210847355b7
Create Date: 2026-05-02 12:41:01.979180

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0601129beb3a'
down_revision: Union[str, Sequence[str], None] = 'b210847355b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Create price_alerts table
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("target_price", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_alerts_stock_id", "price_alerts", ["stock_id"])
    op.create_index("ix_price_alerts_enabled", "price_alerts", ["enabled"])

    # 2. Make alerts.rule_id nullable (SQLite needs batch_alter_table)
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("alerts", schema=None) as batch_op:
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=False)

    op.drop_index("ix_price_alerts_enabled", table_name="price_alerts")
    op.drop_index("ix_price_alerts_stock_id", table_name="price_alerts")
    op.drop_table("price_alerts")
