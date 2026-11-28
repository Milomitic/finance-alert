"""Percorso confermato mentre il piano era aperto."""
import sqlalchemy as sa
from alembic import op

revision = "b4012fab78ac"
down_revision = "5d0053689053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("plan_outcomes", sa.Column("peak_fraction", sa.Float()))
    op.add_column("plan_outcomes", sa.Column("close_90_before_exit", sa.Boolean()))
    op.add_column("plan_outcomes", sa.Column("peak_date", sa.Date()))
    op.add_column("plan_outcomes", sa.Column("close_fraction", sa.Float()))


def downgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as table:
        for field in ("close_fraction", "peak_date", "peak_fraction", "close_90_before_exit"):
            table.drop_column(field)
