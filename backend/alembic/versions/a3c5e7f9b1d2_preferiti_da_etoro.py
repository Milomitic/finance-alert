"""preferiti da eToro: origine, esclusioni, strumenti in watchlist (FA-125)

Revision ID: a3c5e7f9b1d2
Revises: f2a6c8e1d4b9
Create Date: 2026-10-06

`preferiti.origine` nasce «manuale» per le righe che esistono: sono tutte
stelle messe a mano. Il ritorno toglie i preferiti nati da eToro insieme alla
colonna, perche' senza l'origine diventerebbero indistinguibili da quelli
manuali e nessuna sincronizzazione potrebbe piu' toglierli: lo dichiara.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a3c5e7f9b1d2"
down_revision: str | None = "f2a6c8e1d4b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("preferiti") as b:
        b.add_column(sa.Column("origine", sa.String(length=8), nullable=False, server_default="manuale"))
    with op.batch_alter_table("etoro_strumenti") as b:
        b.add_column(sa.Column("in_watchlist", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "preferiti_esclusi",
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("escluso_il", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stock_id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM preferiti WHERE origine = 'etoro'")).scalar_one()
    if n:
        print(f"[a3c5e7f9b1d2] downgrade: {n} preferiti nati da eToro tolti")
    bind.execute(sa.text("DELETE FROM preferiti WHERE origine = 'etoro'"))
    op.drop_table("preferiti_esclusi")
    with op.batch_alter_table("etoro_strumenti") as b:
        b.drop_column("in_watchlist")
    with op.batch_alter_table("preferiti") as b:
        b.drop_column("origine")
