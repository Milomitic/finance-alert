"""technical_scores table

Revision ID: 7c1a9e2d4b50
Revises: 512f9cc71164
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = "7c1a9e2d4b50"
down_revision = "512f9cc71164"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technical_scores",
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("composite", sa.Float(), nullable=False),
        sa.Column("trend", sa.Float(), nullable=True),
        sa.Column("momentum", sa.Float(), nullable=True),
        sa.Column("structure", sa.Float(), nullable=True),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("rel_strength", sa.Float(), nullable=True),
        sa.Column("signals", sa.Float(), nullable=True),
        sa.Column("posture", sa.String(length=16), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breakdown", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stock_id"),
    )
    op.create_index("ix_technical_scores_composite", "technical_scores", ["composite"])
    op.create_index("ix_technical_scores_posture", "technical_scores", ["posture"])


def downgrade() -> None:
    op.drop_index("ix_technical_scores_posture", table_name="technical_scores")
    op.drop_index("ix_technical_scores_composite", table_name="technical_scores")
    op.drop_table("technical_scores")
